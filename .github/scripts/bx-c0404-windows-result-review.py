#!/usr/bin/env python3
"""Public C0404 Windows source/frozen-report comparison and Korean next actions.

NOT an independent attestation or commercial release gate: the source reports
remain produced by the same runner. Never treat forged reports as proof.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

PROBE_SCHEMA = 'BX_C0403_RUNTIME_PROBE_V1'
REVIEW_SCHEMA = 'BX_C0404_WINDOWS_RESULT_REVIEW_V1'
SHA_RE = re.compile(r'^[a-fA-F0-9]{64}$')
MAX_BYTES = 128_000
KNOWN_CATEGORIES = frozenset(('QT_PLUGIN','MISSING_MODULE','MISSING_DLL','PYTHON_EXCEPTION'))
KNOWN_REASONS = frozenset(('OK','TARGET_NOT_FOUND','START_FAILURE','TIMEOUT','NONZERO_EXIT','MARKER_MISSING','NOT_RUN'))
HINTS = {
    'QT_PLUGIN': 'Qt 플랫폼 플러그인과 실행 PC의 그래픽/디스플레이 환경을 확인하세요.',
    'MISSING_DLL': '누락된 DLL과 네이티브 라이브러리의 패키징 위치를 확인하세요.',
    'MISSING_MODULE': 'PyInstaller hidden-import 및 패키지 의존성을 점검하세요.',
    'PYTHON_EXCEPTION': '원본과 EXE의 예외 위치 및 입력 자료를 비교하세요.',
}


class EvidenceInvalid(ValueError):
    pass


def unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise EvidenceInvalid('DUPLICATE_JSON_KEY')
        obj[key] = value
    return obj


def load_probe(path: str, expected_mode: str) -> dict:
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise EvidenceInvalid('MISSING_OR_SYMLINK_REPORT')
    if p.stat().st_size > MAX_BYTES:
        raise EvidenceInvalid('REPORT_TOO_LARGE')
    try:
        doc = json.loads(p.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(EvidenceInvalid('NONFINITE_NUMBER')))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceInvalid('INVALID_JSON') from exc
    if not isinstance(doc, dict) or doc.get('schema') != PROBE_SCHEMA or doc.get('mode') != expected_mode:
        raise EvidenceInvalid('PROBE_SCHEMA_OR_MODE_MISMATCH')
    if doc.get('status') not in ('PASS', 'FAIL') or not isinstance(doc.get('reason'), str):
        raise EvidenceInvalid('INVALID_STATUS_OR_REASON')
    if doc['reason'] not in KNOWN_REASONS:
        raise EvidenceInvalid('UNKNOWN_RUNTIME_REASON')
    if not isinstance(doc.get('success_marker_seen'), bool):
        raise EvidenceInvalid('INVALID_MARKER_FLAG')
    code = doc.get('exit_code')
    if code is not None and (type(code) is not int or code < -2147483648 or code > 4294967295):
        raise EvidenceInvalid('INVALID_EXIT_CODE')
    categories = doc.get('categories')
    if not isinstance(categories, list) or any(not isinstance(x, str) or len(x) > 60 for x in categories):
        raise EvidenceInvalid('INVALID_CATEGORIES')
    if any(x not in KNOWN_CATEGORIES for x in categories):
        raise EvidenceInvalid('UNKNOWN_ERROR_CATEGORY')
    if len(categories) > 30:
        raise EvidenceInvalid('EXCESSIVE_CATEGORIES')
    if doc['status'] == 'PASS' and not (doc['reason'] == 'OK' and code == 0 and doc['success_marker_seen']):
        raise EvidenceInvalid('CONTRADICTORY_PASS_REPORT')
    if doc['status'] == 'FAIL' and doc['reason'] == 'OK':
        raise EvidenceInvalid('CONTRADICTORY_FAILURE_REPORT')
    return doc


def compare(source: dict, exe: dict, before_sha: str, after_sha: str, *, run_id: str='', attempt: str='') -> dict:
    """Evaluate two *reported* test outcomes. This never approves a sale."""
    before = before_sha.lower().strip()
    after = after_sha.lower().strip()
    hash_provided = bool(before or after)
    if hash_provided and not (SHA_RE.fullmatch(before) and SHA_RE.fullmatch(after)):
        raise EvidenceInvalid('INVALID_OR_UNPAIRED_EXE_HASH')
    if run_id and not re.fullmatch(r'[0-9]{1,25}',run_id):
        raise EvidenceInvalid('INVALID_RUN_ID')
    if attempt and not re.fullmatch(r'[0-9]{1,10}',attempt):
        raise EvidenceInvalid('INVALID_ATTEMPT')

    source_pass = source['status']=='PASS' and source['reason']=='OK' and source['exit_code']==0
    exe_pass = exe['status']=='PASS' and exe['reason']=='OK' and exe['exit_code']==0
    hash_match = bool(before) and before==after
    if source_pass and exe_pass and hash_match:
        decision = 'REPORTED_FUNCTIONAL_PASS'
        guidance = '원본과 EXE 기능검사 기록이 모두 PASS입니다. 실제 GitHub 실행 로그와 산출물을 별도로 확인하세요.'
    elif hash_provided and not hash_match:
        decision = 'EXE_HASH_CHANGED'
        guidance = 'EXE 실행 전후 해시가 달라졌습니다. 산출물 무결성을 먼저 조사하세요.'
    elif not source_pass:
        decision = 'SOURCE_RUNTIME_FAILED'
        guidance = '원본 Python부터 실패했습니다. EXE 패키징을 탓하기 전에 원본 실행환경을 수정하세요.'
    elif not exe_pass:
        decision = 'FROZEN_EXE_RUNTIME_FAILED'
        primary = next((name for name in exe['categories'] if name in HINTS), None)
        guidance = '원본은 정상이고 EXE 실행검사만 실패했습니다. ' + HINTS.get(primary, '실행파일의 종료 코드와 오류 분류를 확인하세요.')
    else:
        decision = 'HASH_EVIDENCE_MISSING'
        guidance = 'EXE 실행 전후 SHA-256 기록이 없어 검증을 완료할 수 없습니다.'
    return {
        'schema': REVIEW_SCHEMA,
        'scope': 'PUBLIC_NAPARI_SOURCE_VS_WINDOWS_EXE_SELF_REPORTED',
        'decision': decision,
        'source_status': source['status'],
        'source_reason': source['reason'],
        'frozen_status': exe['status'],
        'frozen_reason': exe['reason'],
        'frozen_exit_code': exe['exit_code'],
        'frozen_error_categories': exe['categories'][:30],
        'exe_hash_checked': bool(before),
        'exe_hash_equal': hash_match,
        'github_run_id': run_id,
        'github_run_attempt': attempt,
        'next_action_ko': guidance,
        'evidence_consistency_only': True,
        'independent_windows_attestation': False,
        'private_bx_engine_tested': False,
        'customer_sale_approved': False,
    }


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description='C0404 Windows diagnostic report review (no certification)')
    p.add_argument('--source-json',required=True)
    p.add_argument('--exe-json',required=True)
    p.add_argument('--before-sha256',default='')
    p.add_argument('--after-sha256',default='')
    p.add_argument('--run-id',default='')
    p.add_argument('--run-attempt',default='')
    p.add_argument('--json-out',required=True)
    a=p.parse_args(argv)
    try:
        source=load_probe(a.source_json,'source')
        exe=load_probe(a.exe_json,'exe')
        doc=compare(source,exe,a.before_sha256,a.after_sha256,run_id=a.run_id,attempt=a.run_attempt)
    except (EvidenceInvalid, OSError, ValueError) as e:
        # Error names are constants: don't print untrusted paths or JSON in public job logs.
        code=str(e) if isinstance(e,EvidenceInvalid) else 'EVIDENCE_READ_ERROR'
        print('C0404_REVIEW_INVALID='+re.sub(r'[^A-Z_]', '_', code)[:90])
        return 3
    destination=Path(a.json_out)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=destination.parent,prefix='.bx_c0404_',suffix='.tmp',delete=False) as tmp:
        json.dump(doc,tmp,ensure_ascii=False,sort_keys=True,indent=2)
        tmp.write('\n');tmpname=tmp.name
    os.replace(tmpname,destination)
    print('C0404_DECISION='+doc['decision'])
    print('C0404_NEXT_ACTION_KO='+doc['next_action_ko'])
    print('C0404_WINDOWS_CERTIFIED=false')
    return 0 if doc['decision']=='REPORTED_FUNCTIONAL_PASS' else 10

if __name__=='__main__':
    sys.exit(main())
