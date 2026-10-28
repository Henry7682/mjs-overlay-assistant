from types import SimpleNamespace
import pytest
from mjs_assistant.uia_wait import wait_visible


def element(visible):
    return SimpleNamespace(CurrentBoundingRectangle=SimpleNamespace(left=0,top=0,right=200,bottom=400),
                           CurrentIsOffscreen=not visible)


def test_page_becoming_visible_after_one_second():
    now=[0.0]
    def sleep(seconds):now[0]+=seconds
    def fetch():return element(now[0]>=1.6) if now[0]>.3 else None
    result,state=wait_visible(fetch,lambda:None,15,3,lambda:now[0],sleep)
    assert result and not result.CurrentIsOffscreen and 1.6<=now[0]<1.7


def test_readiness_cannot_extend_global_deadline():
    now=[14.0]
    def sleep(seconds):now[0]+=seconds
    result,state=wait_visible(lambda:None,lambda:None,14.5,3,lambda:now[0],sleep)
    assert result is None and state=='not_found' and now[0]==14.5


def test_user_intervention_aborts_wait():
    def stop():raise RuntimeError('user input')
    with pytest.raises(RuntimeError,match='user input'):
        wait_visible(lambda:None,stop,999999,3)
