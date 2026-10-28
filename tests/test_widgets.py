import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter
from PySide6.QtCore import Qt
from mjs_assistant.widgets import Overlay
from mjs_assistant.storage import BoardStore
from mjs_assistant.recognition import Detection


def test_overlay_transparent_and_no_focus(tmp_path):
    app=QApplication.instance() or QApplication([])
    from mjs_assistant.app import STYLE
    app.setStyleSheet(STYLE)
    overlay=Overlay(BoardStore(tmp_path));overlay.resize(1280,720);overlay.frame_size=(1920,1080)
    overlay.items=[Detection('司马睿','司马睿',(500,100,540,180),.99,'0',True)]
    canvas=QImage(1280,720,QImage.Format.Format_ARGB32_Premultiplied);canvas.fill(Qt.GlobalColor.transparent)
    painter=QPainter(canvas);overlay.render(painter, __import__('PySide6.QtCore',fromlist=['QPoint']).QPoint());painter.end()
    assert canvas.pixelColor(900,500).alpha()==0
    assert canvas.pixelColor(15,10).alpha()>0
    assert overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    overlay.close()
