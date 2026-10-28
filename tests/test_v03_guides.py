from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from mjs_assistant.modes import *
from mjs_assistant.stats_source import statistics_mode,is_strong,source_label
from mjs_assistant.storage import BoardStore
from mjs_assistant.guide_state import GuideQuery,RoundGuideCache,PeakDraft,BattleTracker,BattleRoster,enemy_auto_allowed
from mjs_assistant.guide_reader import GuidePages
from mjs_assistant.guide_panel import clamped_position,card_html
from mjs_assistant.recommendations import SelectionSnapshot,ModeContext,RecommendationResult,filter_cards
from mjs_assistant.provider import WeChatMiniProgramProvider
from mjs_assistant.recognition import Detection,peak_phase


@pytest.mark.parametrize('win,pick,expected',[(20,None,True),(21,51,False),(21,50,True),(50,50,True),(51,1,False),(1,None,True),(None,1,False),(0,0,False),(False,1,False),(-1,1,False),(50,None,False)])
def test_strong_boundary_and_missing_ranks(win,pick,expected):
    assert is_strong({'win_rank':win,'pick_rank':pick})==expected


def test_stats_mapping_keeps_raw_boards_and_no_ranked_fallback(tmp_path,monkeypatch):
    ordinary=BoardStore(tmp_path,RANKED_CHUHAN);peak=BoardStore(tmp_path,PEAK_CHUHAN)
    assert statistics_mode(RANKED_CHUHAN)==PEAK_CHUHAN
    assert ordinary.mode_id==RANKED_CHUHAN and peak.mode_id==PEAK_CHUHAN
    for mode in (MINGDAO,PEAK_SHUANGLONG,PEAK_CHUHAN):assert statistics_mode(mode)==mode
    assert '统计来源' in source_label(RANKED_CHUHAN)
    # Removing the source must not silently use the ordinary board.
    import mjs_assistant.storage as storage
    original=storage.read_json
    monkeypatch.setattr(storage,'read_json',lambda path,*args:None if PEAK_CHUHAN in str(path) else original(path,*args))
    source=BoardStore(tmp_path,statistics_mode(RANKED_CHUHAN))
    assert not source.board['heroes'] and BoardStore(tmp_path,RANKED_CHUHAN).board['heroes']


def test_source_rollback_is_shared_but_raw_ordinary_is_unchanged(tmp_path):
    from copy import deepcopy
    ordinary=BoardStore(tmp_path,RANKED_CHUHAN);raw=deepcopy(ordinary.board)
    peak=BoardStore(tmp_path,PEAK_CHUHAN);initial=deepcopy(peak.board)
    newer=deepcopy(initial);newer['period_start']='2026-09-24';newer['period_end']='2026-10-07'
    peak.install(newer)
    assert BoardStore(tmp_path,statistics_mode(RANKED_CHUHAN)).board['period_start']=='2026-09-24'
    peak.rollback()
    assert BoardStore(tmp_path,statistics_mode(RANKED_CHUHAN)).board==initial
    assert BoardStore(tmp_path,RANKED_CHUHAN).board==raw


def card(a='孙权',b='孙策',reason='说明'):
    return dict(heroes=[a,b],seats=[(a,'1',b,'4')],reason=reason,rating=None)


def result(request='q',game='g',cards=()):
    return RecommendationResult(request,game,'fp',source_cards=cards)


def test_one_time_filter_applies_to_late_batches_but_never_deletes_raw_cache():
    c=RoundGuideCache(PEAK_CHUHAN,'g');q=GuideQuery('selection',PEAK_CHUHAN,'g','q',('孙权','孙策','陆逊'),30)
    assert c.begin(q)
    c.freeze({'陆逊'});assert c.accept(result(cards=(card(),card('陆逊','孙策'))))
    assert len(c.raw_cards)==2 and len(c.visible_cards())==1
    c.freeze({'孙权'});assert c.excluded=={'陆逊'}
    assert not c.accept(result(request='old',cards=(card(),)))
    assert not c.accept(result(game='old',cards=(card(),)))
    assert not c.begin(replace(q,mode_id=RANKED_CHUHAN))
    assert c.begin(replace(q,request_id='q2')) and c.excluded=={'陆逊'}


