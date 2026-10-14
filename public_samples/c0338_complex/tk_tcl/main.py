import argparse
import json
import tkinter as tk
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    t=tk.Tcl()
    answer=int(t.eval('expr {6 * 7}'))
    assert answer == 42
    obj={'kind':'tk_tcl','answer':answer,'tcl_initialized':True}
    Path(args.output).write_bytes((json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8'))
    print('PUBLIC_SAMPLE_PASS')

if __name__=='__main__':main()
