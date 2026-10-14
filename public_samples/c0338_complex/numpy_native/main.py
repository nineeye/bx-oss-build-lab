import argparse
import json
from pathlib import Path
import numpy as np

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    arr=np.array([[2,3],[5,7]],dtype=np.int64)
    result=(arr @ arr.T).tolist()
    assert result==[[13,31],[31,74]]
    obj={'kind':'numpy_native','matrix':result,'trace':87}
    Path(args.output).write_bytes((json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8'))
    print('PUBLIC_SAMPLE_PASS')

if __name__=='__main__':main()
