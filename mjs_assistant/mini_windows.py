"""Read-only capability discovery for the connection settings."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path


def select_mini_window(candidates,bound_hwnd=None):
    if bound_hwnd in candidates:return bound_hwnd
    return candidates[0] if len(candidates)==1 else None


def mini_windows():
    import win32gui,win32process
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
    kernel.CloseHandle.argtypes=[W.HANDLE]
    result=[]
    def visit(hwnd,_):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetWindowText(hwnd)!='名将小助手':return
        if not win32gui.GetClassName(hwnd).startswith('Chrome_WidgetWin') or win32gui.GetWindow(hwnd,4):return
        # Minimized windows report a tiny off-screen rectangle; inspect their
        # restore bounds so an already-open mini program remains connectable.
        a,b,c,d=(win32gui.GetWindowPlacement(hwnd)[4] if win32gui.IsIconic(hwnd)
                 else win32gui.GetWindowRect(hwnd))
        if c-a<250 or d-b<400:return
        cloaked=W.DWORD();C.windll.dwmapi.DwmGetWindowAttribute(hwnd,14,C.byref(cloaked),4)
        if cloaked.value:return
        handle=kernel.OpenProcess(0x1000,False,win32process.GetWindowThreadProcessId(hwnd)[1])
        if not handle:return
        try:
            buffer=C.create_unicode_buffer(32768);size=W.DWORD(32768)
            if kernel.QueryFullProcessImageNameW(handle,0,buffer,C.byref(size)) and Path(buffer.value).name.lower()=='wechatappex.exe':result.append(hwnd)
        finally:kernel.CloseHandle(handle)
    win32gui.EnumWindows(visit,None)
    return result
