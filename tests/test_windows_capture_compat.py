import sys
from types import SimpleNamespace

import numpy as np
import pytest

from mjs_assistant import capture
from mjs_assistant.windows_compat import capture_options, optional_capture_error, runtime_issue


@pytest.mark.parametrize('build,cursor,border,interval', [
    (18362, None, None, None), (19041, False, None, None),
    (19045, False, None, None), (20348, False, False, None),
    (22000, False, False, None), (22631, False, False, None),
    (26100, False, False, 200), (28000, False, False, 200),
])
def test_optional_api_boundaries(build, cursor, border, interval):
    assert capture_options(build) == dict(cursor_capture=cursor,
        draw_border=border, minimum_update_interval=interval)


def install_fake(monkeypatch, build, failures=()):
    engines = []
    class Engine:
        def __init__(self, **options):
            self.options = options
            self.stopped = False
            engines.append(self)
        def event(self, handler):
            setattr(self, handler.__name__, handler)
        def start_free_threaded(self):
            if len(engines) <= len(failures):
                raise RuntimeError(failures[len(engines)-1])
            return self
        def stop(self):
            self.stopped = True
    monkeypatch.setitem(sys.modules, 'windows_capture', SimpleNamespace(WindowsCapture=Engine))
    monkeypatch.setattr(capture, 'windows_build', lambda: build)
    return engines


def test_win10_frame_throttle_and_owned_memory(monkeypatch):
    engines = install_fake(monkeypatch, 19045)
    clock = [10.]
    monkeypatch.setattr(capture.time, 'monotonic', lambda: clock[0])
    cap = capture.Capture(4321)
    assert engines[0].options == dict(window_hwnd=4321, **capture_options(19045))
    pixels = np.full((310, 410, 4), 75, np.uint8)
    frame = SimpleNamespace(frame_buffer=pixels)
    engines[0].on_frame_arrived(frame, None)
    pixels[:] = 120
    assert cap.frame[0, 0, 0] == 75
    clock[0] = 10.1
    engines[0].on_frame_arrived(frame, None)
    assert cap.stamp == 10.
    assert cap.frame[0, 0, 0] == 75
    clock[0] = 10.21
    engines[0].on_frame_arrived(frame, None)
    assert cap.stamp == 10.21 and cap.frame[0, 0, 0] == 120
    monkeypatch.setattr(capture.user32, 'IsIconic', lambda _: False)
    monkeypatch.setattr(capture, 'client_rect', lambda _: (20, 30, 410, 310))
    image, rect, stamp = cap.read()
    assert image.shape == (310, 410, 3) and rect == (20, 30, 410, 310)
    clock[0] = 14.
    with pytest.raises(RuntimeError, match='暂停更新'): cap.read()
    cap.stop(); cap.stop()
    assert engines[0].stopped


def test_win11_keeps_native_settings_and_frame_delivery(monkeypatch):
    engines = install_fake(monkeypatch, 26100)
    cap = capture.Capture(42)
    assert cap.copy_interval == 0
    assert engines[0].options['draw_border'] is False
    assert engines[0].options['minimum_update_interval'] == 200
    engines[0].on_closed()
    with pytest.raises(RuntimeError, match='关闭'): cap.read()
    cap.stop()


@pytest.mark.parametrize('message', [
    'Toggling the capture border is not supported by the Graphics Capture API on this platform.',
    'Setting a minimum update interval is not supported by the Graphics Capture API on this platform.',
    'Toggling cursor capture is not supported by the Graphics Capture API on this platform.',
])
def test_explicit_optional_api_failure_retries_same_window_once(monkeypatch, message):
    engines = install_fake(monkeypatch, 26100, (message,))
    cap = capture.Capture(123)
    assert len(engines) == 2
    assert engines[1].options == dict(window_hwnd=123, cursor_capture=None,
                                     draw_border=None, minimum_update_interval=None)
    assert cap.copy_interval == .2
    cap.stop()


def test_failed_fallback_does_not_loop(monkeypatch):
    message = 'Toggling the capture border is not supported'
    engines = install_fake(monkeypatch, 26100, (message, message))
    with pytest.raises(RuntimeError, match='border'): capture.Capture(123)
    assert len(engines) == 2


@pytest.mark.parametrize('message', ['Access denied', 'DirectX device removed',
    'Invalid window', 'The Graphics Capture API is not supported on this platform.'])
def test_unrelated_errors_are_not_hidden(monkeypatch, message):
    engines = install_fake(monkeypatch, 19045, (message,))
    assert not optional_capture_error(message)
    with pytest.raises(RuntimeError, match=message): capture.Capture(123)
    assert len(engines) == 1


def test_media_prerequisites_are_checked_before_gui_imports():
    called = []
    def missing_media(name):
        called.append(name)
        if name == 'mfplat.dll': raise OSError('not found')
    assert 'Media Feature Pack' in runtime_issue(19045, missing_media)
    assert len(called) == 4
    assert runtime_issue(19045, lambda _: None) is None
    assert runtime_issue(26100, lambda _: None) is None


def test_unsupported_old_build_is_explained_before_loading_dlls():
    def forbidden(_): raise AssertionError('must not load DLLs')
    assert '19041' in runtime_issue(18363, forbidden)
