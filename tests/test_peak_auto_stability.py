from types import SimpleNamespace as NS,MethodType
from unittest.mock import Mock
import pytest
from mjs_assistant.guide_state import CandidateStability,GuideQuery
from mjs_assistant.guide_controller import GuideController
from mjs_assistant.recognition import Detection


def test_one_flickering_name_does_not_restart_other_confirmed_names():
    stable=CandidateStability();ctx=('round','selection')
    assert not stable.update(('孙权','刘邦','东方朔'),10,ctx)
    assert not stable.update(('孙权','刘邦','白起'),10.5,ctx)
    assert stable.update(('孙权','刘邦','东方朔'),11,ctx)
    assert '白起' not in stable.since
    assert stable.since['东方朔']==11


@pytest.mark.parametrize('change',['phase','round','gap','empty','clock'])
def test_stale_or_other_stage_evidence_cannot_unlock_auto(change):
    stable=CandidateStability();names=('孙权','刘邦');ctx=('r1','ban')
    stable.update(names,10,ctx)
    assert stable.update(names,11,ctx)
    if change=='empty':
        assert not stable.update((),11.1,ctx)
        assert not stable.update(names,11.2,ctx)
    else:
        when=16 if change=='gap' else 9 if change=='clock' else 11.2
        other=('r1','selection') if change=='phase' else ('r2','ban') if change=='round' else ctx
        assert not stable.update(names,when,other)


def test_one_persistent_name_or_duplicates_are_insufficient():
    stable=CandidateStability();ctx=('r','selection')
    stable.update(('孙权','孙权','刘邦'),10,ctx)
    assert not stable.update(('孙权','孙权','白起'),11.1,ctx)
    assert not stable.update(('孙权','孙权','东方朔'),12.2,ctx)


def test_real_controller_queries_once_despite_alternating_ocr_names(monkeypatch):
    from test_ranked_retention import host
    clock=[10.];mode='peak_chuhan_2v2'
    monkeypatch.setattr('mjs_assistant.guide_controller.time.monotonic',lambda:clock[0])
    monkeypatch.setattr('mjs_assistant.guide_controller.foreground',lambda hwnd:True)
    w=host(mode=mode);w.auto_attempted=False;w.window_box=NS(currentData=lambda:42)
    w.maybe_auto_recommend=MethodType(GuideController.maybe_auto_recommend,w)
    w.provider.connection_status=lambda:(True,'ready')
    def start(snap,frame,hwnd):
        w.provider.active={'query':GuideQuery('selection',mode,'round','r1',snap.own_pool,40)}
        return 'r1'
    w.provider.start=Mock(side_effect=start)
    for index,third in enumerate(('东方朔','白起','东方朔','白起','东方朔')):
        clock[0]=10+index*.5
        names=('孙权','刘邦',third)
        items=[Detection(n,n,(10,10,20,30),.99,'roi'+str(i),True) for i,n in enumerate(names)]
        w.latest=dict(scene='selection',phase='selection',layout='draft9',items=items,
                      stamp=clock[0],frame=object())
        w.update_selection(w.latest)
        if index<2:w.provider.start.assert_not_called()
    w.provider.start.assert_called_once()
    submitted=w.provider.start.call_args.args[0]
    assert submitted.own_pool==('孙权','刘邦','东方朔')  # Full current pool, not only the two stable names.


def test_wait_reason_logs_only_changes(monkeypatch,caplog):
    from test_auto_launch_recovery import controller
    w,clock=controller(monkeypatch);w.peak_auto_ready=False
    with caplog.at_level('INFO'):
        for _ in range(4):w.maybe_auto_recommend()
    assert len([r for r in caplog.records if 'automatic guide waiting' in r.message])==1
    w.provider.start.assert_not_called()


def test_stale_frame_wait_does_not_log_on_every_recognition(monkeypatch,caplog):
    from test_auto_launch_recovery import controller
    w,clock=controller(monkeypatch);w.latest['stamp']=90.
    with caplog.at_level('INFO'):
        for _ in range(4):w.maybe_auto_recommend()
    assert len([r for r in caplog.records if 'automatic guide waiting' in r.message])==1
    w.provider.start.assert_not_called()
