#!/usr/bin/env python3
"""Public, stand-alone, bounded smoke test for source script or frozen EXE.

This only executes the public user-selected test target. It does not build anything,
install packages, contact services, or upload source files. The JSON result deliberately
contains no original stdout/stderr or full path.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

PASS_MARKER = 'BX_NAPARI_FUNCTIONAL_PASS'
STAGES = ('IMPORT_OK', 'VIEWER_CREATED', 'IMAGE_VERIFIED', 'VIEWER_CLOSED')
STAGE_PREFIX = 'BX_NAPARI_STAGE_'
WINDOWS_EXIT_CATEGORIES = {
    0xC0000005: 'WINDOWS_ACCESS_VIOLATION',
    0xC0000135: 'WINDOWS_DLL_NOT_FOUND',
    0xC0000409: 'WINDOWS_STACK_BUFFER_OVERRUN',
    0xC0150002: 'WINDOWS_SIDE_BY_SIDE',
}
CATEGORIES = (
    ('QT_PLUGIN', re.compile(r'(could not load the qt platform plugin|no qt platform plugin could be initialized|qt\.qpa\.plugin)', re.I)),
    ('MISSING_MODULE', re.compile(r'(ModuleNotFoundError|No module named)', re.I)),
    ('MISSING_DLL', re.compile(r'(DLL load failed|could not find .*\.dll|cannot find .*\.dll)', re.I)),
    ('PYTHON_EXCEPTION', re.compile(r'(Traceback \(most recent call last\)|\b(?:RuntimeError|ImportError|AttributeError|AssertionError):)', re.I)),
)


def scrub_output(value: str, limit: int = 2500) -> str:
    # GitHub secrets and local user identifiers must never go into public logs.
    value = re.sub(r'(?i)github_pat_[a-z0-9_]+|gh[pousr]_[a-z0-9_]+', '[REDACTED_TOKEN]', value)
    value = re.sub(r'(?i)(?:Bearer\s+)[a-z0-9._~+\-/]+=*', 'Bearer [REDACTED_TOKEN]', value)
    value = re.sub(r'(?i)[a-z]:\\Users\\[^\\\r\n ]+', r'C:\\Users\\[REDACTED_USER]', value)
    value = re.sub(r'(?i)(?:/home/|/Users/)[^/\r\n ]+', '/[REDACTED_USER]', value)
    value = re.sub(r'[\x00-\x08\x0b\x0e-\x1f\x7f]', '?', value)
    value = value.replace('::', ': :')  # prevent GitHub workflow command injection in logged excerpts
    return value[-limit:]


def read_tail(filename: Path, length: int = 32768) -> tuple[str,int]:
    with filename.open('rb') as f:
        f.seek(0,2); size=f.tell();f.seek(max(0,size-length))
        raw=f.read(length)
    return raw.decode('utf-8','replace'),size


def marker_is_exact_line(filename: Path) -> bool:
    """Find the full PASS line even when huge output pushes it out of the tail."""
    marker = PASS_MARKER.encode('utf-8')
    pending = bytearray()
    overlong = False
    with filename.open('rb') as f:
        while True:
            chunk = f.read(64 * 1024)
            if not chunk:
                break
            fragments = chunk.split(b'\n')
            for n,part in enumerate(fragments):
                if not overlong:
                    if len(pending) + len(part) <= len(marker) + 2:
                        pending.extend(part)
                    else:
                        overlong = True
                if n < len(fragments)-1:
                    if not overlong and pending.rstrip(b'\r') == marker:
                        return True
                    pending.clear(); overlong = False
    return not overlong and pending.rstrip(b'\r') == marker


def scan_stdout_markers(filename: Path) -> tuple[bool, str]:
    """Read full stdout and accept only exact, in-order bounded stage lines."""
    success = False
    stage_index = 0
    expected = [STAGE_PREFIX + stage for stage in STAGES]
    line = bytearray()
    overflow = False
    def finish_line():
        nonlocal stage_index, success, line, overflow
        if not overflow:
            value = bytes(line).rstrip(b'\r')
            if value == PASS_MARKER.encode('ascii'):
                success = True
            if stage_index < len(expected) and value == expected[stage_index].encode('ascii'):
                stage_index += 1
        line.clear()
        overflow = False
    with filename.open('rb') as f:
        while True:
            chunk = f.read(64 * 1024)
            if not chunk:
                break
            parts = chunk.split(b'\n')
            for index, segment in enumerate(parts):
                if not overflow:
                    if len(line) + len(segment) <= 128:
                        line.extend(segment)
                    else:
                        overflow = True
                if index < len(parts) - 1:
                    finish_line()
    if line or overflow:
        finish_line()
    return success, (STAGES[stage_index - 1] if stage_index else 'NOT_REACHED')


def scan_error_categories(*paths: Path) -> list[str]:
    """Find known error classes even when early messages drop out of the tail."""
    matches = set()
    for path in paths:
        with path.open('rb') as handle:
            overlap = ''
            while True:
                block = handle.read(64 * 1024)
                if not block:
                    break
                text = overlap + block.decode('utf-8', 'replace')
                for name, pattern in CATEGORIES:
                    if name not in matches and pattern.search(text):
                        matches.add(name)
                overlap = text[-768:]
    return [name for name, _ in CATEGORIES if name in matches]


def category_from_windows_exit(code: int | None) -> str | None:
    if type(code) is not int:
        return None
    return WINDOWS_EXIT_CATEGORIES.get(code & 0xFFFFFFFF)


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None: return
    if os.name == 'nt':
        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
    else:
        try: os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError: pass
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)


def evaluate(mode: str, target: Path, *, timeout_seconds: int = 120) -> tuple[dict,str]:
    result={'schema':'BX_C0403_RUNTIME_PROBE_V1','mode':mode,'status':'FAIL','reason':'NOT_RUN',
            'exit_code':None,'success_marker_seen':False,'categories':[],
            'stdout_size_bytes':0,'stderr_size_bytes':0,'elapsed_seconds':0.0,
            'last_stage':'NOT_REACHED','windows_exit_category':None}
    if not target.is_file():
        result['reason']='TARGET_NOT_FOUND'
        return result,''
    cmd=[sys.executable,str(target)] if mode=='source' else [str(target)]
    started=time.monotonic()
    err_preview=''
    with tempfile.TemporaryDirectory(prefix='bx_c0403_probe_') as td:
        out_file=Path(td)/'stdout.txt';err_file=Path(td)/'stderr.txt'
        with out_file.open('wb') as stdout,err_file.open('wb') as stderr:
            try:
                options={'stdout':stdout,'stderr':stderr,'stdin':subprocess.DEVNULL,
                         'shell':False,'cwd':str(target.parent),
                         'env':{**os.environ,'PYTHONUNBUFFERED':'1'}}
                if os.name=='nt':options['creationflags']=subprocess.CREATE_NEW_PROCESS_GROUP
                else:options['start_new_session']=True
                process=subprocess.Popen(cmd,**options)
                try:process.wait(timeout=timeout_seconds)
                except subprocess.TimeoutExpired:
                    kill_tree(process);result['reason']='TIMEOUT'
                else:result['exit_code']=process.returncode
            except OSError:
                result['reason']='START_FAILURE'
        std,size_out=read_tail(out_file)
        err,size_err=read_tail(err_file)
        result['stdout_size_bytes']=size_out
        result['stderr_size_bytes']=size_err
        result['success_marker_seen'],result['last_stage']=scan_stdout_markers(out_file)
        result['categories']=scan_error_categories(out_file,err_file)
        native_reason=category_from_windows_exit(result['exit_code'])
        if native_reason:
            result['windows_exit_category']=native_reason
            result['categories'].append(native_reason)
        if result['reason'] not in ('TIMEOUT','START_FAILURE'):
            if result['exit_code']!=0:result['reason']='NONZERO_EXIT'
            elif not result['success_marker_seen']:result['reason']='MARKER_MISSING'
            else:result.update(status='PASS',reason='OK')
        # Raw stderr and stdout stay ephemeral; never print untrusted data in public logs.
        err_preview=''
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    return result,err_preview


def main(argv=None) -> int:
    ap=argparse.ArgumentParser(description='Public C0403 Python/Windows EXE smoke comparison')
    ap.add_argument('--mode',required=True,choices=('source','exe'))
    ap.add_argument('--target',required=True)
    ap.add_argument('--json-out',required=True)
    ap.add_argument('--timeout',type=int,default=120)
    args=ap.parse_args(argv)
    if not 1 <= args.timeout <= 180:ap.error('timeout must be 1 to 180 seconds')
    target=Path(args.target).resolve()
    result,preview=evaluate(args.mode,target,timeout_seconds=args.timeout)
    dest=Path(args.json_out).resolve()
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix('.tmp')
    temp.write_text(json.dumps(result,sort_keys=True)+'\n',encoding='utf-8')
    temp.replace(dest)
    prefix='BX_C0403_'+args.mode.upper()
    for field in ('status','reason','exit_code','success_marker_seen','last_stage','windows_exit_category','categories','elapsed_seconds'):
        print(f'{prefix}_{field.upper()}={result[field]}',flush=True)
    if preview:
        print(prefix+'_ERROR_TAIL_BEGIN',flush=True)
        print(preview,flush=True)
        print(prefix+'_ERROR_TAIL_END',flush=True)
    return 0 if result['status']=='PASS' else 10

if __name__=='__main__':sys.exit(main())
