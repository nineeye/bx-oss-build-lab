#!/usr/bin/env python3
"""BX C0510 — offline build-log evidence triage.

Public, reusable reference module. Treat logs and model suggestions as untrusted.
No network, shell execution, project writes, edits, or PASS/certification claims.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

MAX_LOG_BYTES = 3_000_000
MAX_LINES = 30000
MAX_EVIDENCE = 12

# Human-review action IDs, not executable commands.
ACTIONS = {
    "inspect_disk": "출력 디스크 용량과 임시 작업공간을 확인하세요.",
    "inspect_memory": "메모리 제한·OOM 기록을 확인하고 병렬 수 축소를 검토하세요.",
    "inspect_permissions": "대상 폴더 소유권과 쓰기 권한을 확인하세요.",
    "inspect_include_paths": "헤더 설치 여부와 include 경로를 확인하세요.",
    "inspect_link_inputs": "라이브러리 연결 순서와 누락 심볼의 출처를 확인하세요.",
    "inspect_dependency": "의존성 이름·버전·경로가 설치 조건과 맞는지 확인하세요.",
    "inspect_cmake": "CMake 오류 직전 단계와 캐시·원본 경로를 확인하세요.",
    "inspect_timeout": "중단이 시간 제한 때문인지 확인하고 안전 재개하세요.",
    "inspect_process_exit": "실제 프로세스 종료 코드와 마지막 오류를 확인하세요.",
    "inspect_compiler_diagnostic": "컴파일러가 지목한 원본 파일·행을 확인하세요.",
    "request_human_review": "근거가 충분하지 않아 담당자 확인이 필요합니다.",
}
RULES = (
    ("disk_full", r"no space left on device|disk quota exceeded", "critical", "inspect_disk"),
    ("permission", r"permission denied|operation not permitted", "high", "inspect_permissions"),
    ("oom_suspected", r"(?:^|\W)(?:out of memory|oom-kill|oom killer|killed process \d+|cc1plus.*killed)(?:\W|$)", "high", "inspect_memory"),
    ("missing_header", r"fatal error:.*(?:no such file or directory|file not found)", "high", "inspect_include_paths"),
    ("undefined_symbol", r"undefined reference to|undefined symbol:|ld\.lld: error: undefined", "high", "inspect_link_inputs"),
    ("missing_dependency", r"could not find (?:a )?package|could not find .*configuration file|no package .* found", "high", "inspect_dependency"),
    ("cmake_configure", r"cmake error(?: at|:)", "high", "inspect_cmake"),
    ("compiler_diagnostic", r"(?:^|\s)(?:fatal )?error:\s", "medium", "inspect_compiler_diagnostic"),
    ("timeout", r"(?:timed out|timeout after|time limit exceeded|deadline exceeded)", "medium", "inspect_timeout"),
    ("interrupted", r"ninja: build stopped: interrupted|received signal: interrupt|keyboardinterrupt", "info", "inspect_timeout"),
)
COMPILED = tuple((name, re.compile(pat, re.I), severity, action) for name, pat, severity, action in RULES)
RANK = {"critical": 4, "high": 3, "medium": 2, "info": 1}
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:github_pat_|ghp_|gho_|ghu_|ghs_)[A-Za-z0-9_]{12,}"),
    re.compile(r"(?i)\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s\"']+"),
)


def scrub(s: str) -> str:
    for pattern in SECRET_PATTERNS:
        s = pattern.sub("[REDACTED]", s)
    return s


def parse_log(log: str, *, exit_code: int | None = None, ai_proposal: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(log, str):
        raise TypeError("log must be text")
    if len(log.encode("utf-8")) > MAX_LOG_BYTES:
        raise ValueError("log exceeds configured safe limit")
    if exit_code is not None and (not isinstance(exit_code, int) or isinstance(exit_code, bool)):
        raise TypeError("exit_code must be int or None")

    # All evidence is sanitized before parsing, prompting or exporting.
    lines = scrub(log).splitlines()
    if len(lines) > MAX_LINES:
        raise ValueError("too many log lines")
    found = []
    for num, line in enumerate(lines, 1):
        normalized = line.strip()
        if not normalized:
            continue
        # Never execute or follow instructions found inside a log.
        for name, pattern, severity, action in COMPILED:
            if pattern.search(normalized):
                found.append({"category": name, "severity": severity,
                              "line": num, "excerpt": normalized[:450],
                              "action_id": action})
                break
    found.sort(key=lambda x: (-RANK[x["severity"]], x["line"], x["category"]))
    evidence = found[:MAX_EVIDENCE]
    has_hard_diagnostics = any(x["severity"] in ("critical", "high", "medium") for x in found)
    interrupted = any(x["category"] in ("timeout", "interrupted") for x in found)
    if exit_code == 0 and not has_hard_diagnostics:
        # A process returning zero is not evidence of release readiness.
        status = "process_exit_zero_unverified"
    elif exit_code == 0 and has_hard_diagnostics:
        status = "contradictory_needs_review"
    elif interrupted and exit_code in (None, 124, 130, 137, 143, -2, -9, -15):
        status = "partial_or_interrupted"
    elif exit_code is not None and exit_code != 0:
        status = "failed"
    else:
        status = "unknown"
    actions = list(dict.fromkeys(x["action_id"] for x in evidence))
    if not actions:
        actions = ["request_human_review"]
    output = {
        "schema": "BX_C0510_LOG_TRIAGE_V1",
        "classification": status,
        "exit_code": exit_code,
        "lines_seen": len(lines),
        "signal_count": len(found),
        "evidence": evidence,
        "recommended_action_ids": actions,
        "action_guidance_ko": [ACTIONS[x] for x in actions],
        "ai": {"state": "not_run", "reason": "optional proposal absent"},
        "gate": {"stage1_pass": False, "stage2_pass": False, "windows_pass": False,
                 "release_approved": False,
                 "reason": "Log triage is advice only; independent native execution gate required"},
    }
    if ai_proposal is not None:
        output["ai"] = validate_ai_proposal(ai_proposal, evidence)
    return output


def validate_ai_proposal(proposal: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Independent validator; models cannot invent line references or commands."""
    rejected = {"state": "rejected", "reason": "AI proposal failed schema/evidence validation"}
    if not isinstance(proposal, dict):
        return rejected
    if set(proposal) != {"category", "line", "action_id", "summary_ko"}:
        return rejected
    category, line, action, summary = (proposal[k] for k in ("category", "line", "action_id", "summary_ko"))
    if not isinstance(category, str) or not isinstance(line, int) or isinstance(line, bool):
        return rejected
    if action not in ACTIONS or not isinstance(summary, str) or not 1 <= len(summary) <= 200:
        return rejected
    if any(ch in summary for ch in ("\n", "\r", "\x00", "\t")):
        return rejected
    if not any(x["category"] == category and x["line"] == line and x["action_id"] == action for x in evidence):
        return rejected
    return {"state": "evidence_matched_untrusted_suggestion",
            "category": category, "line": line, "action_id": action,
            "summary_ko": scrub(summary), "not_authorized_to_execute": True}