def test_peak_missing_three_only_triggers_transition_not_filter():
    p=PeakDraft();pool=tuple(f'将{i}' for i in range(14))
    p.update('ban','ban14',pool,14,0)
    p.update('unknown','unknown',pool[:9],9,2)
    assert not p.frozen and p.phase=='transition'
    p.update('transition','ban14',pool,14,3)
    assert not p.frozen
    p.update('selection','draft9',pool[:9],9,4)
    p.update('selection','draft9',pool[:8],9,4.5)  # Early confirmed evidence survives dropout.
    p.update('selection','draft9',pool[:9],9,5.0)
    p.update('selection','draft9',pool[:9],9,5.6)
    assert p.frozen and p.excluded==set(pool[9:])
    p.update('selection','draft9',pool[:9],9,6.2)
    assert p.frozen and p.excluded==set(pool[9:])
    p.update('selection','draft9',pool[:2],2,8)
    p.update('battle','default',(),0,10)
    assert p.excluded==set(pool[9:])


def test_incomplete_postban_waits_without_timeout_guess_and_manual_confirmation_once():
    p=PeakDraft();p.update('ban','ban14',('甲','乙','丙'),14,0)
    for t in range(2,100):p.update('selection','draft9',('甲','乙'),9,t)
    assert not p.frozen and '待确认' in p.message
    assert p.confirm(('甲','乙')) and p.excluded=={'丙'}
    assert not p.confirm(('甲','丙')) and p.excluded=={'丙'}


def test_locked_evidence_preserves_fast_picked_hero():
    p=PeakDraft();pool=tuple(f'将{i}' for i in range(14));p.update('ban','ban14',pool,14,0)
    p.update('selection','draft9',pool[:8],8,2,locked=(pool[8],))
    p.update('selection','draft9',pool[:8],8,4,locked=())
    assert p.frozen and pool[8] not in p.excluded


def test_partial_pages_dedup_and_repetition_are_not_end_evidence():
    p=GuidePages();page=dict(selected=['孙权','孙策'],cards=[card()])
    for _ in range(4):p.add(page)
    assert not p.complete and len(p.cards)==1
    p.add(dict(selected=page['selected'],cards=[card(reason='另一个方向说明')]),at_end=True)
    assert p.complete and len(p.cards)==2
    with pytest.raises(ValueError):p.add(dict(selected=['孙权','陆逊'],cards=[]))


def test_true_no_result_and_partial_cache_are_distinct():
    p=GuidePages();p.add(dict(selected=['孙权','孙策'],no_result=True))
    assert p.no_result and p.complete
    cache=RoundGuideCache(RANKED_CHUHAN,'g')
    assert '尚未' in cache.empty_message()
    cache.received=True;assert '不完整' in cache.empty_message()
    cache.no_match=True;assert '小程序明确' in cache.empty_message()


def test_all_cards_kept_without_top_three_limit():
    names=('孙权','孙策','陆逊','孙尚香')
    snap=SelectionSnapshot(ModeContext(PEAK_CHUHAN,'g','selection'),names,names,phase='ban',reference_only=True)
    cards=[card(names[a],names[b]) for a,b in [(0,1),(0,2),(0,3),(1,2),(1,3),(2,3)]]
    assert len(filter_cards(cards,snap))==12


def test_roster_requires_both_camps_and_stable_main_heroes():
    t=BattleTracker()
    items=[Detection(n,n,(0,0,1,1),1,s,True) for s,n in [('roi0','张仪'),('roi1','荀彧'),('roi2','袁术'),('roi4','金日磾')]]
    badges={s:dict(camp=c,seat=p) for s,c,p in [('roi0','汉军',3),('roi1','汉军',2),('roi2','楚军',4),('roi4','楚军',1)]}
    assert not t.update(items,{}).confirmed
    assert not t.update(items,badges).confirmed
    roster=t.update(items,badges)
    assert roster.friendly==('金日磾','袁术') and set(roster.enemy)=={'张仪','荀彧'}
    assert enemy_auto_allowed(RANKED_CHUHAN,roster,False)
    assert not enemy_auto_allowed(RANKED_CHUHAN,roster,True)
    assert not enemy_auto_allowed(PEAK_CHUHAN,roster,False)
    # A puppet / temporarily unreadable name doesn't overwrite established teams.
    assert t.update([Detection('刘备','刘备',(0,0,1,1),1,'puppet0',True)],{}).friendly==roster.friendly


