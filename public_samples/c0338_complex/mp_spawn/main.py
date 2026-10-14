import argparse
import json
import multiprocessing as mp
from pathlib import Path

def square(n):return n*n

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    ctx=mp.get_context('spawn')
    with ctx.Pool(processes=2) as pool:
        squares=pool.map(square,[1,2,3,4])
    assert squares==[1,4,9,16]
    obj={'kind':'mp_spawn','squares':squares,'sum':30}
    Path(args.output).write_bytes((json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8'))
    print('PUBLIC_SAMPLE_PASS')

if __name__=='__main__':
    mp.freeze_support()
    main()
