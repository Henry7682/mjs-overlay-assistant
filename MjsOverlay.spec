from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
import os
import sys
from pathlib import Path

# Never let unrelated developer tools on PATH supply same-named ICU/VC/OpenSSL
# DLLs. Qt uses Windows' ICU; Python supplies its own OpenSSL.
os.environ['PATH'] = os.pathsep.join(str(p) for p in (
    Path(sys.base_prefix), Path(sys.base_prefix)/'DLLs', Path(sys.prefix)/'Scripts',
    Path(sys.prefix)/'Lib/site-packages/PySide6',
    Path(sys.prefix)/'Lib/site-packages/shiboken6',
    Path(os.environ['SystemRoot'])/'System32', Path(os.environ['SystemRoot'])))

datas = [('assets', 'assets')]
datas += collect_data_files('rapidocr', excludes=['models/*'])
datas += copy_metadata('rapidocr')
hidden = collect_submodules('rapidocr') + collect_submodules('pywinauto')
hidden += collect_submodules('comtypes.gen')
bundle_name = os.environ.get('MJS_BUILD_NAME','MjsOverlay-0.3.10-preview')
a = Analysis(['main.py'], pathex=[], binaries=[], datas=datas, hiddenimports=hidden,
             excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtPdf',
                       'torch','tensorflow','paddle','openvino','tensorrt','pytest'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=bundle_name, debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=bundle_name)
