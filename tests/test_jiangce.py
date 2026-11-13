import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from mjs_assistant.jiangce import GuideBook, SEED
from mjs_assistant import jiangce_update as update
from mjs_assistant.guide_controller import GuideController
from mjs_assistant.guide_panel import card_html
from mjs_assistant.guide_state import RoundGuideCache, BattleTracker, PeakDraft
from mjs_assistant.modes import PEAK_CHUHAN
from mjs_assistant.recommendations import ModeContext, SelectionSnapshot
from tools.build_jiangce import parse_detail
from tools.sync_jiangce import listing


def test_actual_seed_and_partial_lock(tmp_path):
    book=GuideBook(SEED)
    manifest=(SEED.parent/'channel.json').read_bytes()
    meta,name=update.verify(manifest,(SEED.parent/'channel.sig').read_bytes())
    assert len(book.cards)==meta['count']
    assert hashlib.sha256(SEED.read_bytes()).hexdigest()==meta['sha256']
    cards=book.selection(['嬴政','蔺相如'],['白起','陈阿娇'],'白起')
    assert all('白起' in c['heroes'] for c in cards)
    sample=next(c for c in cards if c['id']=='01M2FN6NANEF5BZXJGPJ13YG0Z')
    html=card_html([sample],{'白起':2,'嬴政':3})
    assert html.index('白起 2 位、嬴政 3 位　5/5') < html.index('嬴政 1 位、白起 4 位　4/5')
    assert html.count(sample['reason'])==1
    assert list(book.battle(['嬴政'],partial=True))
    assert not book.battle(['嬴政'])
    assert not book.selection(['嬴政'],['嬴政'])
    with pytest.raises(Exception):
        update.verify(manifest+b' ',(SEED.parent/'channel.sig').read_bytes())


def test_unknown_seat_unrated_and_pagination_guard():
    raw="""<article class="combo-detail"><div class="combo-members-grid"><i class="general-card-name">甲</i>
    <i class="general-card-name">乙</i></div><div class="position-grid"><div><strong>2 / 3</strong>
    <p>站位未提供</p></div></div><div class="prose">说明</div><p class="muted">分享者：作者</p></article>"""
    card=parse_detail(raw.encode(),'example')
    assert card['variants']==[{'group':'2 / 3'}]
    assert '评分未提供' in card_html([card])
    with pytest.raises(ValueError):
        listing('<nav class="pagination">第 1 / 41 页</nav>'.encode(),2)


def test_local_round_incremental_and_frozen(tmp_path,monkeypatch):
    snap=SelectionSnapshot(ModeContext(PEAK_CHUHAN,'round','selection'),('嬴政','白起'),('嬴政','白起'),phase='ban')
    controller=SimpleNamespace(folder=tmp_path,enabled=True,guides_enabled=lambda:True,config={},snapshot=snap,
        confirmed_snapshot=None,current_mode=lambda:PEAK_CHUHAN,peak_draft=PeakDraft(),battle_tracker=BattleTracker(),
        game_id='round',guide_cache=RoundGuideCache(PEAK_CHUHAN,'round'),recommendation_status=lambda text:None)
    GuideController.local_query(controller,'selection')
    first=controller.local_book
    assert controller.guide_cache.visible_cards()
    controller.guide_cache.freeze({'白起'})
    GuideController.local_query(controller,'selection')
    assert not controller.guide_cache.visible_cards()
    assert controller.guide_cache.raw_cards
    assert controller.local_book is first


def test_failed_or_lagging_source(tmp_path,monkeypatch):
    raw=SEED.read_bytes()
    signed=json.loads((SEED.parent/'channel.json').read_text())
    roots=('a/','b/')
    monkeypatch.setattr(update,'ROOTS',roots)
    def mock_verify(data,sig):
        m=dict(signed,version=str(int(signed['version'])+int(data)))
        return m,m['version']+'-'+m['sha256']+'.sqlite'
    monkeypatch.setattr(update,'verify',mock_verify)
    def fetch(url,limit):
        if url.endswith('.json'):return b'2' if url.startswith('a/') else b'1'
        if url.endswith('.sig'):return b'test'
        return b'bad' if url.startswith('a/') else raw
    monkeypatch.setattr(update,'get_bytes',fetch)
    assert '已更新' in update.refresh(tmp_path)
    assert len(list(update.installed(tmp_path)))==1
    assert '失败' in update.refresh(tmp_path)
    assert len(list(update.installed(tmp_path)))==1



def test_daily_check_survives_restart_and_failed_source(tmp_path,monkeypatch):
    calls=[]
    def fake_refresh(folder):
        calls.append(folder)
        return '离线，保留本地库'
    monkeypatch.setattr(update,'refresh',fake_refresh)
    check=update.DailyCheck(tmp_path)
    check.check()
    check.thread.join(2)
    update.DailyCheck(tmp_path).check()
    assert calls==[tmp_path]
    check.check(force=True)
    check.thread.join(2)
    assert calls==[tmp_path,tmp_path]


def test_two_articles_same_heroes_keep_separate_reasons():
    book=GuideBook(SEED)
    card=book.selection(['嬴政'],['白起'])[0]
    second=dict(card,id='other',reason='另一篇说明')
    cache=RoundGuideCache(PEAK_CHUHAN,'round',raw_cards=(card,second))
    html=card_html(cache.pair_cards(('嬴政','白起'),(1,4)),{'嬴政':1,'白起':4})
    assert html.count('嬴政 1 位、白起 4 位　4/5')==2 and '另一篇说明' in html
