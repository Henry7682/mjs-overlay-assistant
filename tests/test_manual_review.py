from collections import deque
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import Mock
import threading
from mjs_assistant.provider import WeChatMiniProgramProvider
from mjs_assistant.recommendations import ModeContext,SelectionSnapshot


def host(monkeypatch,messages):
    clock=[10.];monkeypatch.setattr('mjs_assistant.provider.time.monotonic',lambda:clock[0])
    queue=deque(messages)
    snap=SelectionSnapshot(ModeContext('ranked_chuhan_2v2','round1','selection'),
        phase='selection',reference_only=True,image_only=True)
    state=dict(began=0,physical_stop=threading.Event(),watch=NS(close=Mock()),
        pipe=NS(poll=lambda:bool(queue),recv=queue.popleft),process=NS(is_alive=lambda:True),
        id='request1',snapshot=snap)
    p=NS(active=state,images=NS(cleanup=Mock()),status=NS(emit=Mock()),
         finished=NS(emit=Mock()),cancel=Mock())
    p._finish=lambda:setattr(p,'active',None)
    p.cleanup_images=lambda:WeChatMiniProgramProvider.cleanup_images(p)
    return p,state,clock,queue


def test_manual_confirmation_keeps_request_and_allows_human_input(monkeypatch):
    p,s,clock,q=host(monkeypatch,[{'event':'input_complete'},{'event':'manual_review'}])
    s['physical_stop'].set()
    WeChatMiniProgramProvider.poll(p)
    assert p.active is s and s['manual_review'] and s['input_complete']
    s['watch'].close.assert_called_once();p.images.cleanup.assert_called_once()
    clock[0]=25
    WeChatMiniProgramProvider.poll(p)
    p.cancel.assert_not_called()  # Automated 15s deadline no longer owns a human handoff.
    q.append({'status':'success','manually_reviewed':True,'no_result':True,
              'selected':['孙权','孙策','刘备','孙尚香','终军','杨艳','荀彧','司马睿']})
    WeChatMiniProgramProvider.poll(p)
    result=p.finished.emit.call_args.args[0]
    assert result.is_current(s['snapshot'],'request1')
    assert not result.is_current(replace(s['snapshot'],visual_revision='changed'),'request1')
    assert '人工复核完成' in p.status.emit.call_args.args[0]


def test_handoff_cannot_rescue_an_automatic_request_already_over_deadline(monkeypatch):
    p,s,clock,q=host(monkeypatch,[{'event':'manual_review'}]);clock[0]=16
    WeChatMiniProgramProvider.poll(p)
    assert not s.get('manual_review') and p.cancel.called


def test_manual_wait_is_bounded(monkeypatch):
    p,s,clock,q=host(monkeypatch,[{'event':'input_complete'},{'event':'manual_review'}])
    WeChatMiniProgramProvider.poll(p);clock[0]=101
    WeChatMiniProgramProvider.poll(p)
    assert '等待人工复核已结束' in p.cancel.call_args.args[0]


def test_physical_input_before_upload_does_not_abort(monkeypatch):
    p,s,clock,q=host(monkeypatch,[]);s['physical_stop'].set()
    WeChatMiniProgramProvider.poll(p)
    p.cancel.assert_not_called()
    clock[0]=16
    WeChatMiniProgramProvider.poll(p)
    assert '时限' in p.cancel.call_args.args[0]


def test_confirmation_with_incomplete_candidates_cannot_publish(monkeypatch):
    p,s,clock,q=host(monkeypatch,[{'event':'input_complete'},{'event':'manual_review'},
        {'status':'success','selected':['孙权'],'no_result':True,'manually_reviewed':True}])
    WeChatMiniProgramProvider.poll(p)
    p.finished.emit.assert_not_called();assert p.cancel.called


def test_late_local_names_update_evidence_without_changing_request_identity(monkeypatch):
    p,s,clock,q=host(monkeypatch,[]);s['mini']=456;s['pipe'].send=Mock()
    snapshot=replace(s['snapshot'],own_pool=('孙权',),ally_pool=('孙权',))
    original_fingerprint=s['snapshot'].fingerprint
    WeChatMiniProgramProvider.update_evidence(p,snapshot)
    assert s['snapshot'].fingerprint==original_fingerprint
    s['pipe'].send.assert_called_once_with({'observed':['孙权']})
    WeChatMiniProgramProvider.update_evidence(p,replace(snapshot,visual_revision='different'))
    s['pipe'].send.assert_called_once()


def test_evidence_before_ready_does_not_overtake_go_handshake(monkeypatch):
    p,s,clock,q=host(monkeypatch,[]);s['pipe'].send=Mock()
    WeChatMiniProgramProvider.update_evidence(p,replace(s['snapshot'],own_pool=('孙权',)))
    assert '孙权' in s['snapshot'].own_pool
    s['pipe'].send.assert_not_called()