def test_phase_geometry_does_not_treat_three_missing_as_selection():
    assert peak_phase('',True,'')==('transition','ban14')
    assert peak_phase('请选择3名禁止双方选择的武将',True,'')==('ban','ban14')
    assert peak_phase('请选择本局要使用的武将',False,'')==('unknown','unknown')
    assert peak_phase('请选择本局要使用的武将',False,'',draft_layout='draft11')==('selection','draft11')
    assert peak_phase('',False,'')==('unknown','unknown')


def test_panel_position_clamps_at_window_edges_and_content_is_escaped():
    assert clamped_position((100,200,1000,600),(430,430),(1.5,-.5))==(670,200)
    assert clamped_position((100,200,200,100),(430,430),(1,1))==(100,200)
    assert '&lt;script&gt;' in card_html([card(reason='<script>')])


def test_provider_cancel_preserves_partial_on_timeout():
    from types import MethodType
    partial=result(cards=(card(),))
    p=NS(active={'partial':partial},finished=NS(emit=Mock()),status=NS(emit=Mock()),_return_failed=False)
    p._finish=lambda restore:setattr(p,'active',None)
    WeChatMiniProgramProvider.cancel(p,'30 秒超时')
    saved=p.finished.emit.call_args.args[0]
    assert saved.source_cards==partial.source_cards and not saved.complete
    assert '30 秒超时' in saved.limits


def test_controller_enemy_queries_once_even_when_start_fails_and_peak_never_queries(monkeypatch):
    from test_ranked_retention import host,data
    from mjs_assistant.guide_controller import GuideController
    monkeypatch.setattr('mjs_assistant.guide_controller.foreground',lambda hwnd:True)
    monkeypatch.setattr('mjs_assistant.guide_controller.input_idle_seconds',lambda:1)
    import time
    window=host();window.config['recommendation'].update(enabled=True,automatic=True)
    window.window_box=NS(currentData=lambda:123)
    window.latest=data('battle');window.latest['stamp']=time.monotonic()
    window.provider.connection_status=lambda:(True,'ready')
    window.provider.start=Mock(side_effect=RuntimeError('测试中断'))
    window.battle_tracker.roster=BattleRoster(('孙权','孙策'),('张仪','荀彧'),(1,4),(2,3),'楚军',True)
    for _ in range(4):GuideController.maybe_enemy_query(window)
    assert window.provider.start.call_count==1 and window.enemy_attempted
    window.mode_box.currentData=lambda:PEAK_CHUHAN;window.enemy_attempted=False
    GuideController.maybe_enemy_query(window)
    assert window.provider.start.call_count==1


def test_partial_picker_input_is_explicit_and_never_claims_global_no_match():
    names=('孙权','孙策','陆逊')
    snap=SelectionSnapshot(ModeContext(PEAK_CHUHAN,'g','selection'),names,names,phase='ban',reference_only=True)
    state={'snapshot':snap,'id':'q'}
    with pytest.raises(ValueError):
        WeChatMiniProgramProvider.make_result(state,dict(selected=names[:2],no_result=True))
    r=WeChatMiniProgramProvider.make_result(state,dict(selected=names[:2],no_result=True,input_incomplete=True))
    assert not r.complete and not r.no_match


def test_growing_picker_pool_uses_latest_public_order_without_losing_old_cards():
    c=RoundGuideCache(PEAK_CHUHAN,'g',request_id='q')
    first=card();second=card('陆逊','孙策')
    assert c.accept(result(cards=(first,)))
    assert c.accept(result(cards=(second,first)))
    assert c.raw_cards==(second,first)
    assert c.accept(result(cards=(second,)))
    assert c.raw_cards==(second,first)


def test_cached_conflict_filter_survives_into_battle_without_requiring_old_seats():
    c=RoundGuideCache(RANKED_CHUHAN,'g',request_id='q')
    r=replace(result(cards=(card(),card('陆逊','孙策'))),selected_candidates=('孙权','孙策','陆逊'),local_observed=('孙权','孙策','刘备'))
    assert c.accept(r)
    assert len(c.raw_cards)==2 and c.visible_cards()==(card(),)
    # Even if the old selection direction had no recommendation, raw valid cards remain.
    assert c.pair_cards(('孙权','孙策'),(2,3))==(card(),)
