"""Restore settings from tray/second launch without injecting mouse or keys."""
import logging
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication


def show_settings_window(window):
    modal=QApplication.activeModalWidget()
    owner=modal
    while owner is not None and owner is not window:owner=owner.parentWidget()
    target=modal if owner is window else window
    target.showNormal()
    screens=QApplication.screens()
    frame=target.frameGeometry()
    # A disconnected monitor must not leave a visible-but-unreachable window.
    if screens and not any(s.availableGeometry().contains(frame.topLeft()) and
                           s.availableGeometry().intersected(frame).width()>=120 for s in screens):
        area=(window.screen() or QApplication.primaryScreen()).availableGeometry()
        target.move(area.center()-QRect(0,0,target.width(),target.height()).center())
    target.raise_();target.activateWindow()
    handle=target.windowHandle()
    if handle:handle.requestActivate()
    try:
        import win32gui,win32con
        hwnd=int(target.winId())
        win32gui.ShowWindow(hwnd,win32con.SW_RESTORE)
        try:win32gui.SetForegroundWindow(hwnd)
        except Exception:pass  # Windows may refuse focus; the taskbar window remains available.
        logging.info('settings restored: visible=%s foreground=%s hwnd=%s',
                     win32gui.IsWindowVisible(hwnd),win32gui.GetForegroundWindow(),hwnd)
    except ImportError:pass
    except Exception:logging.exception('settings native restore failed')
    return target
