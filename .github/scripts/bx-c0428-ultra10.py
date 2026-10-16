#!/usr/bin/env python3
"""BX C0428 public OSS ultra-hard Windows native build probe.
Runs one upstream source build, never checks out BX private/customer source.
An incomplete build is BLOCK/FAIL, never a fabricated PASS.
"""
import json, os, pathlib, shutil, subprocess, sys, time, traceback, re

CONFIG = {
 "godot": ("https://github.com/godotengine/godot.git", "SCons Windows native game engine + headless runtime"),
 "obs": ("https://github.com/obsproject/obs-studio.git", "OBS multimedia/native plugins full dependency challenge"),
 "freecad": ("https://github.com/FreeCAD/FreeCAD.git", "FreeCAD OpenCASCADE native CAD stack"),
 "qgis": ("https://github.com/qgis/QGIS.git", "QGIS Qt/GDAL/PROJ spatial desktop suite"),
 "kicad": ("https://github.com/KiCad/kicad-source-mirror.git", "KiCad EDA native wxWidgets dependency stack"),
 "blender": ("https://github.com/blender/blender.git", "Blender native 3D application"),
 "krita": ("https://github.com/KDE/krita.git", "Krita paint/Qt dependency stack"),
 "gimp": ("https://github.com/GNOME/gimp.git", "GIMP GTK/Meson Windows dependency stack"),
 "openshot": ("https://github.com/OpenShot/libopenshot.git", "OpenShot C++ audio and video libraries"),
 "tesseract": ("https://github.com/tesseract-ocr/tesseract.git", "Tesseract native OCR library + executable")
}
if len(sys.argv) != 2 or sys.argv[1] not in CONFIG:
    print("USAGE: python bx-c0428-ultra10.py "+ " | ".join(CONFIG));sys.exit(2)
case=sys.argv[1]
repo,goal=CONFIG[case]
report={"schema":"BX_C0428_PUBLIC_ULTRA10_V1", "case":case,"source_url":repo,
 "goal":goal,"status":"BLOCK","last_stage":"PREFLIGHT","cause":"NOT_COMPLETED",
 "windows_native_build_attempted":False,"full_upstream_app_certified":False,
 "private_product_certified":False,"customer_release_approved":False,
 "github_run_id":os.environ.get("GITHUB_RUN_ID",""),
 "github_sha":os.environ.get("GITHUB_SHA",""),"upstream_sha":None,
 "steps":[]}
root=pathlib.Path.cwd()
start=time.monotonic()
def cmd(stage,args,seconds=240,cwd=None,required=True):
    report["last_stage"]=stage
    spec={"stage":stage,"command":[str(x) for x in args],"timeout_seconds":seconds}
    print("BX_STAGE "+stage+" START",flush=True)
    begun=time.monotonic()
    try:
        proc=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                            text=True,encoding="utf-8",errors="replace",timeout=seconds,check=False)
        output=proc.stdout or ""
        code=proc.returncode
        spec.update({"code":code,"elapsed_seconds":round(time.monotonic()-begun,2),
                     "last_lines":output.splitlines()[-28:]})
        if output: print(output[-10000:],flush=True)
        if code and required:raise RuntimeError("EXIT_"+str(code)+"_AT_"+stage)
        return output
    except subprocess.TimeoutExpired as exc:
        spec.update({"code":None,"elapsed_seconds":round(time.monotonic()-begun,2),"timeout":True})
        raise RuntimeError("TIMEOUT_"+stage) from exc
    finally:
        report["steps"].append(spec)
        print("BX_STAGE "+stage+" END",flush=True)
def clone(repo_url, pinned_tag=None):
    args=["git","-c","core.longpaths=true","clone","--depth","1","--filter=blob:none"]
    if pinned_tag:
        args+=["--branch",pinned_tag]
    args += [repo_url,"source"]
    cmd("UPSTREAM_SHALLOW_CLONE",args,200)
    v=cmd("UPSTREAM_COMMIT",["git","rev-parse","HEAD"],20,cwd="source")
    sha=v.strip().splitlines()[-1]
    if not re.fullmatch("[a-f0-9]{40}",sha):raise RuntimeError("UNVERIFIED_UPSTREAM_COMMIT")
    report["upstream_sha"]=sha
def cmake_app(flags,build_target=None):
    cmd("WINDOWS_CMAKE_CONFIGURE",["cmake","-S","source","-B","native-build","-A","x64"]+flags,180)
    report["windows_native_build_attempted"]=True
    cmd("WINDOWS_NATIVE_COMPILE",["cmake","--build","native-build","--config","Release","--parallel","2"]+
        (["--target",build_target] if build_target else []),380)
def cmake_source(folder,flags,build_target=None):
    cmd("WINDOWS_CMAKE_CONFIGURE",["cmake","-S",folder,"-B","native-build","-A","x64"]+flags,180)
    report["windows_native_build_attempted"]=True
    cmd("WINDOWS_NATIVE_COMPILE",["cmake","--build","native-build","--config","Release","--parallel","2"]+
        (["--target",build_target] if build_target else []),380)
