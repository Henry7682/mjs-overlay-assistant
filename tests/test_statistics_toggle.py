import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import Mock
import pytest
from PySide6.QtCore import Qt,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from mjs_assistant.statistics_toggle import StatisticsToggle
from mjs_assistant.storage import read_json
from mjs_assistant.modes import PEAK_CHUHAN
from test_entry_and_isolation import window, deliver


def test_statistics_setting_preserves_recognition_and_guides(window,monkeypatch):
    w=window
    w.mode_box.setCurrentIndex(w.mode_box.findData(PEAK_CHUHAN))
    monkeypatch.setattr(w,'update_selection',lambda d:None)
    w.present_guides=Mock(return_value=True)
    deliver(w,None,'selection')
    w.overlay.present.reset_mock();w.present_guides.reset_mock()
    cache=w.guide_cache;worker=w.worker
    w.statistics_btn.click()
    assert not w.statistics_visible() and not read_json(w.folder/'settings.json')['statistics_visible']
    assert '已隐藏' in w.statistics_btn.text() and w.statistics_button.button.text()=='数据：关'
    w.overlay.present.assert_not_called();w.present_guides.assert_called()
    assert w.enabled and w.worker is worker and w.guide_cache is cache
    w.statistics_button.toggle()
    assert w.statistics_visible() and '已显示' in w.statistics_btn.text()
    w.overlay.present.assert_called()
    w.save_statistics_position((.2,.4))
    assert read_json(w.folder/'settings.json')['statistics_button_anchor']==[.2,.4]


def test_switch_available_without_ocr_and_hidden_off_game(window,monkeypatch):
    w=window;w.latest=None
    w.statistics_button.present=Mock();w.statistics_button.hide=Mock()
    w.tick();w.statistics_button.present.assert_called()
    monkeypatch.setattr('mjs_assistant.app.foreground',lambda hwnd:False)
    w.tick();w.statistics_button.hide.assert_called()
    monkeypatch.setattr('mjs_assistant.app.foreground',lambda hwnd:True)
    w.visible_overlay=False;w.statistics_button.present.reset_mock()
    w.tick();w.statistics_button.present.assert_not_called()


@pytest.mark.parametrize('size',[(1920,1080),(2560,1440)])
def test_small_window_scale_clamp_and_no_focus(size,monkeypatch):
    app=QApplication.instance() or QApplication([]);b=StatisticsToggle((1,1))
    monkeypatch.setattr(b,'devicePixelRatioF',lambda:1.5)
    try:
        b.present((300,200,*size));app.processEvents()
        assert b.width()==round(92*size[0]/2560)
        assert b.height()==round(round(51*size[1]/1440)/1.5)
        assert all(0<x<1 for x in b.anchor)
        assert b.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        assert not b.windowFlags() & Qt.WindowType.WindowTransparentForInput
        assert b.button.focusPolicy()==Qt.FocusPolicy.NoFocus
        b.set_statistics_visible(False)
        assert b.button.text()=='数据：关'
    finally:b.close()


def test_drag_saves_position_without_toggling_and_click_toggles():
    app=QApplication.instance() or QApplication([]);b=StatisticsToggle((.2,.3))
    clicked=Mock();saved=Mock();b.toggled.connect(clicked);b.position_saved.connect(saved)
    b.game_rect=(0,0,1920,1080);b.place=Mock()
    def event(kind,pos,button,buttons):
        e=QMouseEvent(kind,QPointF(10,10),QPointF(*pos),button,buttons,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(b.button,e)
    left=Qt.MouseButton.LeftButton;none=Qt.MouseButton.NoButton
    try:
        event(QEvent.Type.MouseButtonPress,(100,100),left,left)
        event(QEvent.Type.MouseMove,(130,120),none,left)
        event(QEvent.Type.MouseButtonRelease,(130,120),left,none)
        saved.assert_called_once();clicked.assert_not_called()
        event(QEvent.Type.MouseButtonPress,(100,100),left,left)
        event(QEvent.Type.MouseButtonRelease,(100,100),left,none)
        clicked.assert_called_once()
        event(QEvent.Type.MouseButtonRelease,(100,100),Qt.MouseButton.RightButton,none)
        clicked.assert_called_once()
    finally:b.close()
