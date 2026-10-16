#!/usr/bin/env python3
"""C0426 public OSS Windows heavy builds. Only public packages and generated tests."""
import hashlib, json, os, pathlib, shutil, subprocess, sys, tempfile, time, traceback

CASES = {
    "napari": {
      "packages": ["napari[all]==0.9.2"],
      "collect": ["napari", "napari_resources", "vispy", "magicgui", "qtpy", "superqt"],
      "src": """import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import numpy as np, napari
v=napari.components.ViewerModel()
a=v.add_image(np.arange(100,dtype=np.uint8).reshape(10,10))
assert a.data.shape==(10,10) and int(a.data[-1,-1])==99
v.layers.clear()
print('BX_HARD10_PASS')
"""
    },
    "ocrmypdf": {
      "packages": ["ocrmypdf==17.13.0", "pillow", "pypdf"],
      "collect": ["ocrmypdf", "pikepdf"],
      "native": True,
      "src": """import os, tempfile
from PIL import Image,ImageDraw,ImageFont
import ocrmypdf
from pypdf import PdfReader
with tempfile.TemporaryDirectory() as d:
    im=Image.new('RGB',(1500,450),'white')
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',135)
    ImageDraw.Draw(im).text((120,100),'123456',font=font,fill='black')
    src=os.path.join(d,'src.pdf');dst=os.path.join(d,'dst.pdf')
    im.save(src,'PDF',resolution=300.0)
    ocrmypdf.ocr(src,dst,force_ocr=True,output_type='pdf',progress_bar=False)
    txt=' '.join(p.extract_text() or '' for p in PdfReader(dst).pages)
    assert '123456' in txt,repr(txt[:200])
print('BX_HARD10_PASS')
"""
    },
    "labelme": {
      "packages": ["labelme==7.8.1"],
      "collect": ["labelme", "PySide6"],
      "src": """import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import numpy as np
import labelme
from PySide6.QtWidgets import QApplication,QLabel
app=QApplication([])
w=QLabel('한글 Labelme Qt')
mask=np.zeros((20,20),dtype=bool);mask[2:12,2:12]=True
assert w.text()=='한글 Labelme Qt'
assert mask.shape==(20,20) and 80<=int(mask.sum())<=130
print('BX_HARD10_PASS')
"""
    },
    "rapidocr": {
      "packages": ["rapidocr_onnxruntime", "pillow"],
      "collect": ["rapidocr_onnxruntime", "onnxruntime"],
      "src": """from rapidocr_onnxruntime import RapidOCR
from PIL import Image,ImageDraw,ImageFont
import numpy as np
im=Image.new('RGB',(680,160),'white')
ImageDraw.Draw(im).text((20,20),'TEST 1234',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',80),fill='black')
ocr=RapidOCR()
value,_=ocr(np.asarray(im))
assert value is None or isinstance(value,list)
print('BX_HARD10_PASS')
"""
    },
    "opencv": {
      "packages": ["opencv-python==4.12.0.88"],
      "collect": ["cv2"],
      "src": """import cv2,numpy as np
a=np.zeros((100,100,3),dtype=np.uint8);cv2.rectangle(a,(20,20),(80,80),(255,255,255),2)
ok,data=cv2.imencode('.png',a)
assert ok
b=cv2.imdecode(data,cv2.IMREAD_COLOR)
assert b.shape==(100,100,3)
assert np.count_nonzero(cv2.Canny(b,50,100))>100
print('BX_HARD10_PASS')
"""
    },
    "pyarrow": {
      "packages": ["pandas==2.3.3", "pyarrow==22.0.0"],
      "collect": ["pyarrow", "pandas"],
      "src": """import io
import pandas as pd
a=pd.DataFrame({'품목':['볼트','너트'],'수량':[3,5]})
b=io.BytesIO();a.to_parquet(b,index=False,engine='pyarrow');b.seek(0)
out=pd.read_parquet(b,engine='pyarrow')
assert out.equals(a)
print('BX_HARD10_PASS')
"""
    },
    "scipy": {
      "packages": ["scipy==1.16.3", "scikit-image==0.25.2"],
      "collect": ["scipy", "skimage"],
      "src": """import numpy as np
from scipy.ndimage import gaussian_filter
from skimage.measure import label
a=np.zeros((64,64));a[10:20,10:20]=1;a[40:50,40:50]=1
b=gaussian_filter(a,1.0)
assert label(b>0.5).max()==2
print('BX_HARD10_PASS')
"""
    },
    "pyside6": {
      "packages": ["PySide6==6.10.0"],
      "collect": ["PySide6"],
      "src": """import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtGui import QImage
app=QApplication([])
widget=QLabel('한글 test')
img=QImage(50,50,QImage.Format.Format_RGB32)
img.fill(0xff22aa55)
assert widget.text()=='한글 test' and img.width()==50
widget.close()
print('BX_HARD10_PASS')
"""
    },
    "matplotlib": {
      "packages": ["matplotlib==3.10.7"],
      "collect": ["matplotlib"],
      "src": """import io,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,ax=plt.subplots()
ax.plot([1,2,3],[2,4,1])
o=io.BytesIO();fig.savefig(o,format='png')
assert o.getvalue().startswith(bytes([137,80,78,71])) and len(o.getvalue())>1000
plt.close(fig)
print('BX_HARD10_PASS')
"""
    }
}

