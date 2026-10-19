#!/usr/bin/env python3
"""C0511: fail-closed, offline, phase-aware post-build diagnostics.

Accept only logs from the known public C0509 OSS workflow. Logs are untrusted
data, never commands. This tool does not call AI, build, edit, or certify.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from bx_ai_log_triage_c0510 import parse_log, scrub

# The synthetic negative compiler test log is intentionally excluded: its error
# is an expected success condition and must not be treated as a build failure.
PHASE_FILES = (
    "07_elf_types.log",
    "06_lld_version.log",
    "05_clang_version.log",
    "04_ninja_build.log",
    "03_cmake_configure.log",
    "02_source_sha256.log",
    "01_download.log",
    "00_environment.log",
)
ALLOWED_CONCLUSIONS = {
    "success", "failure", "cancelled", "timed_out", "skipped",
    "neutral", "action_required", "unknown",
}
MAX_WINDOW_BYTES = 500_000
MAX_SCAN_FILES = 60
MAX_REPORT_BYTES = 1_500_000

CATEGORY_KO = {
    "disk_full": "디스크 부족 가능성이 감지됐습니다.",
    "permission": "작업 폴더 권한 문제가 감지됐습니다.",
    "oom_suspected": "메모리 부족 징후가 감지됐습니다. 실제 OOM 여부는 별도 확인이 필요합니다.",
    "missing_header": "컴파일에 필요한 헤더 파일을 찾지 못했습니다.",
    "undefined_symbol": "링크 중 해결되지 않은 심볼이 발견됐습니다.",
    "missing_dependency": "필요한 외부 의존성을 찾지 못했습니다.",
    "cmake_configure": "CMake 설정 오류가 감지됐습니다.",
    "compiler_diagnostic": "컴파일러 오류 메시지가 감지됐습니다.",
    "timeout": "시간 제한으로 작업이 중단됐을 가능성이 있습니다.",
    "interrupted": "작업 중단 메시지가 발견됐습니다.",
}


def _safe_candidate(root: Path, candidate: Path) -> bool:
    """Reject symlinks at *every* component and paths escaping selected root."""
    if not candidate.is_file() or candidate.is_symlink():
        return False
    rel = candidate.relative_to(root)
    curr = root
    for part in rel.parts:
        curr = curr / part
        if curr.is_symlink():
            return False
    return candidate.resolve().is_relative_to(root.resolve())


def _read_tail(path: Path) -> tuple[str, dict[str, Any]]:
    before = path.stat()
    if not path.is_file() or path.is_symlink():
        raise ValueError("Unsafe log changed during scan")
    with path.open("rb") as stream:
        trunc = before.st_size > MAX_WINDOW_BYTES
        if trunc:
            stream.seek(before.st_size - MAX_WINDOW_BYTES)
        data = stream.read(MAX_WINDOW_BYTES + 1)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise ValueError("Log changed during read")
    if len(data) > MAX_WINDOW_BYTES:
        raise ValueError("Log grew during read")
    if trunc:
        # Discard incomplete UTF-8 / log line at tail window boundary.
        sep = data.find(b"\n")
        data = data[sep + 1:] if sep >= 0 else b""
    return data.decode("utf-8", errors="replace"), {
        "file_bytes": before.st_size, "window_bytes": len(data),
        "tail_window_only": trunc, "line_numbers": (
            "relative_to_tail_window" if trunc else "from_start_of_log"
        ),
    }


def inspect_run(log_root: Path, *, run_id: str, conclusion: str) -> dict[str, Any]:
    """Create a compact, sanitized advisory report; never claim native PASS."""
    if not re.fullmatch(r"[0-9]{1,18}", run_id or ""):
        raise ValueError("Run ID must be 1..18 ASCII digits")
    if conclusion not in ALLOWED_CONCLUSIONS:
        raise ValueError("Unsupported workflow conclusion")
    if (not log_root.is_absolute() or log_root.is_symlink()
            or not log_root.is_dir()):
        raise ValueError("Log root must be an absolute real directory")
    root = log_root.resolve()
    candidates = []
    # Only known log names inside a 'logs' folder, never arbitrary artifact files.
    for phase_index, name in enumerate(PHASE_FILES):
        for candidate in root.rglob(name):
            if candidate.parent.name != "logs":
                continue
            if not _safe_candidate(root, candidate):
                continue
            if len(candidates) >= MAX_SCAN_FILES:
                raise ValueError("Too many log candidates")
            content, meta = _read_tail(candidate)
            parsed = parse_log(content, exit_code=None)
            evidence = parsed["evidence"]
            severity = {"critical": 4, "high": 3, "medium": 2, "info": 1}
            strongest = max((severity[e["severity"]] for e in evidence), default=0)
            probe = None
            # Real C0509 case: LLVM/Lld compiled successfully, but the generic
            # 'lld' dispatcher was wrongly used to check ld.lld's version.
            lower = content.lower()
            if (name == "06_lld_version.log"
                    and "lld is a generic driver." in lower
                    and "invoke ld.lld" in lower):
                probe = {
                    "category": "wrong_lld_driver_probe",
                    "line": next(
                        (i for i, line in enumerate(content.splitlines(), 1)
                         if "lld is a generic driver." in line.lower()), 1),
                    "action_ko": "범용 lld가 아니라 ld.lld --version으로 검증하세요.",
                    "proof": "Exact generic-driver hint in 06_lld_version.log",
                }
            candidates.append((max(strongest, 5 if probe else 0),
                               -phase_index, name, meta, parsed, probe))
    # Prefer a grounded error rather than a clean build log from an earlier step.
    # When no known error exists, select the furthest available pipeline phase.
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    report: dict[str, Any] = {
        "schema": "BX_C0511_POSTBUILD_TRIAGE_V1",
        "source_run_id": run_id,
        "source_conclusion": conclusion,
        "scanned_known_logs": len(candidates),
        "ai": {"state": "not_run", "reason": "offline rule-only report"},
        "gate": {
            "stage1_pass": False, "stage2_pass": False,
            "windows_pass": False, "release_approved": False,
            "reason": "Only independent native binary + execution proof may pass a gate",
        },
    }
    if not candidates:
        report.update({
            "state": "log_unavailable",
            "summary_ko": "원본 빌드 로그를 찾지 못해 원인을 판단할 수 없습니다.",
            "next_steps_ko": ["원본 GitHub Actions 작업 단계와 로그 아티팩트를 확인하세요."],
            "selected_log": None, "diagnosis": None,
        })
        return report
    _, _, selected, meta, diagnosis, probe = candidates[0]
    if conclusion == "success":
        state = "workflow_reported_success_unverified"
        summary = "GitHub 작업은 성공으로 보고됐지만, 상용화 합격은 별도로 검증해야 합니다."
    elif conclusion in ("cancelled", "timed_out"):
        state = "workflow_interrupted"
        summary = "GitHub 작업이 중단됐습니다. 시간 제한·취소·리소스 상태를 확인하세요."
    elif conclusion == "failure":
        state = "workflow_failed_needs_review"
        summary = "GitHub 작업이 실패했습니다. 아래 근거와 실패 단계를 확인하세요."
    else:
        state = "workflow_conclusion_unverified"
        summary = "GitHub 실행 결론이 확정적이지 않습니다. 원본 작업 상태를 확인하세요."
    top = diagnosis["evidence"][:1]
    if probe:
        summary += " LLD를 범용 드라이버 이름으로 실행한 버전 검사 문제가 확인됐습니다."
    elif top:
        summary += " " + CATEGORY_KO.get(top[0]["category"], "확인할 오류 신호가 있습니다.")
    actions = ([probe["action_ko"]] if probe else diagnosis["action_guidance_ko"][:4]) or [
        "GitHub Actions 작업 단계와 실패 종료 코드를 확인하세요."
    ]
    if meta["tail_window_only"]:
        actions.append("큰 로그의 뒷부분만 분석했습니다. 행 번호는 추출 구간 기준입니다.")
    report.update({
        "state": state, "summary_ko": summary, "selected_log": selected,
        "log_window": meta, "diagnosis": diagnosis,
        "probe_issue": probe, "next_steps_ko": actions,
    })
    # No raw paths, unredacted log text, or commands in the report.
    if len(json.dumps(report, ensure_ascii=False).encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("Report exceeds limit")
    return report



def render_korean_report(report: dict[str, Any]) -> str:
    """Short, non-executable Korean report without raw attacker-controlled excerpts."""
    if report.get("schema") != "BX_C0511_POSTBUILD_TRIAGE_V1":
        raise ValueError("Invalid C0511 report schema")
    lines = [
        "BX PRO 빌드 자동진단 결과",
        "=======================",
        "원본 GitHub 실행 ID: " + str(report["source_run_id"]),
        "원본 실행 결과: " + report["source_conclusion"],
        "진단 상태: " + report["state"],
        "문제 요약: " + report["summary_ko"],
        "분석 대상 단계: " + (report.get("selected_log") or "원본 로그 없음"),
    ]
    window = report.get("log_window")
    if window and window.get("tail_window_only"):
        lines.append("주의: 큰 로그의 마지막 일부만 검사했습니다. 행 번호는 추출 구간 기준입니다.")
    issue = report.get("probe_issue")
    if issue:
        lines.append("실제 로그와 일치한 문제: " + issue["category"])
        lines.append("근거 위치: 선택 로그의 " + str(issue["line"]) + "번째 행")
    elif report.get("diagnosis") and report["diagnosis"]["evidence"]:
        ev = report["diagnosis"]["evidence"][0]
        lines.append("발견된 오류 유형: " + ev["category"])
        lines.append("근거 위치: 선택 로그의 " + str(ev["line"]) + "번째 행")
    lines.append("권장 확인 조치:")
    for i, action in enumerate(report.get("next_steps_ko", [])[:5], 1):
        # These instructions come from the fixed, trusted rule dictionary.
        lines.append(f"  {i}. {action}")
    lines.extend([
        "안전 판정: AI/로그 진단만으로 Clang Stage1, Stage2, Windows, 상용 출시 합격 불가",
        "고객 소스 자동 수정: 실행하지 않음",
        "원본 로그 명령 실행: 실행하지 않음",
        "",
    ])
    return "\n".join(lines)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BX C0511: 빌드 완료 후 안전한 한국어 자동진단")
    parser.add_argument("--log-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--conclusion", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--text-out", type=Path, help="Optional safe Korean TXT summary")
    args = parser.parse_args(argv)
    try:
        out = args.out
        if not out.is_absolute() or out.is_symlink() or not out.parent.is_dir():
            raise ValueError("Output requires an absolute non-symlink path and existing parent")
        if out.resolve().is_relative_to(args.log_root.resolve()):
            raise ValueError("Output must be outside untrusted log root")
        tmp = out.with_name(out.name + ".tmp")
        if tmp.is_symlink():
            raise ValueError("Temporary output symlink blocked")
        txt = args.text_out
        if txt is not None:
            if (not txt.is_absolute() or txt.is_symlink() or
                    not txt.parent.is_dir() or txt.resolve() == out.resolve()
                    or txt.resolve().is_relative_to(args.log_root.resolve())):
                raise ValueError("Text report path must be outside logs, distinct and safe")
            if txt.with_name(txt.name + ".tmp").is_symlink():
                raise ValueError("Temporary text report symlink blocked")
        data = inspect_run(args.log_root, run_id=args.run_id,
                           conclusion=args.conclusion)
        serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        tmp.write_text(serialized, encoding="utf-8")
        os.replace(tmp, out)
        if txt is not None:
            ttemp = txt.with_name(txt.name + ".tmp")
            ttemp.write_text(render_korean_report(data), encoding="utf-8")
            os.replace(ttemp, txt)
        print(data["state"], "-", data["summary_ko"])
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print("C0511 안전 중단:", scrub(str(exc)), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
