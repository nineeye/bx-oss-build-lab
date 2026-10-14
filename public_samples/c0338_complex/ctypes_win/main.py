import argparse
import ctypes
import json
import os
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    if os.name=='nt':
        lib=ctypes.WinDLL('kernel32',use_last_error=True)
        lib.GetCurrentProcessId.restype=ctypes.c_ulong
        pid=lib.GetCurrentProcessId()
    else:
        libc=ctypes.CDLL(None)
        libc.getpid.restype=ctypes.c_int
        pid=libc.getpid()
    assert pid>0
    obj={'kind':'ctypes_win','native_library_loaded':True,'pid_positive':True}
    Path(args.output).write_bytes((json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8'))
    print('PUBLIC_SAMPLE_PASS')

if __name__=='__main__':main()
