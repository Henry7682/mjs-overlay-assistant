from types import SimpleNamespace as NS
import numpy as np
import pytest

from mjs_assistant.guide_state import BattleTracker, PeakDraft, enemy_auto_allowed
from mjs_assistant.guide_reader import result_scroll_target
from mjs_assistant.modes import MINGDAO, PEAK_SHUANGLONG, PEAK_CHUHAN, RANKED_CHUHAN
from mjs_assistant.recognition import Detection, Recognizer, Stabilizer, peak_phase, profile_key
from mjs_assistant.ocr import Names, Word
from test_ranked_retention import host
from test_v03_guides import card


def battle(friend=('孙权','孙策'), enemy=('张仪',)):
    pairs=list(zip(('roi4','roi2'),friend))+list(zip(('roi0','roi1'),enemy))
    items=[Detection(n,n,(0,0,1,1),1,s,True) for s,n in pairs]
    badges={s:dict(camp='楚军' if s in ('roi4','roi2') else '汉军',seat=None) for s,n in pairs}
    badges.setdefault('roi4',dict(camp='楚军',seat=None))
    return items,badges


@pytest.mark.parametrize('mode',[RANKED_CHUHAN,PEAK_CHUHAN])
def test_missing_enemy_never_blocks_friendly_guides(mode):
    w=host(mode=mode);w.enemy_status='敌方尚未查询';items,badges=battle()
    for _ in range(2):r=w.battle_tracker.update(items,badges)
    assert r.friendly_confirmed and not r.enemy_confirmed and not r.confirmed
    w.guide_cache.raw_cards=(card(reason='己方已缓存攻略'),)
    html=w.guide_html('battle')
    assert '己方已缓存攻略' in html and '等待该阵营两名主将识别' in html


def test_single_known_friendly_hero_shows_only_related_cached_guides():
    w=host(mode=PEAK_CHUHAN);items,badges=battle(friend=('孙权',),enemy=('张仪','荀彧'))
    for _ in range(2):r=w.battle_tracker.update(items,badges)
    w.guide_cache.raw_cards=(card(reason='可能组合甲'),card('孙权','刘备','可能组合乙'),card('孙策','刘备','无关组合'))
    html=w.guide_html('battle')
    assert '可能组合甲' in html and '可能组合乙' in html and '无关组合' not in html
    assert '尚未确认实际组合' in html
    assert enemy_auto_allowed(RANKED_CHUHAN,r,False) and not enemy_auto_allowed(PEAK_CHUHAN,r,False)
    # Enemy confirmation is independent of the missing friendly portrait.
    assert r.enemy_confirmed and not r.friendly_confirmed


def test_unknown_camp_breaks_consecutive_evidence_but_preserves_known_team():
    t=BattleTracker();items,badges=battle()
    assert not t.update(items,badges).friendly
    assert not t.update(items,{}).friendly
    assert not t.update(items,badges).friendly
    assert t.update(items,badges).friendly==('孙权','孙策')
    assert t.update([],{}).friendly==('孙权','孙策')


@pytest.mark.parametrize('count',range(6,13))
def test_postban_early_evidence_is_frozen_once_and_never_reduced(count):
    p=PeakDraft();pool=tuple(f'将{i}' for i in range(14))
    p.update('ban','ban14',pool,14,0)
    p.update('selection',f'draft{count}',pool[:count],count,1)
    # An already confirmed name missing from the next frame remains evidence.
    p.update('selection',f'draft{count}',pool[:count-1],count,2.6)
    assert p.frozen and p.excluded==set(pool[count:])
    for phase,layout in [('selection',f'draft{count}'),('unknown','unknown'),('ban','ban14')]:
        p.update(phase,layout,pool[:2],2,10)
        assert p.excluded==set(pool[count:])


def test_selection_landmark_cannot_reopen_ban_or_use_late_disappearance():
    p=PeakDraft();pool=tuple(f'将{i}' for i in range(14))
    p.update('ban','ban14',pool,14,0)
    p.update('selection','draft9',pool[:6],9,1)
    p.update('ban','ban14',('新名字',),14,2)
    assert '新名字' not in p.ban_seen
    p.update('selection','draft9',pool[:9],9,5)
    assert p.auto_closed and not p.frozen and not p.excluded
    assert peak_phase('',False,'楚汉汉楚',draft_layout='draft9')==('unknown','unknown')
    assert peak_phase('其他玩家选择中',False,'',draft_layout='draft9')==('selection','draft9')
    assert peak_phase('请等待其他玩家选择武将',False,'楚汉汉楚',draft_layout='draft12')==('selection','draft12')


def test_early_portrait_disappearance_cannot_shrink_expected_roster():
    p=PeakDraft();pool=tuple(f'将{i}' for i in range(14))
    p.update('ban','ban14',pool,14,0)
    p.update('selection','draft9',pool[:8],9,1)
    p.update('selection','draft8',pool[:8],8,2.6)
    assert not p.frozen and p.selection_count==9
    p.update('selection','draft8',pool[:8],8,5)
    assert p.auto_closed and not p.excluded


def test_scroll_anchor_uses_visible_results_after_heading_has_left_screen():
    point,signature=result_scroll_target((0,0,416,781),(10,710,120,20),
        (20,320,50,20,20,400,50,20),
        (20,-30,80,20,20,450,80,25,20,660,100,20,20,760,80,20))
    assert point==(208,670) and len(signature)==2
    assert result_scroll_target((0,0,416,781),(),(20,400,50,20),(20,660,80,20))==(None,())
    # Offscreen/foreign rectangles cannot become a click target.
    assert result_scroll_target((0,0,416,781),(10,710,120,20),(20,400,50,20),(500,660,80,20))==(None,())


@pytest.mark.parametrize('score,accepted',[(.79,False),(.80,True),(.84,True)])
@pytest.mark.parametrize('scene',['selection','battle'])
def test_name_threshold_still_requires_exact_dictionary_and_two_frames(score,accepted,scene):
    ocr=NS(read=lambda image:[Word('平阳公主',score,(17,20,23,100))])
    r=Recognizer(ocr,Names());r.read_region=lambda key,image:[]
    frame=np.zeros((667,1280,3),np.uint8)
    profiles={profile_key(scene,1280,667):{'regions':[(.2,.2,.23,.35)]}}
    _,items,_=r.analyze(frame,scene_override=scene,profiles=profiles,mode_id=MINGDAO)
    assert bool(items[0].name)==accepted
    s=Stabilizer();assert not s.update(scene,items,1)[0].confirmed
    assert s.update(scene,items,2)[0].confirmed==accepted


@pytest.mark.parametrize('mode',[MINGDAO,PEAK_SHUANGLONG,PEAK_CHUHAN,RANKED_CHUHAN])
def test_battle_nameplates_gain_margin_without_changing_manual_calibration(mode):
    r=Recognizer(NS(read=lambda image:[Word('孙权',1,(17,20,23,100))]),Names())
    r.read_region=lambda key,image:[]
    frame=np.zeros((1000,2000,3),np.uint8)
    _,items,_=r.analyze(frame,scene_override='battle',mode_id=mode)
    x=.294 if mode in (PEAK_CHUHAN,RANKED_CHUHAN) else .151
    assert items[0].box==(int((x-.002)*2000),int((.088-.008)*1000),int((x+.034+.002)*2000),188)
    profiles={profile_key('battle',2000,1000):{'regions':[(.2,.2,.23,.35)]}}
    _,items,_=r.analyze(frame,scene_override='battle',profiles=profiles,mode_id=mode)
    assert items[0].box==(400,200,460,350)
