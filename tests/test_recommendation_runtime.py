from dataclasses import replace
import json
import numpy as np
import pytest

from mjs_assistant.provider import ManagedImages
from mjs_assistant.hotkeys import parse_hotkey
from mjs_assistant.selection_state import SelectionGuard
from mjs_assistant.recognition import Detection
from mjs_assistant.recognition import selection_seconds,empty_selection_panel
from mjs_assistant.ocr import Word
from mjs_assistant.mini_worker import parse_document
from mjs_assistant.boards import validate_board
from mjs_assistant.storage import BoardStore
from mjs_assistant.modes import PEAK_SHUANGLONG


def test_registered_temp_cleanup_cannot_escape_or_delete_unregistered(tmp_path):
    manager=ManagedImages(tmp_path)
    outside=tmp_path/'private.png';outside.write_bytes(b'keep')
    untouched=manager.folder/'not-registered.png';untouched.write_bytes(b'keep')
    actual=manager.save(np.zeros((8,8,3),np.uint8))
    registered=json.loads(manager.registry.read_text('utf8'))
    manager.registry.write_text(json.dumps(registered+['../private.png',str(outside)]),'utf8')
    manager.cleanup()
    assert not actual.exists() and outside.read_bytes()==b'keep' and untouched.exists()


def test_card_visual_change_invalidates_same_names():
    guard=SelectionGuard();frame=np.zeros((200,400,3),np.uint8)
    items=[Detection('张仪','张仪',(100,40,108,60),.99,'roi0',True)]
    first,changed=guard.update(frame,items,'peak_chuhan_2v2','selection','selection')
    assert changed
    assert guard.update(frame.copy(),items,'peak_chuhan_2v2','selection','selection')==(first,False)
    frame[43:65,107:130]=180  # Same name, changed central badge.
    second,changed=guard.update(frame,items,'peak_chuhan_2v2','selection','selection')
    assert changed and second!=first
    assert guard.update(frame,items,'peak_chuhan_2v2','battle','battle')[1]


def test_hotkey_validation():
    assert parse_hotkey('Ctrl+Alt+R')==(0x4003,ord('R'))
    with pytest.raises(ValueError):parse_hotkey('Ctrl+Alt+Enter')


def test_selected_ally_panel_invalidates_unchanged_candidates():
    guard=SelectionGuard();frame=np.zeros((200,400,3),np.uint8)
    items=[Detection('张仪','张仪',(100,40,108,60),.99,'roi0',True)]
    before,_=guard.update(frame,items,'ranked_chuhan_2v2','selection','selection')
    frame[160:188,32:60]=180
    after,changed=guard.update(frame,items,'ranked_chuhan_2v2','selection','selection')
    assert changed and before!=after


def test_blank_panel_requires_positive_evidence():
    def word(text,score=1):return Word(text,score,(0,0,20,20))
    assert empty_selection_panel([word('将')])
    assert not empty_selection_panel([])
    assert not empty_selection_panel([word('将',.94)])
    assert not empty_selection_panel([word('将'),word('已确认')])


def test_unlabelled_numbers_never_enable_auto_switch():
    def word(text,score=1):return Word(text,score,(0,0,20,20))
    assert selection_seconds([word('18')]) is None
    assert selection_seconds([word('选将剩余时间：18秒')])==18
    assert selection_seconds([word('剩余20秒',.7)]) is None
    assert selection_seconds([word('剩余18秒'),word('剩余19秒')]) is None


def test_no_result_document_does_not_require_result_heading():
    doc='已选武将（点击移除） 清空 张仪 ✕ 袁术 ✕ 未找到匹配的组合搭配 位置: 不限'
    result=parse_document(doc)
    assert result['selected']==['张仪','袁术'] and result['no_result'] and not result['cards']
    one='位置: 不限 已选武将（点击移除） 清空 侯嬴 ✕ H 侯嬴 51.27%'
    assert parse_document(one)['selected']==['侯嬴']


def test_period_specific_identity_mapping_cannot_be_reused(tmp_path):
    board=BoardStore(tmp_path,PEAK_SHUANGLONG).board
    assert not validate_board(board)
    board['period_start']='2026-10-09'
    assert any('周期' in error for error in validate_board(board))
