"""Recognize only the bound mini-program's standard file picker.

A leftover modal disables the main window and hides its Chromium document from
UIA. Never interpret that state as an ordinary page-loading delay.
"""
import time


def dialog_state(mini,gui=None):
    """Return (ready pickers, owned native dialogs), including loading modals."""
    if gui is None:
        import win32gui as gui
    found=[];owned=[]
    def visit(hwnd,_):
        try:
            if (gui.IsWindowVisible(hwnd) and gui.GetClassName(hwnd)=='#32770'
                    and gui.GetAncestor(hwnd,3)==mini):
                owned.append(hwnd)
                # Standard Open dialog: Open, Cancel, File name, File type.
                if all(gui.GetDlgItem(hwnd,i) for i in (1,2,1148,1136)):found.append(hwnd)
        except Exception:pass  # A window can disappear during enumeration.
        return True
    gui.EnumWindows(visit,None)
    return found,owned


def image_dialogs(mini,gui=None):
    return dialog_state(mini,gui)[0]


def album_click_allowed(mini,gui=None):
    """Native-only check; never query/click a web page behind a modal."""
    if gui is None:
        import win32gui as gui
    return (not dialog_state(mini,gui)[1] and gui.IsWindowEnabled(mini)
            and gui.GetForegroundWindow()==mini)


def open_image_dialog(mini,open_album,guard,deadline,stage=lambda text:None,
                      gui=None,clock=time.monotonic,sleep=time.sleep):
    """Wait within the request budget, retrying an unacknowledged click once.

    open_album must locate the current album control and recheck
    album_click_allowed immediately before sending input. False means a modal
    appeared during lookup, so no click was sent. No UIA reads while pending.
    """
    if gui is None:
        import win32gui as gui
    attempts=0;last_click=None;last_state=None
    while clock()<deadline:
        guard()
        ready,owned=dialog_state(mini,gui)
        if len(ready)>1:raise RuntimeError('小程序存在多个图片选择框，请关闭后重试')
        if len(ready)==1 and len(owned)==1:return ready[0]
        pending=bool(owned) or not gui.IsWindowEnabled(mini)
        state='文件窗口正在初始化，等待就绪' if pending else '等待文件对话框'
        if state!=last_state:stage(state);last_state=state
        if (not pending and attempts<2 and (last_click is None or clock()-last_click>=4)
                and gui.GetForegroundWindow()==mini):
            stage('打开相册' if attempts==0 else '未检测到文件窗口，重新定位相册（仅重试一次）')
            attempts+=1
            open_album()
            last_click=clock()
            continue
        sleep(min(.08,max(0,deadline-clock())))
    raise TimeoutError('相册上传超时：文件选择框仍未就绪（已用尽本次查询预算）')


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
