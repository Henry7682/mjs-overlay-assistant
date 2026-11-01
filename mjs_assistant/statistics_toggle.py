"""Interactive statistics visibility button; never takes game keyboard focus."""
import ctypes
import math
from ctypes import wintypes
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout
from .guide_panel import DragHandle, clamped_position
from .overlay_scale import logical_scale


class ToggleHandle(DragHandle):
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)


class StatisticsToggle(QWidget):
    toggled = Signal()
    position_saved = Signal(object)

    def __init__(self, anchor=(.93, .38)):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle('武将数据开关')
        try:
            if len(anchor)!=2 or not all(math.isfinite(float(x)) for x in anchor):raise ValueError()
            self.anchor=tuple(max(0.,min(1.,float(x))) for x in anchor)
        except (ValueError, TypeError):self.anchor=(.93,.38)
        self.game_rect=None;self._style=None
        self.root=QVBoxLayout(self);self.root.setContentsMargins(0,0,0,0)
        self.button=ToggleHandle('',self,True);self.root.addWidget(self.button)
        self.set_statistics_visible(True)
        u=ctypes.windll.user32;hwnd=int(self.winId())
        u.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int];u.GetWindowLongPtrW.restype=ctypes.c_ssize_t
        u.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t]
        u.SetWindowLongPtrW(hwnd,-20,u.GetWindowLongPtrW(hwnd,-20)|0x8000000|0x80)
        u.SetWindowDisplayAffinity.argtypes=[wintypes.HWND,wintypes.DWORD];u.SetWindowDisplayAffinity(hwnd,0x11)

    def nativeEvent(self,event_type,message):
        if wintypes.MSG.from_address(int(message)).message==0x21:return True,3
        return super().nativeEvent(event_type,message)

    def toggle(self):
        self.toggled.emit()

    def set_statistics_visible(self, visible):
        self.button.setText('数据：开' if visible else '数据：关')
        self.button.setToolTip(('点击隐藏武将数据' if visible else '点击显示武将数据')+'；按住拖动，不影响攻略')

    def present(self,rect):
        self.game_rect=rect;self.place()

    def place(self):
        if not self.game_rect:return
        _,_,w,h=self.game_rect
        scale=logical_scale(w,h);dpi=self.devicePixelRatioF()
        pw,ph=max(1,min(w,round(92*scale))),max(1,min(h,round(34*scale)))
        font,pad=max(1,round(12*scale/dpi)),max(1,round(4*scale/dpi))
        style=(font,pad)
        if style!=self._style:
            self._style=style
            self.setStyleSheet(f'QPushButton {{background:#203b49;color:#edf2ed;border:1px solid #88a8b5;'
                              f'border-radius:4px;font-family:"Microsoft YaHei UI";font-size:{font}px;padding:{pad}px;}}'
                              'QPushButton:hover {background:#345768;}')
        self.resize(max(1,round(pw/dpi)),max(1,round(ph/dpi)))
        x,y=clamped_position(self.game_rect,(pw,ph),self.anchor)
        self.anchor=((x-self.game_rect[0])/w,(y-self.game_rect[1])/h)
        self.show()
        u=ctypes.windll.user32
        u.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        u.SetWindowPos(int(self.winId()),wintypes.HWND(-1),x,y,pw,ph,0x10|0x40)