def read_log(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError("input must be a regular non-symlink log file")
    if path.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("log file is too large")
    return path.read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BX C0510 — 오프라인 빌드 로그 안전 진단")
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--exit-code", type=int, default=None)
    parser.add_argument("--ai-proposal-json", type=Path,
                        help="Optional local model JSON (not commands; evidence-validated)")
    parser.add_argument("--out", type=Path,
                        help="JSON result destination (must be outside input directory if desired)")
    args = parser.parse_args(argv)
    try:
        ai = None
        if args.ai_proposal_json is not None:
            if args.ai_proposal_json.is_symlink() or not args.ai_proposal_json.is_file():
                raise ValueError("AI proposal must be a regular file")
            if args.ai_proposal_json.stat().st_size > 16384:
                raise ValueError("AI proposal too large")
            ai = json.loads(args.ai_proposal_json.read_text(encoding="utf-8"))
        result = parse_log(read_log(args.log), exit_code=args.exit_code, ai_proposal=ai)
        serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            if args.out.is_symlink() or args.out.resolve() == args.log.resolve():
                raise ValueError("output must not replace the source log or a symlink")
            if not args.out.parent.is_dir():
                raise ValueError("output directory does not exist")
            # No arbitrary builds or shell commands. Save diagnosis only.
            temp = args.out.with_name(args.out.name + ".tmp")
            if temp.is_symlink():
                raise ValueError("temporary output symlink blocked")
            temp.write_text(serialized, encoding="utf-8")
            os.replace(temp, args.out)
        else:
            sys.stdout.write(serialized)
        return 0
    except (ValueError, TypeError, OSError, json.JSONDecodeError) as exc:
        print("진단 실패:", scrub(str(exc)), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
