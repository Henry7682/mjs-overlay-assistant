"""Small interactive guide window; the fullscreen statistics layer stays transparent."""
import ctypes
from ctypes import wintypes
from html import escape
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QTextBrowser,QLayout
from .overlay_scale import panel_metrics


def clamped_position(rect, size, anchor):
    x,y,w,h=rect;pw,ph=size
    return (round(x+max(0,min(max(0,w-pw),anchor[0]*w))),
            round(y+max(0,min(max(0,h-ph),anchor[1]*h))))


def card_html(cards):
    blocks=[]
    for i,card in enumerate(cards,1):
        pair=' ＋ '.join(card['heroes'])
        seats='；'.join(f'{a} {sa}、{b} {sb}' for a,sa,b,sb in card.get('seats',[]))
        rating=card.get('rating')
        blocks.append(f'<p><b>{i}. {escape(pair)}</b><br>原始座次：{escape(seats or "未提供")}'
                      +(f'<br>小程序评级：{escape(str(rating))}' if rating else '')
                      +f'<br>{escape(card.get("reason", "")).replace(chr(10),"<br>")}</p>')
    return ''.join(blocks)


class DragHandle(QPushButton):
    def __init__(self,text,panel,click_toggle=False):
        super().__init__(text,panel);self.panel=panel;self.click_toggle=click_toggle
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._press=None;self._moved=False

    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:
            self._press=e.globalPosition();self._anchor=self.panel.anchor;self._moved=False
        super().mousePressEvent(e)

    def mouseMoveEvent(self,e):
        if self._press is not None:
            delta=e.globalPosition()-self._press
            if delta.manhattanLength()>4:self._moved=True
            if self._moved and self.panel.game_rect:
                _,_,w,h=self.panel.game_rect;dpi=self.panel.devicePixelRatioF()
                self.panel.anchor=(self._anchor[0]+delta.x()*dpi/w,self._anchor[1]+delta.y()*dpi/h)
                self.panel.place()

    def mouseReleaseEvent(self,e):
        moved=self._moved;self._press=None
        super().mouseReleaseEvent(e)
        if moved:self.panel.position_saved.emit(self.panel.anchor)
        elif self.click_toggle:self.panel.toggle()


class GuidePanel(QWidget):
    position_saved=Signal(object)
    retry_enemy=Signal()

    def __init__(self,anchor=(.02,.4)):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|
                         Qt.WindowType.Tool|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle('名将组合攻略')
        self.anchor=tuple(anchor);self.game_rect=None;self.compact=False;self.scene=None;self._html=None
        self.ui_scale=1.;self._style_metrics=None
        self.root=QVBoxLayout(self);self.root.setContentsMargins(5,5,5,5)
        self.root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.button=DragHandle('攻略',self,True);self.root.addWidget(self.button)
        self.body=QWidget(self);self.root.addWidget(self.body)
        layout=QVBoxLayout(self.body);self.body_layout=layout;layout.setContentsMargins(2,2,2,2)
        header=QHBoxLayout();self.header_layout=header;self.title=DragHandle('配阵参考 · 名将小助手  ↔ 拖动',self);header.addWidget(self.title,1)
        minimize=QPushButton('收起');minimize.setFocusPolicy(Qt.FocusPolicy.NoFocus);minimize.clicked.connect(self.toggle);header.addWidget(minimize);layout.addLayout(header)
        self.browser=QTextBrowser();self.browser.setOpenExternalLinks(False);self.browser.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.browser.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction);layout.addWidget(self.browser,1)
        self.retry=QPushButton('重试敌方查询');self.retry.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.retry.clicked.connect(self.retry_enemy);layout.addWidget(self.retry)
        u=ctypes.windll.user32;hwnd=int(self.winId())
        u.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int];u.GetWindowLongPtrW.restype=ctypes.c_ssize_t
        u.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t]
        u.SetWindowLongPtrW(hwnd,-20,u.GetWindowLongPtrW(hwnd,-20)|0x8000000|0x80)
        u.SetWindowDisplayAffinity.argtypes=[wintypes.HWND,wintypes.DWORD];u.SetWindowDisplayAffinity(hwnd,0x11)
        self.apply_size()

    def nativeEvent(self,event_type,message):
        msg=wintypes.MSG.from_address(int(message))
        if msg.message==0x21:return True,3  # WM_MOUSEACTIVATE -> MA_NOACTIVATE, still deliver clicks.
        return super().nativeEvent(event_type,message)

    def apply_size(self):
        self.button.setVisible(self.compact);self.body.setVisible(not self.compact)
        dpi=self.devicePixelRatioF()
        if self.game_rect:
            self.ui_scale,physical=panel_metrics(self.game_rect,dpi,self.compact)
            desired=tuple(max(1,round(v/dpi)) for v in physical)
        else:desired=(76,42) if self.compact else (430,430)
        s=self.ui_scale
        metrics=tuple(max(1,round(v*s)) for v in (12,5,2,6,4,1,10))
        resized=(self.width(),self.height())!=desired
        restyle=metrics!=self._style_metrics
        scroll=self.browser.verticalScrollBar()
        fraction=scroll.value()/max(1,scroll.maximum())
        if restyle:
            self._style_metrics=metrics
            font,pad,inner,gap,radius,border,scrollbar=metrics
            self.setStyleSheet(f'QWidget {{background:#152632;color:#e3ecee;font-family:"Microsoft YaHei UI";font-size:{font}px;}}'
                              f'QPushButton {{background:#274555;border:{border}px solid #597b87;border-radius:{radius}px;padding:{pad}px;}}'
                              'QTextBrowser {border:0;background:#152632;}'
                              f'QScrollBar:vertical {{width:{scrollbar}px;}}')
            text_font=QFont('Microsoft YaHei UI');text_font.setPixelSize(font)
            self.browser.document().setDefaultFont(text_font)
            self.browser.document().setDocumentMargin(inner)
            self.root.setContentsMargins(pad,pad,pad,pad);self.root.setSpacing(gap)
            self.body_layout.setContentsMargins(inner,inner,inner,inner);self.body_layout.setSpacing(gap)
            self.header_layout.setSpacing(gap)
        if resized:self.resize(*desired)
        if restyle or resized:
            self.root.activate();self.body_layout.activate()
            scroll.setValue(round(fraction*scroll.maximum()))

    def toggle(self):
        self.compact=not self.compact;self.apply_size();self.place()

    def set_content(self,scene,html,enemy_retry=False):
        if scene!=self.scene:
            self.compact=scene=='battle';self.scene=scene;self.apply_size()
        self.retry.setVisible(enemy_retry and not self.compact)
        if html!=self._html:
            self._html=html
            scroll=self.browser.verticalScrollBar().value()
            self.browser.setHtml(html);self.browser.verticalScrollBar().setValue(scroll)

    def present(self,rect):
        self.game_rect=rect;self.show();self.place()

    def place(self):
        if not self.game_rect:return
        ratio=self.devicePixelRatioF();rect=self.game_rect
        self.apply_size()
        _,(pw,ph)=panel_metrics(rect,ratio,self.compact)
        x,y=clamped_position(rect,(pw,ph),self.anchor)
        self.anchor=((x-rect[0])/rect[2],(y-rect[1])/rect[3])
        u=ctypes.windll.user32
        u.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        u.SetWindowPos(int(self.winId()),wintypes.HWND(-1),x,y,pw,ph,0x10|0x40)

    def reset(self):
        self.scene=None;self._html=None;self.hide()
