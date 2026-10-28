from dataclasses import replace
from types import SimpleNamespace as NS, MethodType
from unittest.mock import Mock
import threading
import numpy as np
import pytest
from mjs_assistant.app import MainWindow
from mjs_assistant.guide_controller import GuideController
from mjs_assistant.guide_state import RoundGuideCache,PeakDraft,BattleTracker
from mjs_assistant.recommendations import (
    ModeContext, SelectionSnapshot, RecommendationResult, Recommendation,
    retain_previous_selection, refresh_image_result,
)


def snapshot(mode='ranked_chuhan_2v2'):
    return SelectionSnapshot(ModeContext(mode,'round','selection'),phase='selection',
        image_only=mode=='ranked_chuhan_2v2',reference_only=True,visual_revision='1')


def result(snap):
    return RecommendationResult('request','round',snap.fingerprint,
        (Recommendation('孙权','孙策',1,4,'原有说明'),),reference_only=True)


def host(busy=False,mode='ranked_chuhan_2v2'):
    snap=snapshot(mode)
    window=NS(mode_box=NS(currentData=lambda:mode),previous_scene='selection',game_id='round',
        selection_guard=NS(update=Mock(return_value=('2',True)),reason='visual',clear=Mock()),
        observed_seats=(1,4),provider=NS(busy=busy,cancel=Mock(),update_evidence=Mock(),active={'snapshot':snap}),
        overlay=NS(recommendation=None if busy else result(snap),recommendation_status=''),
        config={'recommendation':{'hotkeys':{'request':'Ctrl+Alt+P'}}},
        rec_status=NS(setText=Mock()),snapshot=snap,confirmed_snapshot=None,mode_evidence='manual',
        worker=NS(lock=threading.Lock(),allow_background=True),request_id='request',
        maybe_auto_recommend=Mock(),tick=Mock())
    window.guide_cache=RoundGuideCache(mode,'round',request_id='request')
    window.enemy_cache=RoundGuideCache(mode,'round')
    window.peak_draft=PeakDraft();window.battle_tracker=BattleTracker();window.guide_panel=NS(hide=Mock(),reset=Mock())
    window.pool_signature=();window.pool_since=0;window.unknown_frames=0;window.latest=None
    window.ranked_request_changed=False;window.enemy_attempted=False
    for name,method in GuideController.__dict__.items():
        if callable(method) and not hasattr(window,name):setattr(window,name,MethodType(method,window))
    window.maybe_enemy_query=Mock()
    return window


def data(scene='selection'):
    return dict(scene=scene,phase=scene,items=[],frame=np.zeros((200,400,3),np.uint8),
        seats=(2,3),self_locked=True,stamp=10.)


def test_ranked_swap_and_lock_keep_visible_guide_with_original_seats():
    window=host();MainWindow.update_selection(window,data())
    assert window.overlay.recommendation.recommendations[0].own_seat==1
    assert window.overlay.recommendation.previous_selection_state
    assert 'Ctrl+Alt+P' in window.overlay.recommendation.limits[0]
    window.provider.cancel.assert_not_called()


def test_inflight_ranked_change_keeps_upload_and_freezes_original_image_evidence():
    window=host(busy=True);MainWindow.update_selection(window,data())
    window.provider.cancel.assert_not_called();window.provider.update_evidence.assert_not_called()
    original=result(snapshot());MainWindow.recommendation_finished(window,original)
    assert window.overlay.recommendation.previous_selection_state
    assert window.overlay.recommendation.recommendations==original.recommendations


@pytest.mark.parametrize('scene',['battle','unknown'])
def test_battle_and_transient_unknown_keep_round_guide(scene):
    window=host();MainWindow.update_selection(window,data(scene))
    assert window.overlay.recommendation is not None and window.request_id=='request'


def test_peak_changes_do_not_cancel_ban_request():
    window=host(busy=True,mode='peak_chuhan_2v2');MainWindow.update_selection(window,data())
    window.provider.cancel.assert_not_called()


def test_retained_reference_cannot_cross_request_round_or_mode():
    snap=snapshot();guide=result(snap);locked=replace(snap,own_locked='孙权',visual_revision='2')
    assert guide.can_display(locked,'request')
    assert not guide.can_display(locked,'next-request')
    assert not guide.can_display(replace(locked,context=replace(locked.context,game_id='next-round')),'request')
    assert not guide.can_display(replace(locked,context=replace(locked.context,mode_id='peak_chuhan_2v2')),'request')


def test_old_reference_does_not_mix_new_hero_pool_into_original_conflict_check():
    snap=snapshot();guide=retain_previous_selection(result(snap),'Ctrl+Alt+P')
    assert retain_previous_selection(guide,'Ctrl+Alt+P') is guide
    assert refresh_image_result(guide,replace(snap,own_pool=('赵云',))) is guide
