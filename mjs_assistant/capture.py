from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os
import ntpath
import re
import threading
import time
from pathlib import Path
from functools import lru_cache
from dataclasses import dataclass

import cv2
import numpy as np

user32 = C.WinDLL('user32', use_last_error=True)
kernel32 = C.WinDLL('kernel32', use_last_error=True)
dwmapi = C.WinDLL('dwmapi', use_last_error=True)
user32.GetForegroundWindow.restype = W.HWND
user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel32.OpenProcess.restype = W.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
kernel32.CloseHandle.argtypes = [W.HANDLE]
for name in ('IsWindow', 'IsWindowVisible', 'IsIconic'):
    getattr(user32, name).argtypes = [W.HWND]
user32.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
user32.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
user32.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
dwmapi.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, C.c_void_p, W.DWORD]


def enable_dpi():
    user32.SetProcessDpiAwarenessContext.argtypes = [C.c_void_p]
    user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))


@dataclass
class GameWindow:
    hwnd: int
    title: str
    path: str
    client: str = 'PC 客户端'


def client_kind(path, title, window_class, steam_paths):
    """Steam manifests identify a channel, not an exclusive allowlist."""
    normalized = ntpath.normcase(ntpath.normpath(path))
    if ntpath.basename(normalized) != 'mjs.exe':
        return None
    if normalized in {ntpath.normcase(ntpath.normpath(p)) for p in steam_paths}:
        return 'Steam'
    # The official standalone PC game uses the same executable and Unity HWND.
    # Do not bind a launcher, crash dialog or a browser based on title alone.
    if title.strip() == '名将杀' and window_class == 'UnityWndClass':
        return 'PC 客户端'
    return None


@lru_cache(maxsize=1)
def steam_game_paths():
    """Read Steam's local library manifests; never read or modify game memory."""
    import winreg
    roots=set()
    for hive,key,field in [(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam','SteamPath'),
                           (winreg.HKEY_LOCAL_MACHINE,r'Software\WOW6432Node\Valve\Steam','InstallPath')]:
        try:
            with winreg.OpenKey(hive,key) as handle: roots.add(Path(winreg.QueryValueEx(handle,field)[0]))
        except OSError:pass
    libraries=set(roots)
    for root in roots:
        try:
            text=(root/'steamapps/libraryfolders.vdf').read_text('utf8')
            libraries.update(Path(p.replace('\\\\','\\')) for p in re.findall(r'"path"\s*"([^"]+)"',text))
        except OSError:pass
    paths=set()
    for library in libraries:
        try:
            manifest=(library/'steamapps/appmanifest_4190600.acf').read_text('utf8')
            folder=re.search(r'"installdir"\s*"([^"]+)"',manifest)
            if folder:paths.add(os.path.normcase(str((library/'steamapps/common'/folder[1]/'mjs.exe').resolve())))
        except OSError:pass
    return paths


def windows():
    result = []
    known = steam_game_paths()
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    @callback_type
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
        process = kernel32.OpenProcess(0x1000, False, pid.value)
        if not process:
            return True
        try:
            path, size = C.create_unicode_buffer(32768), W.DWORD(32768)
            if kernel32.QueryFullProcessImageNameW(process, 0, path, C.byref(size)) and os.path.basename(path.value).lower() == 'mjs.exe':
                title = C.create_unicode_buffer(512)
                user32.GetWindowTextW(W.HWND(hwnd), title, 512)
                window_class = C.create_unicode_buffer(256)
                user32.GetClassNameW(W.HWND(hwnd), window_class, 256)
                client = client_kind(path.value, title.value, window_class.value, known)
                if client:
                    result.append(GameWindow(int(hwnd), title.value, path.value, client))
        finally:
            kernel32.CloseHandle(process)
        return True

    user32.EnumWindows(callback, 0)
    return result


def client_rect(hwnd):
    rect, point = W.RECT(), W.POINT()
    if not user32.IsWindow(hwnd) or not user32.GetClientRect(hwnd, C.byref(rect)) or not user32.ClientToScreen(hwnd, C.byref(point)):
        raise RuntimeError('游戏窗口已关闭')
    return point.x, point.y, rect.right, rect.bottom


def foreground(hwnd):
    return user32.GetForegroundWindow() == hwnd and not user32.IsIconic(hwnd)


class Capture:
    def __init__(self, hwnd):
        from windows_capture import WindowsCapture
        self.hwnd, self.lock = hwnd, threading.Lock()
        self.frame, self.stamp, self.error = None, 0., ''
        self.engine = WindowsCapture(window_hwnd=hwnd, cursor_capture=False, draw_border=False, minimum_update_interval=200)

        @self.engine.event
        def on_frame_arrived(frame, control):
            with self.lock:
                self.frame = np.ascontiguousarray(frame.frame_buffer[:, :, :3]).copy()
                self.stamp = time.monotonic()

        @self.engine.event
        def on_closed():
            self.error = '游戏窗口已关闭'

        self.control = self.engine.start_free_threaded()

    def stop(self):
        if self.control:
            self.control.stop()
            self.control = None

    def read(self):
        if self.error:
            raise RuntimeError(self.error)
        if user32.IsIconic(self.hwnd):
            raise RuntimeError('请还原游戏窗口')
        with self.lock:
            if self.frame is None:
                raise RuntimeError('正在等待游戏截图')
            frame, stamp = self.frame.copy(), self.stamp
        if time.monotonic() - stamp > 3:
            raise RuntimeError('游戏画面暂停更新，识别已暂停')
        x, y, w, h = client_rect(self.hwnd)
        fh, fw = frame.shape[:2]
        if w < 400 or h < 300:
            raise RuntimeError('游戏窗口过小')
        if abs(fw - w) <= 2 and abs(fh - h) <= 2:
            crop = frame[:h, :w]
        else:
            bounds = W.RECT()
            hr = dwmapi.DwmGetWindowAttribute(self.hwnd, 9, C.byref(bounds), C.sizeof(bounds))
            if hr != 0:
                user32.GetWindowRect(self.hwnd, C.byref(bounds))
            if abs(fw - (bounds.right - bounds.left)) > 32 or abs(fh - (bounds.bottom - bounds.top)) > 32:
                raise RuntimeError('截图尺寸与目标窗口不符，请重新连接')
            dx, dy = max(0, x - bounds.left), max(0, y - bounds.top)
            if dx + w > fw + 2 or dy + h > fh + 2:
                raise RuntimeError('客户区坐标不匹配，请切换窗口化')
            crop = frame[dy:dy+h, dx:dx+w]
        if crop.size == 0 or float(np.mean(crop)) < 2:
            raise RuntimeError('截图为黑屏，请切换窗口化／无边框')
        return np.ascontiguousarray(crop), (x, y, w, h), stamp
