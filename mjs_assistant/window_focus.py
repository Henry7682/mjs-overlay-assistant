"""Verified foreground activation using a visible, assistant-owned bridge.

Never clicks the game or sends Alt/Tab. Does not change foreground-lock settings
or attach input queues. A process that receives input can request foreground
activation (SetForegroundWindow documentation); Windows can still refuse it.
"""
from dataclasses import dataclass
import os
import time
import uuid
import logging


@dataclass(frozen=True)
class FocusResult:
    ok: bool
    method: str
    reason: str=''


class NativeFocus:
    def __init__(self):
        import win32api,win32gui,win32con,win32process
        self.api=win32api;self.gui=win32gui;self.con=win32con;self.process=win32process
        self.bridge_classes={}

    def foreground(self):return self.gui.GetForegroundWindow()
    def exists(self,hwnd):return self.gui.IsWindow(hwnd)
    def related(self,hwnd,owner):return hwnd==owner or (bool(hwnd) and self.gui.GetAncestor(hwnd,3)==owner)
    def pump(self):self.gui.PumpWaitingMessages()
    def request(self,hwnd):
        try:
            if self.gui.IsIconic(hwnd):self.gui.ShowWindow(hwnd,self.con.SW_RESTORE)
            self.gui.SetForegroundWindow(hwnd)
        except Exception:pass  # Actual foreground verification is authoritative.

    def create_bridge(self,source):
        name='MjsFocusBridge-'+uuid.uuid4().hex
        wc=self.gui.WNDCLASS();wc.hInstance=self.api.GetModuleHandle(None)
        wc.lpszClassName=name;wc.lpfnWndProc=self.gui.DefWindowProc
        wc.hbrBackground=self.con.COLOR_WINDOW+1
        self.gui.RegisterClass(wc)
        monitor=self.api.GetMonitorInfo(self.api.MonitorFromWindow(source,2))['Work']
        x=monitor[0]+max(0,(monitor[2]-monitor[0]-320)//2);y=monitor[1]+32
        hwnd=self.gui.CreateWindowEx(self.con.WS_EX_TOPMOST|self.con.WS_EX_TOOLWINDOW,name,
            '名将浮窗助手 · 正在切换配阵窗口',self.con.WS_POPUP|self.con.WS_CAPTION,
            x,y,320,72,0,0,wc.hInstance,None)
        self.bridge_classes[hwnd]=(name,wc.hInstance)
        self.gui.CreateWindow('STATIC','正在切换，请暂勿操作鼠标键盘',
            self.con.WS_CHILD|self.con.WS_VISIBLE|self.con.SS_CENTER,4,10,310,24,hwnd,0,wc.hInstance,None)
        self.gui.SetWindowPos(hwnd,self.con.HWND_TOPMOST,x,y,320,72,
            self.con.SWP_SHOWWINDOW|self.con.SWP_NOACTIVATE)
        self.gui.UpdateWindow(hwnd);self.pump()
        return hwnd

    def click_bridge(self,hwnd,stopped):
        rect=self.gui.GetClientRect(hwnd)
        point=self.gui.ClientToScreen(hwnd,((rect[2]-rect[0])//2,(rect[3]-rect[1])//2))
        old=self.api.GetCursorPos()
        def owns_point():
            hit=self.gui.WindowFromPoint(point)
            valid=(self.gui.GetAncestor(hit,2)==hwnd
                and self.process.GetWindowThreadProcessId(hwnd)[1]==os.getpid())
            logging.info('focus bridge hit=%s root=%s bridge=%s valid=%s point=%s cursor=%s foreground=%s',
                         hit,self.gui.GetAncestor(hit,2),hwnd,valid,point,self.api.GetCursorPos(),self.foreground())
            return valid
        if stopped() or not owns_point():return False
        # Injected moves are ignored by the passive physical-input watcher.
        until=time.monotonic()+.2
        while True:
            self.move(point);time.sleep(.025);self.pump()
            if stopped() or not owns_point():return False
            if self.api.GetCursorPos()==point:break
            if time.monotonic()>=until:return False
        self.api.mouse_event(self.con.MOUSEEVENTF_LEFTDOWN,0,0,0,0)
        self.api.mouse_event(self.con.MOUSEEVENTF_LEFTUP,0,0,0,0)
        until=time.monotonic()+.15
        while time.monotonic()<until and not stopped():
            self.pump()
            if self.foreground()==hwnd:break
            time.sleep(.01)
        if not stopped() and self.api.GetCursorPos()==point:self.move(old)
        logging.info('focus bridge after click: foreground=%s bridge=%s stopped=%s',self.foreground(),hwnd,stopped())
        return self.foreground()==hwnd and not stopped()

    def move(self,point):
        left=self.api.GetSystemMetrics(76);top=self.api.GetSystemMetrics(77)
        width=self.api.GetSystemMetrics(78);height=self.api.GetSystemMetrics(79)
        self.api.mouse_event(0xC001,int((point[0]-left)*65535/max(1,width-1)),
            int((point[1]-top)*65535/max(1,height-1)),0,0)

    def destroy(self,hwnd):
        try:
            if self.exists(hwnd):self.gui.DestroyWindow(hwnd)
        finally:
            value=self.bridge_classes.pop(hwnd,None)
            if value:self.gui.UnregisterClass(*value)


def activate_window(target,source,stopped=lambda:False,timeout=.9,api=None):
    api=api or NativeFocus();end=time.monotonic()+timeout;bridge=None;transitioning=False
    def permitted():
        fg=api.foreground()
        # Windows briefly reports HWND 0 while changing activation. This is
        # neither a verified destination nor evidence of a user-selected app.
        return not stopped() and ((transitioning and not fg) or fg==target
            or (bridge and fg==bridge) or api.related(fg,source))
    def wait_for(hwnd,seconds):
        until=min(end,time.monotonic()+seconds)
        while time.monotonic()<until:
            api.pump()
            if not permitted():return False
            if api.foreground()==hwnd:return True
            time.sleep(.01)
        return not stopped() and api.foreground()==hwnd
    try:
        if stopped() or not api.exists(target):return FocusResult(False,'none','用户介入或目标窗口已关闭')
        if api.foreground()==target:return FocusResult(True,'already')
        if not permitted():return FocusResult(False,'none','前台已切至其他应用，停止切窗')
        transitioning=True
        api.request(target)
        if wait_for(target,.12):return FocusResult(True,'direct')
        if not permitted() or time.monotonic()>=end:return FocusResult(False,'direct','前台状态已改变')
        bridge=api.create_bridge(source)
        if not permitted():return FocusResult(False,'bridge','用户已切换应用')
        if api.foreground()!=bridge and not api.click_bridge(bridge,lambda:not permitted()):
            return FocusResult(False,'bridge','助手切换提示窗未能激活')
        if stopped():return FocusResult(False,'bridge','用户输入，切窗已取消')
        api.request(target)
        if wait_for(target,.4):return FocusResult(True,'bridge')
        return FocusResult(False,'bridge','目标窗口仍未成为前台，未继续输入')
    except Exception as error:return FocusResult(False,'bridge' if bridge else 'direct',str(error))
    finally:
        if bridge:
            try:api.destroy(bridge)
            except Exception:pass
