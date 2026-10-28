from unittest.mock import Mock
import pytest
from mjs_assistant.input_phase import wait_input_target
from mjs_assistant.provider import WeChatMiniProgramProvider
from test_manual_review import host


def test_foreground_loss_waits_and_resumes_once_without_injecting():
    states=iter([False,False,True]);check=Mock();notify=Mock();sleep=Mock()
    assert wait_input_target(lambda:next(states),check,notify,sleep)
    assert [c.args[0] for c in notify.call_args_list]==[True,False]
    assert check.call_count==3 and sleep.call_count==2


@pytest.mark.parametrize('error',[TimeoutError('deadline'),RuntimeError('explicit cancel')])
def test_wait_does_not_swallow_deadline_or_explicit_cancel(error):
    with pytest.raises(type(error)):
        wait_input_target(lambda:False,Mock(side_effect=error),Mock(),Mock())


def test_submit_event_allows_physical_input_and_keeps_results(monkeypatch):
    p,s,clock,q=host(monkeypatch,[dict(event='input_complete'),
        dict(status='success',selected=['孙权','孙策','刘备','孙尚香','终军','杨艳','荀彧','司马睿'],no_result=True)])
    s['physical_stop'].set()
    WeChatMiniProgramProvider.poll(p)
    p.cancel.assert_not_called();p.finished.emit.assert_called_once()


def test_ready_is_not_cancelled_by_earlier_mouse_motion(monkeypatch):
    p,s,clock,q=host(monkeypatch,[dict(ready=True,mini=123)])
    s['physical_stop'].set();s['pipe'].send=Mock()
    monkeypatch.setattr('mjs_assistant.provider.input_tick',lambda:1)
    WeChatMiniProgramProvider.poll(p)
    p.cancel.assert_not_called()
    assert s['pipe'].send.call_args_list[0].args==('go',)
