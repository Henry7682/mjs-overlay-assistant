"""Activate the verified mini-program's neutral header after a cold focus switch.

Foreground HWND alone does not guarantee that WeChat has attached its page
renderer. The blank centre of this mini-program's top header was checked in
live tests; use window-relative, DPI-scaled coordinates, never desktop constants.
"""


def activate_content(hwnd,guard,click,gui=None,dpi=None):
    if gui is None:
        import win32gui as gui
    if dpi is None:
        import ctypes
        from ctypes import wintypes
        get_dpi=ctypes.windll.user32.GetDpiForWindow
        get_dpi.argtypes=[wintypes.HWND];get_dpi.restype=wintypes.UINT
        dpi=get_dpi(hwnd) or 96
    guard()
    if (gui.GetForegroundWindow()!=hwnd or not gui.IsWindowVisible(hwnd)
        or not gui.IsWindowEnabled(hwnd) or gui.IsIconic(hwnd)):
        raise RuntimeError('小程序被弹窗遮挡或已失去前台，停止页面激活')
    if gui.GetWindowText(hwnd)!='名将小助手' or not gui.GetClassName(hwnd).startswith('Chrome_WidgetWin'):
        raise RuntimeError('小程序窗口已变化，停止页面激活')
    left,top,right,bottom=gui.GetWindowRect(hwnd)
    if right-left<250 or bottom-top<400:raise RuntimeError('小程序窗口尺寸不足，停止页面激活')
    point=((left+right)//2,top+max(10,min(round(27*dpi/96),int((bottom-top)*.1))))
    if gui.GetAncestor(gui.WindowFromPoint(point),2)!=hwnd:
        raise RuntimeError('小程序顶部被其他窗口遮挡，停止页面激活')
    guard()
    click(point)  # Caller checks foreground and hit-test again immediately before input.
    return point
