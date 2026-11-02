"""Recognize only the bound mini-program's standard file picker.

A leftover modal disables the main window and hides its Chromium document from
UIA. Never interpret that state as an ordinary page-loading delay.
"""
import time


def open_button(dialog):
    """Locate IDOK by role/ID, independent of caption, DPI and child depth."""
    buttons=[button for button in dialog.descendants(class_name='Button')
             if button.control_id()==1 and button.is_visible() and button.is_enabled()]
    if len(buttons)!=1:
        raise RuntimeError('图片选择框已打开，但无法唯一定位打开按钮')
    return buttons[0].handle


def filename_edits(dialog):
    """Native file-name Edit may be several levels below its ComboBoxEx host.

    Never pick the shell Search edit merely because it is visible.
    """
    found=[]
    for edit in dialog.descendants(class_name='Edit'):
        if not edit.is_visible() or not edit.is_enabled():continue
        current=edit;seen=set()
        for _ in range(12):
            if current.handle==dialog.handle or current.handle in seen:break
            seen.add(current.handle)
            if current.control_id() in (1148,1152):
                found.append(edit);break
            current=current.parent()
            if current is None:break
    return found


def validate_image_path(path):
    from pathlib import Path
    if path is None:raise RuntimeError('上传图片路径为空，请重新配阵')
    target=Path(path).resolve()
    if not target.is_file() or target.stat().st_size==0:
        raise RuntimeError('临时游戏截图不存在或为空，请检查数据目录权限后重试')
    if target.suffix.lower()!='.png':raise RuntimeError('上传文件不是游戏PNG截图')
    return str(target)


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
                # pywin32 raises error 1421 for a missing control; it does not
                # return zero like raw Win32 / our old test double. 1148 and
                # 1152 are ALTERNATIVE filename hosts, never both required.
                ids=set()
                for ident in (1,2,1148,1152):
                    try:
                        if gui.GetDlgItem(hwnd,ident):ids.add(ident)
                    except Exception:pass
                if hasattr(gui,'EnumChildWindows'):
                    def collect(child,_):
                        try:ids.add(gui.GetDlgCtrlID(child))
                        except Exception:pass
                        return True
                    gui.EnumChildWindows(hwnd,collect,None)
                if {1,2}<=ids and ids.intersection((1148,1152)):found.append(hwnd)
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
    from .album_location import AlbumNotReady
    attempts=0;last_click=None;last_state=None;location_error=None
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
            try:
                open_album()
                location_error=None
            except AlbumNotReady as error:
                location_error=str(error)
                if attempts>=2:raise
                stage(location_error+'；在剩余预算内重试')
            # No input was sent on a localization failure: do not spend four
            # seconds waiting for a dialog that cannot have been opened.
            last_click=clock()-(3.75 if location_error else 0)
            continue
        sleep(min(.08,max(0,deadline-clock())))
    if location_error:raise AlbumNotReady(location_error)
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
