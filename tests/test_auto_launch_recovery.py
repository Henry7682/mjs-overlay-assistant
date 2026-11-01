from types import SimpleNamespace as NS, MethodType
from unittest.mock import Mock
import threading
import pytest
from mjs_assistant.app import MainWindow
from mjs_assistant.guide_state import GuideQuery,RoundGuideCache
from mjs_assistant.provider import WeChatMiniProgramProvider
from test_automatic_query import snapshot
from test_manual_review import host as provider_host


def controller(monkeypatch,mode='peak_chuhan_2v2'):
    clock=[100.]
    monkeypatch.setattr('mjs_assistant.guide_controller.time.monotonic',lambda:clock[0])
    monkeypatch.setattr('mjs_assistant.guide_controller.foreground',lambda hwnd:True)
    provider=NS(busy=False,connection_status=lambda:(True,'ready'),_connection_cache=object())
    provider.active={'query':GuideQuery('selection',mode,'test-game','r1',(),40)}
    provider.start=Mock(return_value='r1')
    w=NS(config={'recommendation':{}},provider=provider,game_id='test-game',auto_attempted=False,
        snapshot=snapshot(mode),pool_since=98.,ranked_scene_frames=2,peak_auto_ready=True,
        window_box=NS(currentData=lambda:42),latest={'stamp':100.,'frame':object()},
        worker=NS(lock=threading.Lock(),allow_background=False),overlay=NS(recommendation=None),
        rec_status=NS(setText=Mock()),recommendation_status=Mock(),invalidate_recommendation=Mock(),
        guide_cache=RoundGuideCache(mode,'test-game'))
    for name in ('guides_enabled','maybe_auto_recommend','request_recommendation',
                 'retry_auto_launch','recommendation_launch_failed','cancel_recommendation','auto_query_wait'):
        setattr(w,name,MethodType(getattr(MainWindow,name),w))
    return w,clock


@pytest.mark.parametrize('mode',['ranked_chuhan_2v2','peak_chuhan_2v2'])
def test_start_failure_does_not_permanently_consume_auto_attempt(monkeypatch,mode):
    w,clock=controller(monkeypatch,mode)
    w.provider.start.side_effect=[RuntimeError('请返回游戏后按配阵热键'),'r1']
    w.maybe_auto_recommend()
    assert not w.auto_attempted and w.auto_launch_count==1
    assert w.provider._connection_cache is None
    w.maybe_auto_recommend();assert w.provider.start.call_count==1
    clock[0]+=2.1;w.latest['stamp']=clock[0];w.maybe_auto_recommend()
    assert w.auto_attempted and w.auto_launch_id=='r1'
    w.maybe_auto_recommend();assert w.provider.start.call_count==2


def test_retries_bounded_and_manual_retry_still_available(monkeypatch):
    w,clock=controller(monkeypatch)
    w.provider.start.side_effect=RuntimeError('start failed')
    for _ in range(5):
        w.latest['stamp']=clock[0];w.maybe_auto_recommend();clock[0]+=2.1
    assert w.provider.start.call_count==3 and w.auto_attempted
    w.provider.start.side_effect=None;w.latest['stamp']=clock[0]
    w.request_recommendation();assert w.provider.start.call_count==4 and w.auto_launch_id is None


def test_async_launch_failure_only_rearms_matching_automatic_request(monkeypatch):
    w,clock=controller(monkeypatch);w.maybe_auto_recommend()
    event=dict(request_id='r1',game_id='test-game',reason='切窗失败')
    w.recommendation_launch_failed(dict(event,game_id='old-round'));assert w.auto_attempted
    w.recommendation_launch_failed(dict(event,request_id='old-request'));assert w.auto_attempted
    w.recommendation_launch_failed(event);assert not w.auto_attempted
    w.cancel_recommendation();w.recommendation_launch_failed(event)
    clock[0]+=3;w.latest['stamp']=clock[0];w.maybe_auto_recommend()
    assert w.provider.start.call_count==1  # Explicit cancel remains authoritative.


def test_retry_requires_fresh_frame_foreground_and_enabled_feature(monkeypatch):
    w,clock=controller(monkeypatch)
    w.provider.start.side_effect=RuntimeError('start failed');w.maybe_auto_recommend()
    clock[0]+=5
    w.maybe_auto_recommend();assert w.provider.start.call_count==1  # stale
    w.latest['stamp']=clock[0]
    monkeypatch.setattr('mjs_assistant.guide_controller.foreground',lambda hwnd:False)
    w.maybe_auto_recommend();assert w.provider.start.call_count==1
    monkeypatch.setattr('mjs_assistant.guide_controller.foreground',lambda hwnd:True)
    w.config['recommendation']['automatic']=False
    w.maybe_auto_recommend();assert w.provider.start.call_count==1
    w.config['recommendation']['automatic']=True;w.enabled=False
    w.maybe_auto_recommend();assert w.provider.start.call_count==1


@pytest.mark.parametrize('activated',[False,True])
def test_provider_reports_only_pre_activation_failures(monkeypatch,activated):
    events=([dict(event='activated')] if activated else [])+[dict(status='failed',error='failure')]
    p,state,clock,queue=provider_host(monkeypatch,events)
    p.fail=MethodType(WeChatMiniProgramProvider.fail,p);p.launch_failed=NS(emit=Mock())
    WeChatMiniProgramProvider.poll(p)
    assert p.cancel.call_count==1
    assert p.launch_failed.emit.call_count==(0 if activated else 1)
    if not activated:
        assert p.launch_failed.emit.call_args.args[0]['request_id']=='request1'


def test_manual_request_failure_does_not_trigger_auto_retry(monkeypatch):
    w,clock=controller(monkeypatch);w.request_recommendation()
    w.recommendation_launch_failed(dict(request_id='r1',game_id='test-game',reason='failed'))
    assert w.auto_attempted and w.auto_launch_id is None


def test_new_round_resets_exhausted_launch_budget(monkeypatch):
    w,clock=controller(monkeypatch)
    w.auto_attempted=True;w.auto_launch_count=3;w.auto_retry_at=200;w.auto_launch_id='old'
    w.current_mode=lambda:'peak_chuhan_2v2'
    w.guide_panel=NS(reset=Mock());w.selection_guard=NS(clear=Mock())
    MainWindow.reset_round(w,'new round')
    assert not w.auto_attempted and w.auto_launch_count==0
    assert w.auto_retry_at==0 and w.auto_launch_id is None and w.snapshot is None


@pytest.mark.parametrize('evidence',['partial','input_complete','manual_review'])
def test_progress_or_human_handoff_never_retries_launch(monkeypatch,evidence):
    p,state,clock,queue=provider_host(monkeypatch,[])
    state[evidence]=True;p.launch_failed=NS(emit=Mock())
    WeChatMiniProgramProvider.fail(p,'connection lost')
    p.cancel.assert_called_once();p.launch_failed.emit.assert_not_called()


def test_pre_activation_request_deadline_is_not_retried(monkeypatch):
    p,state,clock,queue=provider_host(monkeypatch,[])
    clock[0]=16;p.launch_failed=NS(emit=Mock())
    WeChatMiniProgramProvider.poll(p)
    p.cancel.assert_called_once();p.launch_failed.emit.assert_not_called()
