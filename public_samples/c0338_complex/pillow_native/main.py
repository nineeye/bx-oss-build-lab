import argparse
import json
from pathlib import Path
from PIL import Image

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    source=Path(__file__).resolve().parent/'data'/'two_pixels.ppm'
    with Image.open(source) as im:
        rgb=im.convert('RGB');pixels=[list(rgb.getpixel((x,0))) for x in range(2)]
    assert pixels==[[10,20,30],[200,40,15]]
    obj={'kind':'pillow_native','pixels':pixels,'width':2,'height':1}
    Path(args.output).write_bytes((json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8'))
    print('PUBLIC_SAMPLE_PASS')

if __name__=='__main__':main()
