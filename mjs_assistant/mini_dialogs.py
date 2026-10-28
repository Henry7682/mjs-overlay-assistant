"""Recognize only the bound mini-program's standard file picker.

A leftover modal disables the main window and hides its Chromium document from
UIA. Never interpret that state as an ordinary page-loading delay.
"""
import time


def image_dialogs(mini,gui=None):
    if gui is None:
        import win32gui as gui
    found=[]
    def visit(hwnd,_):
        if (gui.IsWindowVisible(hwnd) and gui.GetClassName(hwnd)=='#32770'
                and gui.GetAncestor(hwnd,3)==mini):
            try:
                # Standard Open dialog: Open, Cancel, File name, File type.
                if all(gui.GetDlgItem(hwnd,i) for i in (1,2,1148,1136)):found.append(hwnd)
            except Exception:pass
        return True
    gui.EnumWindows(visit,None)
    return found


def close_image_dialogs(mini,guard,deadline,gui=None,clock=time.monotonic,sleep=time.sleep):
    if gui is None:
        import win32gui as gui
    guard();dialogs=image_dialogs(mini,gui)
    if len(dialogs)>1:raise RuntimeError('小程序存在多个图片选择框，请关闭后重试')
    for hwnd in dialogs:
        guard()
        # Cancel discards only an unsubmitted file selection, never an image.
        gui.PostMessage(hwnd,0x111,2,0)  # WM_COMMAND / IDCANCEL
    until=min(deadline,clock()+.8)
    while image_dialogs(mini,gui):
        guard()
        if clock()>=until:raise RuntimeError('上次图片选择框未能关闭，请在小程序取消后重试')
        sleep(.04)
    return bool(dialogs)
