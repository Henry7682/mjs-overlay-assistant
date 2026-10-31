"""Source launcher guard, including legacy assistants with relative main.py.

Only enumerates top-level window metadata. Hidden settings windows count; no
foreground changes, game capture, UIA tree reads or process termination.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as wt
import os
from pathlib import PureWindowsPath


def is_assistant_window(title, class_name, executable):
    product = any(title == name or title.startswith(name + ' ')
                  for name in ('名将浮窗助手', '名将统计助手'))
    name = PureWindowsPath(executable).name.lower()
    return (product and class_name.startswith('Qt') and
            (name in {'python.exe', 'pythonw.exe'} or
             (name.startswith('mjsoverlay') and name.endswith('.exe'))))


class WindowsProbe:
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        signatures = (
            (self.kernel.CreateMutexW, [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR], wt.HANDLE),
            (self.kernel.CloseHandle, [wt.HANDLE], wt.BOOL),
            (self.kernel.OpenProcess, [wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
            (self.kernel.QueryFullProcessImageNameW,
             [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)], wt.BOOL),
            (self.user.EnumWindows, [self.callback_type, wt.LPARAM], wt.BOOL),
            (self.user.GetWindowThreadProcessId, [wt.HWND, ctypes.POINTER(wt.DWORD)], wt.DWORD),
            (self.user.GetWindowTextW, [wt.HWND, wt.LPWSTR, ctypes.c_int], ctypes.c_int),
            (self.user.GetClassNameW, [wt.HWND, wt.LPWSTR, ctypes.c_int], ctypes.c_int),
        )
        for function, args, result in signatures:
            function.argtypes, function.restype = args, result

    def acquire(self):
        handle = self.kernel.CreateMutexW(None, False, 'Local\\MjsOverlaySourceStartup_v1')
        error = ctypes.get_last_error()
        if not handle:
            raise ctypes.WinError(error)
        return handle, error == 183  # ERROR_ALREADY_EXISTS

    def close(self, handle):
        self.kernel.CloseHandle(handle)

    def existing(self):
        found, errors = [], []

        @self.callback_type
        def visit(hwnd, _):
            try:
                pid = wt.DWORD()
                self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == os.getpid():
                    return True
                title, kind = ctypes.create_unicode_buffer(1024), ctypes.create_unicode_buffer(256)
                self.user.GetWindowTextW(hwnd, title, len(title))
                self.user.GetClassNameW(hwnd, kind, len(kind))
                if not is_assistant_window(title.value, kind.value, 'python.exe'):
                    return True
                process = self.kernel.OpenProcess(0x1000, False, pid.value)
                if not process:
                    raise RuntimeError(f'Cannot verify assistant window PID {pid.value}; exit it first.')
                try:
                    path, size = ctypes.create_unicode_buffer(32768), wt.DWORD(32768)
                    if not self.kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if is_assistant_window(title.value, kind.value, path.value):
                        found.append(pid.value)
                finally:
                    self.close(process)
            except Exception as error:
                errors.append(error)
            return True

        if not self.user.EnumWindows(visit, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        if errors:
            raise errors[0]
        return sorted(set(found))


@contextmanager
def source_instance_guard(probe=None):
    probe = probe or WindowsProbe()
    handle, occupied = probe.acquire()
    try:
        if occupied or probe.existing():
            raise RuntimeError('Assistant already running; exit it from the tray before testing source. '
                               'No existing instance was changed.')
        yield
    finally:
        probe.close(handle)
