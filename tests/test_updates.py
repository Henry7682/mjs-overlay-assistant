import copy
from contextlib import contextmanager

import httpx
import numpy as np
import pytest

from mjs_assistant.ocr import Names, Word
from mjs_assistant.storage import ASSETS, read_json, BoardStore
from mjs_assistant.updater import Updater


class FakeResponse:
    def __init__(self,text='',data=b'fake image'):self.text,self.data=text,data
    def raise_for_status(self):pass
    def iter_bytes(self):yield self.data


def fake_http(monkeypatch,listing,post='',error=None):
    class Client:
        def __init__(self,*a,**k):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def get(self,url):
            if error:raise error
            return FakeResponse(listing if '/topic?' in url else post)
        @contextmanager
        def stream(self,*a,**k):yield FakeResponse()
    monkeypatch.setattr('mjs_assistant.updater.httpx.Client',Client)


def test_same_post_does_not_load_models(tmp_path,monkeypatch):
    b=read_json(ASSETS/'board.json')
    fake_http(monkeypatch,f'<a href="{b["source_url"]}">武将胜率</a>')
    assert '最新' in Updater(tmp_path,None,Names()).check(b,True)[1]


@pytest.mark.parametrize('error',[None,httpx.ConnectError('offline')])
def test_network_or_page_failure_keeps_board(tmp_path,monkeypatch,error):
    store=BoardStore(tmp_path);original=copy.deepcopy(store.board)
    fake_http(monkeypatch,'captcha or changed markup',error=error)
    with pytest.raises((ValueError,httpx.ConnectError)):Updater(tmp_path,None,Names()).check(store.board,True)
    assert store.board==original and not store.path.exists()


class Ocr:
    def __init__(self,mode='明刀暗箭 8人身份'):self.mode=mode
    def read(self,img):return [Word(self.mode,1,(0,0,1,1))]
    def document(self,img):return []


@pytest.mark.parametrize('bad',[False,True])
def test_new_period_validation_and_pending(tmp_path,monkeypatch,bad):
    old=read_json(ASSETS/'board.json');new=copy.deepcopy(old)
    new.update(period_start='2026-10-22',period_end='2026-10-25',image_sha256='abc',source_url='https://www.taptap.cn/moment/999999999999999999')
    if bad:new['issues']=['OCR错行']
    fake_http(monkeypatch,f'<a href="{new["source_url"]}">武将胜率</a>',
              '<h1>名将杀 · 武将胜率</h1><img alt="名将杀 · 武将胜率 1" src="https://img2-tc.tapimg.com/moment/etag/test_20261026110504.jpg/_tap_ugc.jpg">')
    monkeypatch.setattr('mjs_assistant.updater.decode_image',lambda data:np.ones((300,800,3),np.uint8))
    monkeypatch.setattr('mjs_assistant.updater.parse_words',lambda *a,**k:new)
    draft,message=Updater(tmp_path,Ocr(),Names()).check(old,True)
    assert draft['period_end']=='2026-10-25'
    assert ('复核' in message)==bad
    assert (tmp_path/'boards/pending.json').exists()
    assert not (tmp_path/'board.json').exists()  # UI commits only after validation.


def test_other_mode_does_not_replace(tmp_path,monkeypatch):
    b=read_json(ASSETS/'board.json')
    fake_http(monkeypatch,'<a href="/moment/999999999999999999">武将胜率</a>',
              '<h1>名将杀 · 武将胜率</h1><img alt="名将杀 · 武将胜率 1" src="https://img2-tc.tapimg.com/moment/etag/test.jpg/_tap_ugc.jpg">')
    monkeypatch.setattr('mjs_assistant.updater.decode_image',lambda data:np.ones((300,800,3),np.uint8))
    assert Updater(tmp_path,Ocr('争锋 8人身份'),Names()).check(b,True)[0] is None


def test_same_post_for_one_mode_still_checks_all_other_charts(tmp_path,monkeypatch):
    from mjs_assistant.modes import MINGDAO,RANKED_CHUHAN,PEAK_CHUHAN,MODES
    currents=BoardStore(tmp_path).all_current()
    link=currents[MINGDAO]['source_url']
    # Only identity is already current at this post; both ChuHan boards are old.
    for mode in (RANKED_CHUHAN,PEAK_CHUHAN):
        currents[mode]['source_url']='https://www.taptap.cn/moment/1'
        currents[mode]['period_end']='2026-10-07'
    fake_http(monkeypatch,f'<a href="{link}">武将胜率</a>',
        '<h1>武将胜率</h1>'+''.join(f'<img alt="武将胜率 {i}" src="https://img2-tc.tapimg.com/moment/etag/img{i}.jpg">' for i in (1,2)))
    monkeypatch.setattr('mjs_assistant.updater.decode_image',lambda data:np.ones((300,800,3),np.uint8))
    class MultiOcr:
        index=-1
        def read(self,img):
            self.index+=1
            return [Word(('楚汉争霸','巅峰楚汉')[self.index],1,(0,0,1,1))]
        def document(self,img):return self.index
    def parse(index,*args,**kwargs):
        mode=(RANKED_CHUHAN,PEAK_CHUHAN)[index]
        b=copy.deepcopy(BoardStore(tmp_path,mode).board);b['image_sha256']=str(index)
        return b
    monkeypatch.setattr('mjs_assistant.updater.parse_words',parse)
    drafts,_=Updater(tmp_path,MultiOcr(),Names()).check(currents,True)
    assert {b['mode_id'] for b in drafts}=={RANKED_CHUHAN,PEAK_CHUHAN}
