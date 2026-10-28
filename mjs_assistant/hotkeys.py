"""Global Windows hotkeys; no keyboard interception or suppression."""
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QAbstractNativeEventFilter


def parse_hotkey(value):
    parts=value.upper().replace(' ','').split('+');mod=0x4000
    bits={'ALT':1,'CTRL':2,'SHIFT':4,'WIN':8}
    if len(parts)<2 or len(parts[-1])!=1 or not parts[-1].isalnum():
        raise ValueError('热键格式例如 Ctrl+Alt+R，末键为字母或数字')
    for part in parts[:-1]:
        if part not in bits:raise ValueError('不支持的热键修饰符：'+part)
        mod|=bits[part]
    return mod,ord(parts[-1])


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self,app,bindings):
        super().__init__();self.app=app;self.callbacks={};self.errors=[]
        for index,(label,callback) in enumerate(bindings,0x5100):
            try:
                modifier,key=parse_hotkey(label)
                if not ctypes.windll.user32.RegisterHotKey(None,index,modifier,key):raise ValueError('已被占用')
                self.callbacks[index]=callback
            except ValueError as error:self.errors.append(f'{label}：{error}')
        app.installNativeEventFilter(self)

    def nativeEventFilter(self,event_type,message):
        msg=wintypes.MSG.from_address(int(message))
        if msg.message==0x0312 and msg.wParam in self.callbacks:
            self.callbacks[msg.wParam]();return True,0
        return False,0

    def close(self):
        for index in self.callbacks:ctypes.windll.user32.UnregisterHotKey(None,index)
        self.callbacks.clear();self.app.removeNativeEventFilter(self)
