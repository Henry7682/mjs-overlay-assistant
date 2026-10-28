from dataclasses import replace
from types import SimpleNamespace
import numpy as np
from mjs_assistant.recommendations import ModeContext,SelectionSnapshot,validate_image_candidates
from mjs_assistant.selection_state import SelectionGuard
from mjs_assistant.recognition import Detection
from mjs_assistant.ocr import Names


def snapshot():
    return SelectionSnapshot(ModeContext('ranked_chuhan_2v2','game','selection'),
        phase='selection',reference_only=True,image_only=True)


def test_ranked_image_query_needs_scene_but_not_local_names():
    snap=snapshot()
    assert snap.can_request(True)
    assert replace(snap,own_pool=('赵云',)).can_request(True)
    assert not replace(snap,own_locked='已锁定').can_request(True)
    assert not replace(snap,phase='battle').can_request(True)
    assert not replace(snap,context=replace(snap.context,mode_id='peak_chuhan_2v2')).can_request(True)
    assert not replace(snap,remaining_seconds=17).can_request(True)
    assert snap.fingerprint==replace(snap,own_pool=('赵云',),ally_pool=('赵云',),own_seat=1).fingerprint


def test_mini_candidate_validation_can_work_with_no_local_ocr():
    names=('赵云','郭嘉','甄宓','刘备','韩非','平原君','韩娥','尉缭')
    assert validate_image_candidates(names,names)==None
    assert validate_image_candidates(names,names,('赵云',))==None
    assert validate_image_candidates(names,names,('白起',)) is None
    assert validate_image_candidates(names[:-1],names)
    assert validate_image_candidates(names[:-1]+('赵云',),names)
    assert validate_image_candidates(names,names[:-1])


def test_ranked_image_guard_ignores_ocr_and_portrait_animation_but_tracks_names_and_lock():
    frame=np.zeros((600,1000,3),np.uint8);guard=SelectionGuard()
    def update(items=()):return guard.update(frame,items,'ranked_chuhan_2v2','selection','selection',image_only=True)
    first,_=update()
    frame[170:230,120:165]=200  # Portrait interior, outside the nameplate.
    items=[Detection('赵云','赵云',(92,147,111,192),.99,'roi0',True)]
    assert update(items)==(first,False)
    frame[147:192,92:111]=255  # Candidate nameplate really changed.
    second,changed=update(items)
    assert changed and second!=first
    frame[507:552,60:160]=(0,220,0)  # Ally's confirmation ribbon.
    assert update(items)[1]
    assert guard.update(frame,items,'ranked_chuhan_2v2','battle','battle',True)[1]


def test_traditional_wailiao_is_exact_alias_not_fuzzy():
    names=Names()
    assert names.resolve('尉繚')=='尉缭'
    assert names.resolve('尉续') is None
