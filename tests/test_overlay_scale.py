import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from mjs_assistant.overlay_scale import panel_metrics, logical_scale
from mjs_assistant.guide_panel import GuidePanel
from mjs_assistant.widgets import Overlay
from mjs_assistant.storage import BoardStore
from mjs_assistant.recognition import Detection


@pytest.mark.parametrize('dpi', [1, 1.25, 1.5, 2])
@pytest.mark.parametrize('size', [(2560, 1440), (1920, 1080), (1280, 720)])
def test_physical_size_tracks_client_not_windows_dpi(size, dpi):
    w, h = size
    scale, physical = panel_metrics((100, 200, w, h), dpi)
    assert physical == (round(645*w/2560), round(645*h/1440))
    assert scale*dpi == pytest.approx(1.5*w/2560)
    _, compact = panel_metrics((100, 200, w, h), dpi, True)
    assert compact == (round(114*w/2560), round(63*h/1440))
    assert logical_scale(w/dpi, h/dpi)*dpi == pytest.approx(scale*dpi)


def test_panel_rescale_keeps_content_anchor_and_scroll(monkeypatch):
    app = QApplication.instance() or QApplication([])
    panel = GuidePanel((.2, .3))
    monkeypatch.setattr(panel, 'devicePixelRatioF', lambda: 1.5)
    try:
        html = '<h3>己方组合攻略</h3>' + ''.join(f'<p>组合 {i}：测试说明</p>' for i in range(80))
        panel.set_content('selection', html)
        panel.game_rect = (0, 0, 2560, 1440)
        panel.apply_size();panel.show();app.processEvents()
        assert (panel.width(), panel.height()) == (430, 430)
        assert panel.browser.document().defaultFont().pixelSize() == 12
        scroll = panel.browser.verticalScrollBar()
        scroll.setValue(round(scroll.maximum()*.4))
        panel.game_rect = (300, 200, 1920, 1080)
        panel.apply_size();app.processEvents()
        assert (panel.width(), panel.height()) == (323, 323)
        assert panel.browser.document().defaultFont().pixelSize() == 9
        assert panel.anchor == (.2, .3) and panel._html == html
        assert scroll.value()/scroll.maximum() == pytest.approx(.4, abs=.03)
        # Moving / repeated refresh must not reload the document or reset reading position.
        monkeypatch.setattr(panel.browser, 'setHtml', lambda *_: pytest.fail('document reloaded'))
        monkeypatch.setattr(panel, 'setStyleSheet', lambda *_: pytest.fail('stylesheet reloaded'))
        position = scroll.value()
        panel.apply_size();panel.set_content('selection', html)
        assert scroll.value() == position
        panel.compact = True;panel.apply_size()
        assert (panel.width(), panel.height()) == (57, 31)
        assert panel.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    finally:
        panel.close()


@pytest.mark.parametrize('width,height', [(2560,1440),(1920,1080),(1280,720)])
def test_stats_render_scales_card_and_preserves_normalized_anchor(tmp_path, width, height):
    app = QApplication.instance() or QApplication([])
    overlay = Overlay(BoardStore(tmp_path))
    try:
        overlay.resize(width, height);overlay.frame_size=(width,height)
        overlay.anchors={'0':(.4,.4)}
        overlay.items=[Detection('司马睿','司马睿',(width*.4,height*.3,width*.42,height*.35),.99,'0',True)]
        canvas=QImage(width,height,QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.GlobalColor.transparent)
        painter=QPainter(canvas);overlay.render(painter,QPoint());painter.end()
        s=width/2560
        # Card is 429x69 physical pixels at baseline, with the same normalized anchor.
        x,y=round(width*.4),round(height*.4)
        assert canvas.pixelColor(x+round(200*s),y+round(30*s)).alpha()>0
        assert canvas.pixelColor(x+round(435*s),y+round(30*s)).alpha()==0
        assert canvas.pixelColor(x+round(200*s),y+round(75*s)).alpha()==0
        assert canvas.pixelColor(round(20*s),round(15*s)).alpha()>0
        assert overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput
    finally:
        overlay.close()
