"""Passive physical-input observer. Always forwards events to the next hook."""
import ctypes as C
from ctypes import wintypes as W
import threading
import time


class PhysicalInputWatch:
    def __init__(self,event):
        self.event=event;self.ready=threading.Event();self.thread_id=0;self.error=None
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()
        if not self.ready.wait(1) or self.error:raise RuntimeError('无法启动用户输入检测')

    def _run(self):
        user=C.WinDLL('user32',use_last_error=True);kernel=C.WinDLL('kernel32',use_last_error=True)
        callback=C.WINFUNCTYPE(C.c_ssize_t,C.c_int,W.WPARAM,W.LPARAM)
        user.SetWindowsHookExW.argtypes=[C.c_int,callback,W.HINSTANCE,W.DWORD];user.SetWindowsHookExW.restype=W.HANDLE
        user.CallNextHookEx.argtypes=[W.HANDLE,C.c_int,W.WPARAM,W.LPARAM];user.CallNextHookEx.restype=C.c_ssize_t
        user.UnhookWindowsHookEx.argtypes=[W.HANDLE]
        class Mouse(C.Structure):
            _fields_=[('point',W.POINT),('data',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]
        class Key(C.Structure):
            _fields_=[('vk',W.DWORD),('scan',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]
        started=time.monotonic()
        held={key for key in range(1,256) if user.GetAsyncKeyState(key)&0x8000}
        @callback
        def mouse(code,message,address):
            if code>=0 and not C.cast(address,C.POINTER(Mouse)).contents.flags&1:self.event.set()
            return user.CallNextHookEx(None,code,message,address)
        @callback
        def keyboard(code,message,address):
            if code>=0:
                key=C.cast(address,C.POINTER(Key)).contents
                # Release of the triggering chord is part of that hotkey, not a
                # new user action. Ignore only those releases for the first 0.8s.
                trigger_release=(message in (0x101,0x105) and time.monotonic()-started<.8
                    and key.vk in held)
                if not key.flags&0x10 and not trigger_release:self.event.set()
            return user.CallNextHookEx(None,code,message,address)
        self.thread_id=kernel.GetCurrentThreadId()
        hooks=[user.SetWindowsHookExW(14,mouse,None,0),user.SetWindowsHookExW(13,keyboard,None,0)]
        if not all(hooks):self.error='hook registration failed'
        message=W.MSG();user.PeekMessageW(C.byref(message),None,0,0,0)
        self.ready.set()
        try:
            if not self.error:
                while user.GetMessageW(C.byref(message),None,0,0)>0:
                    user.TranslateMessage(C.byref(message));user.DispatchMessageW(C.byref(message))
        finally:
            for hook in hooks:
                if hook:user.UnhookWindowsHookEx(hook)

    def close(self):
        if self.thread_id and self.thread.is_alive():C.windll.user32.PostThreadMessageW(self.thread_id,0x12,0,0)
        self.thread.join(.2)
        if not self.thread.is_alive():self.thread_id=0
