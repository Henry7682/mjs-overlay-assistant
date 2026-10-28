from dataclasses import replace
import pytest
from mjs_assistant.recommendations import (
    ModeContext, SelectionSnapshot, RecommendationResult,
    filter_image_cards, refresh_image_result,
)
from mjs_assistant.ocr import Names
from mjs_assistant.provider import WeChatMiniProgramProvider
from test_manual_review import host

SELECTED=('孙权','孙策','刘备','孙尚香','终军','杨艳','荀彧','司马睿')
LOCAL=SELECTED[:-1]+('赵云',)


def card(a,b):
    return dict(heroes=[a,b],seats=[(a,'1',b,'4')],reason='小程序原说明')


CARDS=(card('司马睿','刘备'),card('孙权','孙策'),card('刘备','孙尚香'))


def snap():
    return SelectionSnapshot(ModeContext('ranked_chuhan_2v2','g','selection'),
        phase='selection',image_only=True,reference_only=True,own_seat=1,ally_seat=4)


def test_conflict_filters_pairs_before_top_three_and_keeps_provider_order():
    kept,limits=filter_image_cards(CARDS,SELECTED,LOCAL,snap())
    assert [(r.own_hero,r.ally_hero) for r in kept]==[('孙权','孙策'),('刘备','孙尚香')]
    assert kept[0].reason=='小程序原说明' and '司马睿' in limits[0]


def test_partial_local_ocr_is_not_itself_a_conflict():
    kept,limits=filter_image_cards(CARDS,SELECTED,('孙权',),snap())
    assert len(kept)==3 and not limits


def test_partial_conflict_keeps_only_agreed_names_without_guessing_slot_mapping():
    kept,limits=filter_image_cards(CARDS,SELECTED,('孙权','孙策','赵云'),snap())
    assert len(kept)==1 and kept[0].own_hero=='孙权'
    assert '尚未完整' in limits[1]


def test_all_conflicting_cards_return_explicit_empty_result():
    kept,limits=filter_image_cards(CARDS[:1],SELECTED,LOCAL,snap())
    assert not kept and limits


def test_late_local_evidence_refilters_same_request():
    initial,_=filter_image_cards(CARDS,SELECTED,(),snap())
    result=RecommendationResult('r','g',snap().fingerprint,initial,reference_only=True,
        selected_candidates=SELECTED,source_cards=CARDS)
    updated=refresh_image_result(result,replace(snap(),own_pool=LOCAL))
    assert len(updated.recommendations)==2 and updated.is_current(snap(),'r')
    assert refresh_image_result(updated,snap()) is updated  # Temporary OCR loss cannot re-add a conflict.


@pytest.mark.parametrize('manual',[False,True])
def test_worker_success_with_conflict_publishes_filtered_result(monkeypatch,manual):
    messages=([{'event':'input_complete'},{'event':'manual_review'}] if manual else [])
    messages.append(dict(status='success',selected=SELECTED,cards=CARDS,manually_reviewed=manual))
    p,state,_,_=host(monkeypatch,messages)
    state['snapshot']=replace(state['snapshot'],own_pool=LOCAL,ally_pool=LOCAL,own_seat=1,ally_seat=4)
    WeChatMiniProgramProvider.poll(p)
    p.cancel.assert_not_called()
    result=p.finished.emit.call_args.args[0]
    assert len(result.recommendations)==2 and result.limits[0].startswith('姓名存在冲突')


def test_mibazi_explicit_glyph_variants_not_arbitrary_fuzzy_names():
    names=Names()
    for raw in ('芈八子','半八子','羋八子'):
        assert names.resolve(raw)=='芈八子'
    assert names.resolve('半子') is None
    assert names.resolve('羊八子') is None
