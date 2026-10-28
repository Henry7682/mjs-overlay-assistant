from dataclasses import replace
from mjs_assistant.recommendations import (
    ModeContext,SelectionSnapshot,RecommendationResult,filter_cards,capability_limits)


def selection():
    return SelectionSnapshot(ModeContext('ranked_chuhan_2v2','game-1','selection','manual'),
        own_pool=('夏侯惇','鲁仲连','主父偃'),ally_pool=('夏侯惇','鲁仲连','主父偃'),
        own_seat=4,ally_seat=1,phase='selection',pools_confirmed=True,remaining_seconds=30)


def cards():
    return [{'heroes':['夏侯惇','鲁仲连'],'seats':[['夏侯惇','4','鲁仲连','1'],['夏侯惇','3','鲁仲连','2']],
             'reason':'原始理由','rating':None},
            {'heroes':['鲁仲连','主父偃'],'seats':[['鲁仲连','1','主父偃','4']],'reason':'另一理由'}]


def test_legal_direction_and_locked_ally():
    snap=replace(selection(),ally_locked='鲁仲连')
    result=filter_cards(cards(),snap)
    assert [(r.own_hero,r.ally_hero,r.own_seat) for r in result]==[
        ('夏侯惇','鲁仲连',4),('主父偃','鲁仲连',4)]
    assert result[0].reason=='原始理由' and result[0].rating is None
    assert filter_cards(cards(),replace(snap,own_pool=('白起',)))==()


def test_unknown_pool_ban_and_time_gates():
    snap=selection()
    assert snap.can_request(True)
    assert replace(snap,remaining_seconds=None).can_request(True)
    assert not replace(snap,remaining_seconds=17).can_request(True)
    assert replace(snap,remaining_seconds=None).can_request(False)
    for phase in ('ban','waiting','battle','unknown'):
        assert filter_cards(cards(),replace(snap,phase=phase))==()
    assert filter_cards(cards(),replace(snap,pools_confirmed=False))==()


def test_stale_results_never_survive_state_changes():
    snap=selection()
    result=RecommendationResult('r1','game-1',snap.fingerprint)
    assert result.is_current(replace(snap,captured_at=42,remaining_seconds=20),'r1')
    for changed in (replace(snap,own_pool=('白起',)),replace(snap,ally_locked='鲁仲连'),
                    replace(snap,own_seat=2),replace(snap,context=replace(snap.context,game_id='game-2')),
                    replace(snap,context=replace(snap.context,mode_id='peak_chuhan_2v2'))):
        assert not result.is_current(changed,'r1')
    assert not result.is_current(snap,'r2')


def test_shared_pool_assumption_is_visible():
    assert any('尚待确认' in s for s in capability_limits(replace(selection(),shared_pool_assumed=True)))