try:
    if os.name!="nt":raise RuntimeError("UNSUPPORTED_OS_REQUIRES_WINDOWS")
    if case=="openshot":
        # Reuse C0426 real public upstream build, including its component-only gate.
        report["last_stage"]="OPENSHOT_NESTED_NATIVE_OSS"
        report["windows_native_build_attempted"]=True
        cmd("OPENSHOT_FULL_UPSTREAM_BUILD",[sys.executable,
             ".github/scripts/bx-c0426-public-hard10.py","openshot"],730)
        report["status"]="PASS_COMPONENT_ONLY"
        report["cause"]="OPENSHOT_NATIVE_AUDIO_VIDEO_COMPONENTS_BUILT_NOT_GUI"
    else:
        clone(repo, pinned_tag="32.2.2" if case=="obs" else None)
        if case=="godot":
            cmd("INSTALL_SCONS",[sys.executable,"-m","pip","install","--disable-pip-version-check","SCons>=4.7,<5","zstandard"],120)
            report["windows_native_build_attempted"]=True
            cmd("GODOT_NATIVE_CPP_COMPILE",[sys.executable,"-m","SCons","platform=windows",
                 "target=template_release","arch=x86_64","lto=none","accesskit=no","d3d12=no","angle=no","disable_3d=yes","disable_advanced_gui=yes","module_text_server_adv_enabled=no","module_text_server_fb_enabled=yes","-j2"],500,cwd="source")
            exe=next(iter((pathlib.Path("source")/"bin").glob("godot.windows.template_release*.exe")),None)
            if not exe:raise RuntimeError("BUILT_GODOT_EXE_NOT_FOUND")
            cmd("GODOT_HEADLESS_RUN",[str(exe.absolute()),"--headless","--version"],60)
        elif case=="gimp":
            cmd("MESON_INSTALL",[sys.executable,"-m","pip","install","meson","ninja"],120)
            cmd("MESON_GTK_CONFIGURE",["meson","setup","native-build","source",
                "--buildtype=release"],180)
            report["windows_native_build_attempted"]=True
            cmd("MESON_NATIVE_BUILD",["meson","compile","-C","native-build","-j","2"],360)
        elif case=="tesseract":
            vcpkg=pathlib.Path(os.environ.get("VCPKG_INSTALLATION_ROOT",r"C:\vcpkg"))
            vexe=vcpkg/"vcpkg.exe"
            if not vexe.is_file():raise RuntimeError("VCPKG_NOT_FOUND")
            cmd("LEPTONICA_VCPKG_NATIVE_DEP",[str(vexe),"install","leptonica:x64-windows"],330)
            toolchain=vcpkg/"scripts"/"buildsystems"/"vcpkg.cmake"
            cmake_app(["-DBUILD_TRAINING_TOOLS=OFF","-DOPENMP_BUILD=OFF",
                        "-DSW_BUILD=OFF",f"-DCMAKE_TOOLCHAIN_FILE={toolchain}"],"tesseract")
            candidates=list(pathlib.Path("native-build").rglob("tesseract.exe"))
            if not candidates:raise RuntimeError("TESSERACT_EXE_NOT_FOUND")
            cmd("TESSERACT_NATIVE_RUNTIME",[str(candidates[0].absolute()),"--version"],60)
        elif case=="obs":
            cmake_app(["-DOBS_VERSION_OVERRIDE=32.0.0","-DENABLE_UI=OFF","-DENABLE_BROWSER=OFF","-DENABLE_PLUGINS=OFF"],"libobs")
        elif case=="freecad":
            cmake_app(["-DBUILD_GUI=OFF","-DBUILD_FEM=OFF","-DBUILD_TEST=OFF"])
        elif case=="qgis":
            cmd("FLEX_BISON_PINNED_PUBLIC_DEP",["choco","install","winflexbison3","--version=2.5.24.20210105","-y","--no-progress"],240)
            flex=shutil.which("win_flex.exe")
            bison=shutil.which("win_bison.exe")
            if not flex or not bison: raise RuntimeError("FLEX_BISON_NOT_DISCOVERABLE")
            cmd("FLEX_NATIVE_VERSION",[flex,"--version"],15)
            cmd("BISON_NATIVE_VERSION",[bison,"--version"],15)
            cmake_app(["-DWITH_GUI=OFF","-DWITH_DESKTOP=OFF","-DWITH_SERVER=OFF","-DWITH_QTWEBKIT=OFF",
                       f"-DFLEX_EXECUTABLE={flex}",f"-DBISON_EXECUTABLE={bison}"])
        elif case=="kicad":
            cmake_app(["-DKICAD_BUILD_QA_TESTS=OFF","-DKICAD_BUILD_I18N=OFF"])
        elif case=="blender":
            cmake_app(["-DWITH_CYCLES=OFF","-DWITH_OPENCOLORIO=OFF","-DWITH_PYTHON_INSTALL=OFF"])
        elif case=="krita":
            cmake_app(["-DBUILD_TESTING=OFF","-DBUILD_KRITA_QT_DESIGNER_PLUGIN=OFF"])
        # CMake target built does not certify the full desktop GUI/installer.
        report["status"]="PASS_COMPONENT_ONLY" if case=="obs" else "PASS_NATIVE_BUILD"
        report["cause"]="SOURCE_NATIVE_BUILD_GATE_PASSED_NOT_CUSTOMER_RELEASE"
except Exception as exc:
    report["cause"]=str(exc)[:320]
    print("BX_EXCEPTION",traceback.format_exc()[-2000:],flush=True)
finally:
    report["elapsed_seconds"]=round(time.monotonic()-start,2)
    payload=json.dumps(report,ensure_ascii=False,sort_keys=True)
    print("BX_C0428_ULTRA_RECEIPT "+payload,flush=True)
sys.exit(0 if report["status"].startswith("PASS") else 1)
