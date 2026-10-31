import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

from mjs_assistant.source_instance_guard import WindowsProbe, is_assistant_window, source_instance_guard


@pytest.mark.parametrize('title,kind,exe,expected', [
    ('名将浮窗助手 1.0.2', 'Qt681QWindowIcon', 'D:/other/python.exe', True),
    ('名将统计助手', 'Qt6QWindowIcon', 'pythonw.exe', True),
    ('名将浮窗助手 1.0.2', 'Qt6QWindowIcon', 'MjsOverlay.exe', True),
    ('Another project', 'Qt6QWindowIcon', 'python.exe', False),
    ('名将浮窗助手 文档', 'Notepad', 'notepad.exe', False),
    ('名将浮窗助手 1.0.2', 'Qt6QWindowIcon', 'unrelated.exe', False),
])
def test_window_identification(title, kind, exe, expected):
    assert is_assistant_window(title, kind, exe) is expected


@pytest.mark.parametrize('occupied,pids', [(True, []), (False, [123])])
def test_duplicate_guard_closes_handle(occupied, pids):
    probe = Mock(); probe.acquire.return_value = (42, occupied); probe.existing.return_value = pids
    with pytest.raises(RuntimeError, match='already running'):
        with source_instance_guard(probe): pytest.fail('Duplicate allowed')
    probe.close.assert_called_once_with(42)


def test_guard_is_held_through_source_execution_and_cleanup():
    probe = Mock(); probe.acquire.return_value = (42, False); probe.existing.return_value = []
    with pytest.raises(ValueError):
        with source_instance_guard(probe):
            probe.close.assert_not_called()
            raise ValueError('launch failed')
    probe.close.assert_called_once_with(42)


def test_probe_failure_does_not_start_or_leak_handle():
    probe = Mock(); probe.acquire.return_value = (42, False); probe.existing.side_effect = OSError('denied')
    with pytest.raises(OSError):
        with source_instance_guard(probe): pytest.fail('Unknown state allowed')
    probe.close.assert_called_once_with(42)


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Windows hidden Qt window')
def test_relative_main_hidden_window_with_different_data(tmp_path):
    pytest.importorskip('PySide6')
    # Actual relative command line contains no project name. No window is shown.
    (tmp_path/'main.py').write_text('''
from pathlib import Path
import os
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget
app = QApplication([])
window = QWidget()
window.setWindowTitle("名将浮窗助手 integration fixture")
window.winId()
timer = QTimer()
timer.timeout.connect(lambda: app.quit() if Path("stop").exists() else None)
timer.start(50)
QTimer.singleShot(15000, app.quit)
Path("ready").write_text(str(os.getpid()))
app.exec()
''', encoding='utf-8')
    env = {**os.environ, 'QT_QPA_PLATFORM': 'windows', 'MJS_ASSISTANT_HOME': str(tmp_path/'other-data')}
    child = subprocess.Popen([sys.executable, 'main.py'], cwd=tmp_path, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 15
        while not (tmp_path/'ready').exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert (tmp_path/'ready').exists(), 'Hidden Qt fixture failed to initialize'
        # Standard Windows venv python.exe may be a redirector; its child owns
        # the HWND. Embedded/virtualenv Python may execute in the parent PID.
        window_pid = int((tmp_path/'ready').read_text())
        assert window_pid in WindowsProbe().existing()
        with pytest.raises(RuntimeError, match='already running'):
            with source_instance_guard(): pytest.fail('Duplicate source allowed')
    finally:
        (tmp_path/'stop').write_text('stop')
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate(timeout=5)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows named mutex')
def test_native_guard_rejects_simultaneous_launchers():
    probe = WindowsProbe()
    handle, occupied = probe.acquire()
    try:
        with pytest.raises(RuntimeError, match='already running'):
            with source_instance_guard(): pytest.fail('Concurrent launcher allowed')
    finally:
        probe.close(handle)
