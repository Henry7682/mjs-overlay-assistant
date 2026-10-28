import copy
import datetime as dt
import json
from pathlib import Path

import pytest

from mjs_assistant.boards import MODE, parse_words, validate_board
from mjs_assistant.ocr import Names, Word
from mjs_assistant.recognition import Detection, Stabilizer, place_labels, profile_key
from mjs_assistant.storage import ASSETS, BoardStore, read_json
from mjs_assistant.updater import post_links, post_images, Updater


@pytest.fixture
def board():
    return read_json(ASSETS / 'board.json')


def test_official_seed(board):
    assert validate_board(board) == []
    assert len(board['heroes']) == 191
    assert len(board['raw_win_rows']) == len(board['raw_pick_rows']) == 191
    assert [(x['name'], x['win_rate'], x['win_rank']) for x in board['heroes'][:3]] == [
        ('司马睿', 64.38, 1), ('偃师', 61.0, 2), ('白起', 59.69, 3)]
    assert all(Names().resolve(x['name']) for x in board['heroes'])
    assert 'pick_rate' not in board['heroes'][0]


@pytest.mark.parametrize('mutation', [
    lambda b: b.update(mode='争锋'),
    lambda b: b['heroes'].pop(),
    lambda b: b['heroes'][1].update(name=b['heroes'][0]['name']),
    lambda b: b['heroes'][1].update(win_rank=1),
    lambda b: b['heroes'][1].update(pick_rank=None),
    lambda b: b['heroes'][1].update(win_rate=101),
    lambda b: b['heroes'][1].update(win_rate=65),
    lambda b: b.update(period_start='2030-12-01'),
    lambda b: b.update(issues=['姓名疑点']),
])
def test_invalid_update_keeps_current(tmp_path, board, mutation):
    store = BoardStore(tmp_path)
    store.install(board)
    before = store.path.read_bytes()
    bad = copy.deepcopy(board); mutation(bad)
    with pytest.raises(ValueError): store.install(bad)
    assert store.path.read_bytes() == before
    assert store.board == board


def test_rollback_and_corrupt_current(tmp_path, board):
    store = BoardStore(tmp_path)
    new = copy.deepcopy(board); new['period_start'] = '2026-10-09'
    store.install(new); store.rollback()
    assert store.board == board
    store.path.write_text('{broken', encoding='utf8')
    assert BoardStore(tmp_path).board == board


def test_temporal_confirmation_and_replacement():
    s = Stabilizer(); a = Detection('白起','白起',(1,2,3,4),.99,'0')
    assert not s.update('selection',[a],0)[0].confirmed
    assert s.update('selection',[a],.5)[0].confirmed
    b = Detection('偃师','偃师',a.box,.99,'0')
    assert not s.update('selection',[b],1)[0].confirmed
    assert not s.update('battle',[b],1.5)[0].confirmed
    assert s.update('battle',[],2) == []
    assert not s.update('battle',[b],2.5)[0].confirmed
    assert not s.update('battle',[b],8)[0].confirmed


def test_ambiguous_names_are_not_fuzzy_matched():
    assert Names().resolve('王元') is None
    s=Stabilizer(); d=Detection(None,'王元',(0,0,1,1),.7,'0')
    s.update('selection',[d],0)
    assert not s.update('selection',[d],.5)[0].confirmed
    s.overrides[('0','王元')]='王元姬'
    assert s.update('selection',[d],1)[0].name == '王元姬'
    s.update('selection',[],1.5)
    assert not s.overrides


@pytest.mark.parametrize('scale',[1,1.25,1.5])
def test_label_geometry(scale):
    w,h=1920/scale,1080/scale
    items=[Detection('白起','白起',(w-30,80+i*4,w,110+i*4),1,str(i),True) for i in range(8)]
    boxes=[rect for d,rect in place_labels(items,w,h)]
    assert len(boxes)==8
    for i,(a,b,c,d) in enumerate(boxes):
        assert 0<=a<c<=w and 0<=b<d<=h
        assert all(c<=x or a>=z or d<=y or b>=v for x,y,z,v in boxes[:i])
    assert profile_key('battle',1920,1080)==profile_key('battle',2560,1440)


def test_listing_filters_unrelated_posts():
    html='<div class="moment-list-item"><a class="moment-avator__avator--content" href="/app/737825">名将杀</a><a class="moment-article__link" href="/moment/12">武将胜率排行榜</a></div>'
    html+='<a href="/moment/13">武将胜率 玩家推荐</a><div class="moment-list-item"><a class="moment-avator__avator--content" href="/user/other">玩家</a><a class="moment-article__link" href="/moment/14">武将胜率</a></div>'
    assert post_links(html)==['https://www.taptap.cn/moment/12']
    assert post_links('captcha')==[]


def test_article_attachments_exclude_recommendations():
    url='https://img2-tc.tapimg.com/moment/etag/board.jpg/_tap_ugc.jpg'
    html=f'<h1>名将杀 · 武将胜率</h1><img alt="名将杀 · 武将胜率 1" src="{url}">'
    html+='<img alt="攻略" src="https://img2-tc.tapimg.com/moment/etag/other.jpg">'
    assert post_images(html)==[url]
    assert post_images('<html>verification required</html>')==[]


@pytest.mark.parametrize('value',[[],42,{'heroes':None},{'heroes':[42]},{'heroes':[{'name':[]}]}])
def test_invalid_json_shapes_are_rejected(value):
    assert validate_board(value)


def test_update_daily_limit(tmp_path,board,monkeypatch):
    from mjs_assistant.storage import write_json
    write_json(tmp_path/'update_state.json',{'checked_at':dt.datetime.now(dt.timezone.utc).isoformat()})
    def forbidden(*a,**k):raise AssertionError('must not access network')
    monkeypatch.setattr('mjs_assistant.updater.httpx.Client',forbidden)
    assert '24' in Updater(tmp_path,None,Names()).check(board)[1]


def test_missing_model_is_actionable(tmp_path,monkeypatch):
    from mjs_assistant.ocr import Ocr
    monkeypatch.setattr('mjs_assistant.ocr.ASSETS',tmp_path)
    with pytest.raises(FileNotFoundError,match='模型缺失'):Ocr()


def test_parser_rejects_wrong_mode_and_incomplete_chart():
    words=[Word('争锋 8人身份',1,(0,0,200,20)),Word('10.08-10.21',1,(0,25,200,45)),
           Word('1',1,(10,100,20,120)),Word('司马睿',1,(80,100,140,120)),Word('64.38%',1,(200,100,280,120))]
    draft=parse_words(words,800,Names(),'https://www.taptap.cn/moment/1',year=2026)
    problems=validate_board(draft)
    assert any('模式' in p for p in problems)
    assert any('50' in p for p in problems)
    assert draft['period_start']=='2026-10-08'
