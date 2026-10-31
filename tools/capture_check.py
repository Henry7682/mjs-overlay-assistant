"""Explicit WGC check of an assistant-owned animated window; no game/input/images."""
import json
import time
from pathlib import Path


def run(output):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QLabel
    from mjs_assistant.capture import Capture, enable_dpi
    from mjs_assistant.windows_compat import windows_build
    from mjs_assistant.version import VERSION
    enable_dpi()
    app = QApplication.instance() or QApplication([])
    window = QLabel('名将浮窗助手 · 截图兼容检查\n只检测本窗口，约 5 秒后自动关闭')
    window.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.resize(640, 360)
    window.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.setStyleSheet('background:#285575;color:white;font-size:18px')
    window.show(); app.processEvents()
    result = dict(version=VERSION, actual_build=windows_build(), target='self-owned-window',
                  saved_images=False, ok=False)
    cap = None
    try:
        cap = Capture(int(window.winId()))
        result['capture_options'] = cap.options
        stamps = []; began = time.monotonic(); tick = -1
        while time.monotonic() - began < 8:
            current = int((time.monotonic() - began) * 5)
            if current != tick:
                tick = current
                window.setStyleSheet(f'background:rgb({40 + tick % 2 * 35},85,117);color:white;font-size:18px')
            app.processEvents()
            try:
                frame, rect, stamp = cap.read()
                if not stamps or stamp != stamps[-1]: stamps.append(stamp)
                result['client_size'] = list(rect[2:])
                result['frame_size'] = [frame.shape[1], frame.shape[0]]
            except RuntimeError as error:
                if '正在等待游戏截图' not in str(error): raise
            if len(stamps) >= 8: break
            time.sleep(.02)
        result['frames'] = len(stamps)
        result['seconds'] = round(time.monotonic() - began, 3)
        result['ok'] = len(stamps) >= 8
        if not result['ok']: result['error'] = '未取得足够连续帧'
    except Exception as error:
        result['error'] = str(error)
    finally:
        if cap: cap.stop()
        window.close(); app.processEvents()
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    return 0 if result['ok'] else 1
