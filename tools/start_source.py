"""Source-only launcher. No updater, installed EXE fallback, or game input."""
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def prepare():
    import mjs_assistant
    from mjs_assistant.build_identity import get_build_identity
    if Path(mjs_assistant.__file__).resolve().parent != ROOT / 'mjs_assistant':
        raise RuntimeError('Wrong source package loaded; repair the development environment.')
    import struct
    if sys.version_info[:2] != (3, 11) or struct.calcsize('P') != 8:
        raise RuntimeError('Python 3.11 x64 is required. Run setup.ps1 -Development.')
    folder = Path(os.environ.get('MJS_ASSISTANT_HOME') or ROOT / '.research' / 'dev-data').resolve()
    folder.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.TemporaryFile(dir=folder):
        pass
    os.environ['MJS_ASSISTANT_HOME'] = str(folder)
    print(f'Source: {ROOT}\nPython: {sys.executable}\nBuild: {get_build_identity().display}\nData: {folder}', flush=True)
    return folder


def main():
    folder = prepare()
    if '--check' in sys.argv:
        from PySide6 import QtCore, QtGui, QtWidgets
        import cv2, onnxruntime, rapidocr, windows_capture, pywinauto
        print('Source environment ready; no assistant or automation started.')
        return 0
    from PySide6.QtCore import QLockFile
    lock = QLockFile(str(folder / 'assistant.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(50):
        raise RuntimeError('Assistant already running with this data directory; exit it first.')
    lock.unlock()
    sys.argv = [str(ROOT / 'main.py')]
    runpy.run_path(str(ROOT / 'main.py'), run_name='__main__')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f'Source startup failed: {error}', file=sys.stderr)
        raise SystemExit(1)
