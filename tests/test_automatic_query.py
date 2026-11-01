from dataclasses import replace
from types import SimpleNamespace, MethodType
import threading
import time

import pytest
from mjs_assistant.app import MainWindow
from mjs_assistant.mini_windows import select_mini_window
from mjs_assistant.recommendations import ModeContext,SelectionSnapshot,RecommendationResult,capability_limits
from mjs_assistant.guide_state import RoundGuideCache,GuideQuery


def snapshot(mode):
    pool=('张仪','如姬','袁术','巴清','金日磾','侯嬴','郭舍人','荀彧','孟姚')
    if mode=='ranked_chuhan_2v2':
        return SelectionSnapshot(ModeContext(mode,'test-game','selection'),
            phase='selection',reference_only=True,image_only=True)
    return SelectionSnapshot(ModeContext(mode,'test-game','selection'),pool,pool,
        phase='selection',reference_only=True,remaining_seconds=None)


@pytest.mark.parametrize('mode',['ranked_chuhan_2v2','peak_chuhan_2v2'])
def test_wait_for_mini_then_automatically_start_once_without_clock(mode,monkeypatch):
    monkeypatch.setattr('mjs_assistant.guide_controller.foreground',lambda hwnd:True)
    idle=[1.0]
    monkeypatch.setattr('mjs_assistant.guide_controller.input_idle_seconds',lambda:idle[0])
    calls=[];ready=[False];status=[]
    provider=SimpleNamespace(busy=False,connection_status=lambda:(ready[0],'等待小程序'),
        start=lambda snap,frame,hwnd:(calls.append((snap,hwnd)) or 'request-1'))
    host=SimpleNamespace(config={'recommendation':{'enabled':True,'automatic':True}},
        auto_attempted=False,provider=provider,snapshot=snapshot(mode),ranked_scene_frames=2,peak_auto_ready=True,game_id='test-game',
        window_box=SimpleNamespace(currentData=lambda:42),rec_status=SimpleNamespace(setText=status.append),
        latest={'stamp':time.monotonic(),'frame':object()},overlay=SimpleNamespace(recommendation=None),
        worker=SimpleNamespace(lock=threading.Lock(),allow_background=False))
    host.request_recommendation=MethodType(MainWindow.request_recommendation,host)
    host.guides_enabled=MethodType(MainWindow.guides_enabled,host)
    host.auto_query_wait=MethodType(MainWindow.auto_query_wait,host)
    host.pool_since=time.monotonic()-2
    host.guide_cache=RoundGuideCache(mode,'test-game')
    provider.active={'query':GuideQuery('selection',mode,'test-game','request-1',(),30 if mode=='peak_chuhan_2v2' else 15)}
    host.recommendation_status=status.append
    MainWindow.maybe_auto_recommend(host)
    assert not calls and not host.auto_attempted  # Missing mini must not consume the attempt.
    ready[0]=True
    idle[0]=.1
    MainWindow.maybe_auto_recommend(host)
    assert len(calls)==1 and host.auto_attempted  # Physical activity no longer blocks auto-start.
    idle[0]=.5
    MainWindow.maybe_auto_recommend(host)
    MainWindow.maybe_auto_recommend(host)
    assert len(calls)==1 and host.auto_attempted and host.request_id=='request-1'
    host.auto_attempted=False
    monkeypatch.setattr('mjs_assistant.guide_controller.foreground',lambda hwnd:False)
    MainWindow.maybe_auto_recommend(host)
    assert len(calls)==1 and not host.auto_attempted
    monkeypatch.setattr('mjs_assistant.guide_controller.foreground',lambda hwnd:True)
    host.config['recommendation']['automatic']=False
    MainWindow.maybe_auto_recommend(host)
    assert len(calls)==1 and not host.auto_attempted


def test_peak_reference_accepts_partial_ban_pool_and_does_not_certify_ownership():
    snap=snapshot('peak_chuhan_2v2')
    assert snap.can_request(True) and not snap.pools_confirmed
    assert any('归属' in text and '未确认' in text for text in capability_limits(snap))
    assert replace(snap,own_pool=snap.own_pool[:2],ally_pool=snap.ally_pool[:2]).can_request(True)
    assert not replace(snap,own_pool=snap.own_pool[:1],ally_pool=snap.ally_pool[:1]).can_request(True)
    assert not replace(snap,reference_only=False).can_request(True)
    assert replace(snap,own_locked='已锁定').can_request(True)
    assert replace(snap,phase='ban').can_request(True)
    assert not replace(snap,context=replace(snap.context,scene='battle')).can_request(True)
    assert not replace(snap,remaining_seconds=17).can_request(True)
    assert snap.fingerprint!=replace(snap,pools_confirmed=True,reference_only=False).fingerprint
    wrong=RecommendationResult('r1',snap.context.game_id,snap.fingerprint)
    assert not wrong.is_current(snap,'r1')  # A reference must never appear as a player assignment.
    assert replace(wrong,reference_only=True).is_current(snap,'r1')


def test_window_discovery_requires_unique_or_explicit_binding():
    assert select_mini_window([]) is None
    assert select_mini_window([10])==10
    assert select_mini_window([10,20]) is None
    assert select_mini_window([10,20],20)==20
    assert select_mini_window([10,20],99) is None
