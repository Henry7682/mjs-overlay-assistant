import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from mjs_assistant.guide_panel import GuidePanel


def test_panel_scroll_collapse_no_focus_and_round_reset():
    app=QApplication.instance() or QApplication([])
    panel=GuidePanel()
    try:
        assert panel.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        assert not panel.windowFlags() & Qt.WindowType.WindowTransparentForInput
        panel.set_content('selection','<h3>测试页面</h3>'+''.join(f'<p>攻略 {i}</p>' for i in range(80)))
        panel.show();app.processEvents()
        assert not panel.compact and panel.browser.verticalScrollBar().maximum()>0
        panel.browser.verticalScrollBar().setValue(100)
        assert panel.browser.verticalScrollBar().value()==100
        panel.set_content('battle','<h3>己方组合攻略</h3><p>测试内容</p><h3>敌方组合攻略</h3>')
        assert panel.compact
        QTest.mouseClick(panel.button,Qt.MouseButton.LeftButton);app.processEvents()
        assert not panel.compact
        assert '己方组合攻略' in panel.browser.toPlainText() and '敌方组合攻略' in panel.browser.toPlainText()
        panel.toggle();assert panel.compact
        panel.reset();assert not panel.isVisible() and panel.scene is None
    finally:panel.close()


def test_main_window_constructs_with_source_mapping_and_keeps_config(monkeypatch,tmp_path):
    import mjs_assistant.app as module
    from mjs_assistant.storage import write_json,read_json
    from mjs_assistant.modes import RANKED_CHUHAN,PEAK_CHUHAN
    app=QApplication.instance() or QApplication([])
    config={'schema_version':2,'mode_profiles':{'x':{'calibration':'keep'}},
            'recommendation':{'enabled':False,'hotkeys':{'request':'Ctrl+Alt+P'},'panel_anchor':[.2,.3]}}
    write_json(tmp_path/'settings.json',config)
    monkeypatch.setattr(module,'user_dir',lambda:tmp_path)
    monkeypatch.setattr(module,'windows',lambda:[])
    monkeypatch.setattr(module.RecognitionThread,'start',lambda self:None)
    monkeypatch.setattr(module.MainWindow,'start_data',lambda self,*a,**kw:None)
    monkeypatch.setattr(module,'Hotkeys',lambda *a:Mock(errors=[]))
    window=module.MainWindow()
    try:
        window.mode_box.setCurrentIndex(window.mode_box.findData(RANKED_CHUHAN))
        assert window.mode_box.currentData()==RANKED_CHUHAN and window.store.mode_id==PEAK_CHUHAN
        assert '巅峰' in window.board_label.text() and '共用' in window.rollback_btn.text()
        assert window.guide_cache.mode_id==RANKED_CHUHAN
        assert read_json(tmp_path/'settings.json')==config
        window.open_settings();app.processEvents();assert window.isVisible()
        window.save_guide_position((.25,.4))
        saved=read_json(tmp_path/'settings.json')
        assert saved['recommendation']['hotkeys']['request']=='Ctrl+Alt+P'
        assert saved['mode_profiles']==config['mode_profiles']
    finally:
        window.quitting=True
        for timer in (window.timer,window.scan_timer,window.update_timer):timer.stop()
        window.hotkeys.close();window.tray.hide();window.overlay.close();window.guide_panel.close();window.statistics_button.close();window.close()
