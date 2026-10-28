import pytest
from mjs_assistant.recognition import puppet_dialog_visible,Stabilizer,Detection
from mjs_assistant.ocr import Word
from mjs_assistant.app import MainWindow
from test_ranked_retention import host,data


def word(text,confidence=1):return Word(text,confidence,(0,0,20,20))


def test_modal_needs_title_and_cancel_at_separately_checked_positions():
    assert puppet_dialog_visible([word('武将选择')],[word('取消')])
    assert not puppet_dialog_visible([word('武将选择')],[])
    assert not puppet_dialog_visible([],[word('取消')])
    assert not puppet_dialog_visible([word('武将选择',.6)],[word('取消')])


@pytest.mark.parametrize('busy',[False,True])
def test_puppet_names_never_replace_eight_card_pool_or_trigger_upload(busy):
    window=host(busy=busy);old=window.snapshot
    popup=data();popup['phase']='puppet'
    popup['items']=[Detection('虞姬','虞姬',(10,10,20,30),1,'puppet0',True)]
    MainWindow.update_selection(window,popup)
    assert window.snapshot.own_pool==old.own_pool and window.snapshot.phase=='puppet'
    assert not window.snapshot.can_request(True)
    window.provider.cancel.assert_not_called();window.provider.update_evidence.assert_not_called()
    window.maybe_auto_recommend.assert_not_called();window.selection_guard.update.assert_not_called()


def test_popup_slots_clear_immediately_when_closed_and_cannot_inherit_outer_confirmation():
    s=Stabilizer();outer=[Detection('刘备','刘备',(10,10,20,30),1,'roi0')]
    popup=[Detection('刘备','刘备',(50,50,60,80),1,'puppet0')]
    s.update('selection',outer,now=1);s.update('selection',outer,now=1.5)
    assert not s.update('selection',popup,now=2)[0].confirmed
    assert s.update('selection',popup,now=2.5)[0].confirmed
    returned=s.update('selection',outer,now=3)
    assert [d.slot for d in returned]==['roi0'] and not returned[0].confirmed