case=sys.argv[1]
report={"schema":"BX_C0426_PUBLIC_HARD10_V1","case":case,"status":"BLOCK","stage":"PREPARE",
        "run_id":os.getenv("GITHUB_RUN_ID"),"commit":os.getenv("GITHUB_SHA"),
        "public_upstream_only":True,"full_upstream_app_certified":False,
        "private_product_certified":False,"customer_release_approved":False}
started=time.monotonic()
def run(cmd,timeout,env=None):
    print("COMMAND:",' '.join(map(str,cmd)),flush=True)
    result=subprocess.run(cmd,timeout=timeout,check=False,env=env)
    if result.returncode: raise RuntimeError(f"EXIT_{result.returncode}: {cmd[0:3]}")
def h(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
try:
    if case=="openshot":
        report["stage"]="OPENSHOT_SOURCE_CLONE"
        run(["git","clone","--depth","1","--recurse-submodules","--shallow-submodules","https://github.com/OpenShot/libopenshot-audio.git"],300)
        run(["git","clone","--depth","1","--recurse-submodules","--shallow-submodules","https://github.com/OpenShot/libopenshot.git"],300)
        app_config=pathlib.Path("libopenshot-audio/JuceLibraryCode/AppConfig.h")
        current=app_config.read_text(encoding="utf-8")
        if " #define   JUCE_ASIO 1" not in current:raise RuntimeError("ASIO_ENABLE_PATTERN_MISSING")
        app_config.write_text(current.replace(" #define   JUCE_ASIO 1"," #define   JUCE_ASIO 0"),encoding="utf-8")
        report["asio_optional_disabled"]=True
        report["stage"]="OPENSHOT_CMAKE_CONFIG"
        vcpkg_root=pathlib.Path(os.environ.get("VCPKG_INSTALLATION_ROOT",r"C:\\vcpkg"))
        vcpkg_exe=vcpkg_root/"vcpkg.exe"
        if not vcpkg_exe.is_file():
            vcpkg_found=shutil.which("vcpkg")
            if not vcpkg_found: raise RuntimeError("VCPKG_NOT_FOUND")
            vcpkg_exe=pathlib.Path(vcpkg_found)
            vcpkg_root=vcpkg_exe.parent
        report["stage"]="OPENSHOT_INSTALL_ZLIB"
        run([str(vcpkg_exe),"install","zlib:x64-windows"],600)
        toolchain=vcpkg_root/"scripts"/"buildsystems"/"vcpkg.cmake"
        if not toolchain.is_file():raise RuntimeError("VCPKG_CMAKE_TOOLCHAIN_MISSING")
        run(["cmake","-S","libopenshot-audio","-B","out-audio","-A","x64",f"-DCMAKE_TOOLCHAIN_FILE={toolchain}","-DCMAKE_SHARED_LINKER_FLAGS=/DEFAULTLIB:Dbghelp.lib"],300)
        report["stage"]="OPENSHOT_AUDIO_NATIVE_BUILD"
        run(["cmake","--build","out-audio","--config","Release","--target","openshot-audio","--parallel","2"],600)
        report["stage"]="OPENSHOT_VIDEO_CMAKE_CONFIG"
        run(["cmake","-S","libopenshot","-B","out-video","-A","x64","-DUSE_QT6=ON",f"-DOpenShotAudio_ROOT={pathlib.Path('out-audio').resolve()}",f"-DCMAKE_TOOLCHAIN_FILE={toolchain}"],300)
        report["stage"]="OPENSHOT_VIDEO_NATIVE_BUILD"
        run(["cmake","--build","out-video","--config","Release","--parallel","2"],600)
        report["status"]="PASS_COMPONENT_ONLY"
    else:
        spec=CASES[case]
        if spec.get("native"):
            report["stage"]="NATIVE_DEPS"
            run(["choco","install","-y","--no-progress","tesseract","ghostscript"],480)
        report["stage"]="INSTALL_PUBLIC_OSS"
        run([sys.executable,"-m","pip","install","--disable-pip-version-check","PyInstaller==6.22.3"]+spec["packages"],480)
        work=pathlib.Path("bx_hard10.py")
        work.write_text(spec["src"],encoding="utf-8")
        env=dict(os.environ,QT_QPA_PLATFORM="offscreen",MPLBACKEND="Agg")
        report["stage"]="SOURCE_FUNCTIONAL"
        baseline=subprocess.run([sys.executable,str(work)],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=120,env=env)
        print("SOURCE_OUT",baseline.stdout[-2000:],"SOURCE_ERR",baseline.stderr[-2000:],flush=True)
        if baseline.returncode or "BX_HARD10_PASS" not in baseline.stdout:
            raise RuntimeError("SOURCE_FUNCTIONAL_FAILED")
        report["stage"]="PYINSTALLER_REAL_WINDOWS_BUILD"
        cmd=[sys.executable,"-m","PyInstaller","--noconfirm","--clean","--onedir",
             "--name","BX_HARD10_"+case]
        for module in spec["collect"]:
            cmd+=["--collect-all",module]
        if case == "napari":
            cmd+=["--hidden-import", "napari_resources.resources", "--collect-data", "napari_resources"]
        cmd+=[str(work)]
        build_start=time.monotonic();run(cmd,600,env)
        report["build_seconds"]=round(time.monotonic()-build_start,2)
        folder=pathlib.Path("dist")/("BX_HARD10_"+case)
        exe=folder/("BX_HARD10_"+case+".exe")
        if not exe.is_file():raise RuntimeError("BUILT_EXE_MISSING")
        report["exe_sha256"]=h(exe)
        report["exe_bytes"]=exe.stat().st_size
        report["stage"]="KOREAN_PATH_TWICE"
        dest=pathlib.Path(tempfile.gettempdir())/("BX 한글 공백 "+case)
        if dest.exists():shutil.rmtree(dest)
        shutil.copytree(folder,dest)
        moved=dest/exe.name
        if h(moved)!=report["exe_sha256"]:raise RuntimeError("MOVED_EXE_HASH_MISMATCH")
        for i in range(2):
            runout=subprocess.run([str(moved)],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=130,env=env)
            print("RUNTIME",i,runout.returncode,runout.stdout[-1500:],runout.stderr[-1500:],flush=True)
            if runout.returncode or "BX_HARD10_PASS" not in runout.stdout:
                raise RuntimeError("FROZEN_RUNTIME_FAILED_"+str(i))
            if h(moved)!=report["exe_sha256"]: raise RuntimeError("EXE_CHANGED_AFTER_RUN")
        report["status"]="PASS"
except Exception as exc:
    report["reason"]=str(exc)[:450]
    print("ERROR_TYPE",type(exc).__name__,traceback.format_exc()[-4000:],flush=True)
finally:
    report["elapsed_seconds"]=round(time.monotonic()-started,2)
    print("BX_C0426_RECEIPT "+json.dumps(report,ensure_ascii=False,sort_keys=True),flush=True)
sys.exit(0 if report["status"] in ("PASS","PASS_COMPONENT_ONLY") else 1)
