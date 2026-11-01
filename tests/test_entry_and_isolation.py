import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import cv2
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from mjs_assistant.modes import MINGDAO,RANKED_CHUHAN,PEAK_CHUHAN,PEAK_SHUANGLONG
from mjs_assistant.recognition import Recognizer,Detection
from mjs_assistant.ocr import Ocr,Names,Word
from mjs_assistant.storage import write_json,read_json,ASSETS
from mjs_assistant.entry_detection import detect_entry
from mjs_assistant.provider import WeChatMiniProgramProvider
from mjs_assistant.recommendations import RecommendationResult


def entry_fixture(index):
    frame=np.zeros((1334,2559,3),np.uint8)
    regions=[(0,0,.22,.1)]+([(.655,.22,.826,.285),(.832,.22,.995,.285)] if index<2 else
        [(.305,.145,.505,.215),(.508,.145,.708,.215)])
    for j,(a,b,c,d) in enumerate(regions):
        image=cv2.imdecode(np.fromfile(Path(__file__).parent/f'fixtures/entry-{index}-{j}.png',np.uint8),1)
        frame[int(1334*b):int(1334*d),int(2559*a):int(2559*c)]=image
    return frame


def test_four_real_entry_tabs_at_multiple_sizes_and_unknown_during_fade():
    if not (ASSETS/'models/det.onnx').exists():pytest.skip('Pinned OCR models required')
    r=Recognizer(Ocr(),Names())
    for size in ((2559,1334),(1920,1001),(1280,667)):
        for index,expected in enumerate((RANKED_CHUHAN,MINGDAO,PEAK_CHUHAN,PEAK_SHUANGLONG)):
            frame=cv2.resize(entry_fixture(index),size)
            scene,items,_=r.analyze(frame,mode_id=None)
            assert scene=='entry' and not items and r.entry_mode==expected
            # Manual scene override must not turn entry text into hero candidates.
            assert r.analyze(frame,scene_override='battle',mode_id=MINGDAO)[0]=='entry'
    frame=cv2.cvtColor(cv2.cvtColor(entry_fixture(2),cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    assert detect_entry(frame,[Word('巅峰竞技场',1,(0,0,1,1))],r.read_region)==(True,None)
    assert detect_entry(entry_fixture(0),[Word('武将选择',1,(0,0,1,1))],r.read_region)==(False,None)


@pytest.fixture
def window(monkeypatch,tmp_path):
    import mjs_assistant.app as module
    app=QApplication.instance() or QApplication([])
    write_json(tmp_path/'settings.json',{'schema_version':2,'mode_profiles':{},'recommendation':{'enabled':True,'automatic':True}})
    monkeypatch.setattr(module,'user_dir',lambda:tmp_path)
    monkeypatch.setattr(module,'windows',lambda:[NS(hwnd=123,title='test')])
    monkeypatch.setattr(module.RecognitionThread,'start',lambda self:None)
    monkeypatch.setattr(module.MainWindow,'start_data',lambda self,*a,**k:None)
    monkeypatch.setattr(module,'Hotkeys',lambda *a:Mock(errors=[]))
    monkeypatch.setattr(module,'foreground',lambda hwnd:True)
    monkeypatch.setattr(module,'client_rect',lambda hwnd:(0,0,600,300))
    monkeypatch.setattr(module.QSystemTrayIcon,'show',lambda self:None)
    w=module.MainWindow()
    # The delayed startup callback outlives the fixture's class monkeypatch.
    # Keep this instance offline even if a later Qt test pumps that callback.
    w.start_data=lambda *a,**k:None
    for timer in (w.timer,w.scan_timer,w.update_timer):timer.stop()
    w.overlay.present=Mock();w.guide_panel.present=Mock()
    yield w
    w.quitting=True;w.hotkeys.close();w.tray.hide();w.overlay.close();w.guide_panel.close();w.close()
    from PySide6.QtCore import QCoreApplication,QEvent
    w.overlay.deleteLater();w.guide_panel.deleteLater();w.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


def deliver(w,mode,scene='entry',items=()):
    now=time.monotonic()
    d=dict(generation=w.worker.generation,frame=np.zeros((300,600,3),np.uint8),stamp=now,processed_at=now,seconds=.1,
           scene=scene,phase=scene,items=list(items),in_entry=scene=='entry',entry_mode=mode,layout='default')
    w.receive(d)
    return d


def test_auto_is_a_persistent_choice_across_all_four_entries(window):
    w=window
    for mode in (RANKED_CHUHAN,MINGDAO,PEAK_CHUHAN,PEAK_SHUANGLONG,RANKED_CHUHAN):
        for _ in range(3):deliver(w,mode)
        assert w.mode_box.currentData() is None and w.current_mode()==mode
        assert '自动识别' in w.mode_box.currentText()
        assert w.store.mode_id==(PEAK_CHUHAN if mode==RANKED_CHUHAN else mode)
        assert w.overlay.status_lines and '本地官方榜单' in w.overlay.status_lines[1]
    w.overlay.present.assert_called()
    # One transient tab cannot replace the bound game mode.
    deliver(w,PEAK_SHUANGLONG);assert w.current_mode()==RANKED_CHUHAN
    deliver(w,None);deliver(w,None)
    assert w.current_mode() is None and w.mode_box.currentData() is None


def test_manual_choice_warns_without_switching_and_auto_can_resume(window):
    w=window;w.mode_box.setCurrentIndex(w.mode_box.findData(PEAK_CHUHAN))
    for _ in range(3):d=deliver(w,MINGDAO)
    assert w.current_mode()==PEAK_CHUHAN and w.mode_evidence=='manual'
    assert '入口是明刀暗箭' in '\n'.join(w.status_lines(d))
    w.mode_box.setCurrentIndex(0)
    for _ in range(3):deliver(w,MINGDAO)
    assert w.current_mode()==MINGDAO and w.mode_box.currentData() is None


def test_auto_binding_survives_match_frames_but_not_game_window_change(window,monkeypatch):
    w=window
    for _ in range(3):deliver(w,PEAK_CHUHAN)
    deliver(w,None,'selection');deliver(w,None,'battle')
    assert w.current_mode()==PEAK_CHUHAN and w.worker.mode_id==PEAK_CHUHAN
    monkeypatch.setattr('mjs_assistant.app.windows',lambda:[])
    w.refresh_windows()
    assert w.current_mode() is None and w.worker.mode_id is None
    assert '等待明确入口' in w.mode_status.text() and w.mode_evidence=='unknown'


def test_guide_errors_and_disable_never_hide_local_statistics(window,monkeypatch):
    w=window;w.mode_box.setCurrentIndex(w.mode_box.findData(RANKED_CHUHAN))
    d=Detection('孙权','孙权',(80,80,100,130),1,'roi4',True)
    monkeypatch.setattr(w,'update_selection',Mock(side_effect=RuntimeError('guide flow failed')))
    monkeypatch.setattr(w,'guide_html',Mock(side_effect=RuntimeError('guide render failed')))
    w.overlay.hide=Mock()
    deliver(w,None,'battle',[d])
    assert w.table.rowCount()==1 and w.table.item(0,0).text()=='孙权'
    w.overlay.present.assert_called();w.overlay.hide.assert_not_called()
    assert '本地统计继续' in w.rec_status.text()
    w.set_guides_enabled(False)
    assert not w.guides_enabled() and not w.guide_check.isChecked() and not w.guides_action.isChecked()
    assert read_json(w.folder/'settings.json')['recommendation']['guides_enabled'] is False
    w.overlay.present.reset_mock();w.guide_panel.present.reset_mock()
    deliver(w,None,'battle',[d])
    w.overlay.present.assert_called();w.guide_panel.present.assert_not_called()
    w.provider.start=Mock()
    w.request_recommendation();w.maybe_auto_recommend();w.maybe_enemy_query();w.start_enemy_query()
    w.provider.start.assert_not_called()


def test_turning_guides_off_cancels_only_guides_and_retains_cache(window):
    w=window;w.guide_cache.raw_cards=({'heroes':['孙权','孙策']},)
    w.provider=NS(busy=True,cancel=Mock())
    w.provider.cancel.side_effect=lambda reason:setattr(w.provider,'busy',False)
    worker_generation=w.worker.generation
    w.set_guides_enabled(False)
    w.provider.cancel.assert_called_once()
    assert w.worker.generation==worker_generation and w.enabled
    assert w.guide_cache.raw_cards==({'heroes':['孙权','孙策']},)
    w.provider.busy=False;w.set_guides_enabled(True)


def test_unsupported_client_hides_stale_results_and_retains_round_cache(window):
    w=window
    w.guide_cache.raw_cards=({'heroes':['孙权','孙策']},)
    w.latest={'scene':'selection','items':[]}
    w.provider=NS(busy=True,cancel=Mock())
    w.provider.cancel.side_effect=lambda reason:setattr(w.provider,'busy',False)
    w.overlay.hide=Mock();w.guide_panel.hide=Mock()
    message='当前游戏客户区1920×1200不是16:9，请调整游戏窗口'
    w.receive(dict(generation=w.worker.generation,scene='unknown',items=[],unsupported_aspect=message))
    assert w.latest is None and w.table.rowCount()==0
    w.overlay.hide.assert_called_once();w.guide_panel.hide.assert_called_once()
    w.provider.cancel.assert_called_once_with(message)
    assert w.guide_cache.raw_cards==({'heroes':['孙权','孙策']},)
    # A following valid frame is processed normally; no setting is disabled.
    assert w.enabled
    assert w.guide_cache.raw_cards and w.guides_enabled()


def test_tray_state_and_paused_entry_status_are_explicit(window):
    w=window
    for _ in range(3):deliver(w,MINGDAO)
    assert '运行中' in w.pause_action.text() and '已开启' in w.overlay_action.text()
    w.toggle_pause()
    assert '已暂停' in w.pause_action.text() and '点击开始' in w.pause_action.text()
    assert '已暂停识别' in w.overlay.status_lines[1]
    w.toggle_overlay();assert '已关闭' in w.overlay_action.text()
    w.toggle_overlay();w.toggle_pause()
    assert '运行中' in w.pause_action.text() and '已开启' in w.overlay_action.text()


def test_new_defaults_enable_guides_and_public_query_but_keep_explicit_off(window,monkeypatch):
    w=window;w.config['recommendation']={};w.sync_controls()
    assert w.guides_enabled() and w.guide_check.isChecked()
    from mjs_assistant.recommendation_ui import RecommendationSettings
    monkeypatch.setattr('mjs_assistant.mini_windows.mini_windows',lambda:[])
    dialog=RecommendationSettings({})
    assert dialog.enabled.isChecked() and dialog.guides.isChecked() and dialog.auto.isChecked()
    assert dialog.keys['request'].text()=='Ctrl+Alt+P'
    dialog.save()
    assert all(dialog.result_settings[key] for key in ('enabled','guides_enabled','automatic'))
    old={'enabled':False,'guides_enabled':False,'automatic':False,'hotkeys':{'request':'Ctrl+Alt+R'}}
    dialog=RecommendationSettings(old)
    assert not dialog.enabled.isChecked() and not dialog.guides.isChecked() and not dialog.auto.isChecked()
    assert dialog.keys['request'].text()=='Ctrl+Alt+R'
    dialog.save();assert dialog.result_settings['hotkeys']['request']=='Ctrl+Alt+R'
    assert not any(dialog.result_settings[key] for key in ('enabled','guides_enabled','automatic'))
    w.config['recommendation']=old;w.sync_controls()
    assert not w.guides_enabled()


def test_image_cleanup_failure_cannot_discard_partial_or_block_next_query(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    p=WeChatMiniProgramProvider(tmp_path)
    partial=RecommendationResult('request','round','fingerprint',source_cards=({'heroes':['孙权','孙策']},))
    process=Mock();process.is_alive.return_value=False;process.pid=123
    pipe=Mock();pipe.close.side_effect=OSError('pipe failed')
    p.active=dict(process=process,pipe=pipe,partial=partial)
    p.images.cleanup=Mock(side_effect=PermissionError('file in use'))
    p._return_game=Mock(return_value=True)
    received=[];p.finished.connect(received.append)
    p.cancel('test cancel')
    assert not p.busy and received[0].source_cards==partial.source_cards
    process.close.assert_called_once();p._return_game.assert_called_once()


def test_guide_temp_directory_failure_does_not_prevent_statistics_start(tmp_path,monkeypatch):
    import mjs_assistant.provider as module
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(module,'ManagedImages',Mock(side_effect=PermissionError('denied')))
    p=module.WeChatMiniProgramProvider(tmp_path)
    assert not p.busy and p.images is None
    p.cancel('disabled')  # No failed filesystem dependency on stats-only startup.


def test_malformed_guide_message_releases_busy_and_keeps_valid_partial(tmp_path):
    app=QApplication.instance() or QApplication([])
    p=WeChatMiniProgramProvider(tmp_path)
    partial=RecommendationResult('request','round','fingerprint',source_cards=({'heroes':['孙权','孙策']},))
    pipe=Mock();pipe.poll.return_value=True;pipe.recv.return_value=None
    process=Mock();process.is_alive.return_value=False;process.pid=123
    p.active=dict(process=process,pipe=pipe,partial=partial)
    p._return_game=Mock(return_value=True)
    results=[];p.finished.connect(results.append)
    p.poll()
    assert not p.busy and not p.timer.isActive()
    assert results[0].source_cards==partial.source_cards and not results[0].complete


def test_entry_status_render_stays_in_header_and_remains_click_through(window):
    from PySide6.QtCore import Qt,QPoint
    from PySide6.QtGui import QImage,QPainter
    w=window;w.mode_box.setCurrentIndex(w.mode_box.findData(RANKED_CHUHAN))
    for _ in range(3):deliver(w,PEAK_SHUANGLONG)
    o=w.overlay;o.resize(800,450);o.frame_size=(800,450)
    canvas=QImage(800,450,QImage.Format.Format_ARGB32_Premultiplied);canvas.fill(Qt.GlobalColor.transparent)
    painter=QPainter(canvas);o.render(painter,QPoint());painter.end()
    assert canvas.pixelColor(15,10).alpha()>0 and canvas.pixelColor(700,350).alpha()==0
    assert o.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert o.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
