"""C0338 public-only opt-in native Windows PyInstaller compatibility gate.

Never takes customer source paths or emits customer binaries. Checks frozen output
content and frozen executable hash, without considering this a release approval.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

BASE=Path(__file__).resolve().parent
APPS=('tk_tcl','pillow_native','numpy_native','mp_spawn','ctypes_win')
VERSIONS=('6.16.0','6.22.3')
MANIFEST=BASE/'manifest.json'

class GateError(ValueError):pass

def digest(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def _file(path:Path)->bytes:
    if path.is_symlink() or not path.is_file():raise GateError('PUBLIC_SOURCE_MISSING_OR_LINK')
    return path.read_bytes()

def verify_public_sources(app:str)->dict:
    if app not in APPS:raise GateError('APP_NOT_ALLOWLISTED')
    manifest=json.loads(_file(MANIFEST).decode('utf-8'))
    if manifest.get('schema')!='HBX_C0338_PUBLIC_COMPLEX_MATRIX_V1':
        raise GateError('PUBLIC_MANIFEST_SCHEMA_MISMATCH')
    entry=manifest['apps'][app]
    expected_files=sorted(entry['source_sha256'])
    actual_files=sorted(p.relative_to(BASE/app).as_posix() for p in (BASE/app).rglob('*') if p.is_file())
    if expected_files!=actual_files:raise GateError('PUBLIC_SOURCE_SET_CHANGED')
    for rel,expected in entry['source_sha256'].items():
        p=(BASE/app/rel)
        if digest(_file(p))!=expected:raise GateError('PUBLIC_SOURCE_CHANGED')
    return entry

def run_source(app:str,output:Path)->dict:
    entry=verify_public_sources(app)
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise GateError('OUTPUT_MUST_NOT_PREEXIST')
    proc=subprocess.run([sys.executable,str(BASE/app/'main.py'),'--output',str(output)],
                         cwd=output.parent,capture_output=True,timeout=40,check=False,env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'})
    if proc.returncode!=0 or proc.stdout.strip()!=b'PUBLIC_SAMPLE_PASS':
        raise GateError('PUBLIC_SOURCE_EXECUTION_FAILED')
    if digest(_file(output))!=entry['output_sha256']:raise GateError('PUBLIC_OUTPUT_MISMATCH')
    return {'app':app,'result':'PASS','output_sha256':entry['output_sha256']}

def _subprocess(args:list[str],cwd:Path,limit:int)->tuple[int,bytes]:
    try:
        p=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         timeout=limit,check=False,env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'})
    except subprocess.TimeoutExpired as exc:
        raise GateError('PUBLIC_PROCESS_TIMEOUT') from exc
    return p.returncode,p.stdout

def run_windows(app:str,version:str,work:Path)->dict:
    if os.name!='nt':raise GateError('NATIVE_WINDOWS_REQUIRED')
    if version not in VERSIONS:raise GateError('PYINSTALLER_VERSION_NOT_ALLOWLISTED')
    entry=verify_public_sources(app)
    if importlib.metadata.version('pyinstaller')!=version:raise GateError('PYINSTALLER_VERSION_MISMATCH')
    if app=='pillow_native' and importlib.metadata.version('Pillow')!='11.3.0':raise GateError('PILLOW_VERSION_MISMATCH')
    if app=='numpy_native' and importlib.metadata.version('numpy')!='2.3.3':raise GateError('NUMPY_VERSION_MISMATCH')
    work.mkdir(parents=True,exist_ok=True)
    exe=work/'dist'/app/(app+'.exe')
    if exe.exists():raise GateError('EXE_MUST_NOT_PREEXIST')
    args=[sys.executable,'-m','PyInstaller','--clean','--noconfirm','--onedir','--noupx',
          '--log-level','ERROR','--name',app,'--distpath',str(work/'dist'),
          '--workpath',str(work/'build'),'--specpath',str(work/'spec')]
    if app=='pillow_native':args.extend(['--add-data',str(BASE/app/'data'/'two_pixels.ppm')+';data'])
    args.append(str(BASE/app/'main.py'))
    returncode,_logs=_subprocess(args,work,240)
    if returncode!=0:raise GateError('PYINSTALLER_BUILD_FAILED')
    data=_file(exe)
    if not data.startswith(b'MZ') or len(data)<1024:raise GateError('EXE_PE_INVALID')
    out=work/'한글 경로 with spaces'/'result.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    # Running from unrelated workdir verifies that resources are not CWD-relative.
    cwd=work/'unrelated_cwd';cwd.mkdir(parents=True,exist_ok=True)
    code,stdout=_subprocess([str(exe),'--output',str(out)],cwd,65)
    if code!=0 or stdout.strip()!=b'PUBLIC_SAMPLE_PASS':raise GateError('FROZEN_EXE_FAILED')
    if digest(_file(out))!=entry['output_sha256']:raise GateError('FROZEN_OUTPUT_HASH_MISMATCH')
    # TOCTOU: after building we still require unchanged public original source.
    verify_public_sources(app)
    return {'app':app,'pyinstaller':version,'result':'PASS','reason':'NONE',
            'exe_sha256':digest(data),'output_sha256':entry['output_sha256'],
            'customer_release_approved':False,'actual_customer_programs_built':0}

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser()
    p.add_argument('--app',choices=APPS,required=True)
    p.add_argument('--version',choices=VERSIONS)
    p.add_argument('--work',type=Path)
    p.add_argument('--source-only',action='store_true')
    args=p.parse_args(argv)
    if not args.source_only and (not args.version or not args.work):p.error('Windows native mode requires --version and --work')
    try:
        if args.source_only:
            with tempfile.TemporaryDirectory(prefix='bx_public_c0338_') as t:
                result=run_source(args.app,Path(t)/'result.json')
        else:
            result=run_windows(args.app,args.version,args.work)
        code=0
    except (GateError,ValueError,OSError,subprocess.SubprocessError,KeyError) as exc:
        reason=str(exc)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{3,70}',reason,re.ASCII):reason='PUBLIC_NATIVE_GATE_ERROR'
        result={'app':args.app,'pyinstaller':args.version,'result':'FAIL','reason':reason,
                'customer_release_approved':False,'actual_customer_programs_built':0}
        code=1
    result.update({'schema':'HBX_C0338_PUBLIC_COMPLEX_WINDOWS_RESULT_V1',
                   'windows_native_executed':not args.source_only and os.name=='nt',
                   'customer_release_approved':False,'actual_customer_programs_built':0})
    if args.work:
        args.work.mkdir(parents=True,exist_ok=True)
        (args.work/'report.json').write_bytes((json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode())
    print(json.dumps(result,sort_keys=True))
    return code

if __name__=='__main__':raise SystemExit(main())
