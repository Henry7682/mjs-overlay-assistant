import copy
import json
from contextlib import contextmanager
from pathlib import Path
import threading
import time
import pytest
from mjs_assistant.updater import Updater
from mjs_assistant.ocr import Names
from mjs_assistant.storage import BoardStore,write_json,read_json
from mjs_assistant.migration import import_data

def test_update_attempt_does_not_overwrite_last_success(tmp_path,monkeypatch):
    original='2026-10-01T00:00:00+00:00'
    write_json(tmp_path/'update_state.json',{'last_success':original})
    u=Updater(tmp_path,None,Names())
    monkeypatch.setattr(u,'_check',lambda *a:(_ for _ in ()).throw(ValueError('offline')))
    with pytest.raises(ValueError):u.check({},True)
    state=read_json(tmp_path/'update_state.json')
    assert state['last_success']==original and state['last_attempt'] and state['status']=='error'
    assert '24' in u.check({},False)[1]
    monkeypatch.setattr(u,'_check',lambda *a:(None,'ok'))
    u.check({},True)
    assert read_json(tmp_path/'update_state.json')['last_success']!=original

def test_conditional_page_cache(tmp_path):
    calls=[]
    class Response:
        status_code=200;text='<h1>ranking</h1>';headers={'etag':'"first"'}
        def raise_for_status(self):pass
    class Client:
        def get(self,url,headers=None):
            calls.append(headers)
            r=Response()
            if headers:r.status_code=304;r.text=''
            return r
    u=Updater(tmp_path,None,Names())
    assert u._html(Client(),'https://example.com/page')=='<h1>ranking</h1>'
    assert u._html(Client(),'https://example.com/page')=='<h1>ranking</h1>'
    assert calls==[None,{'If-None-Match':'"first"'}]

def test_busy_wait_cancel_does_not_run_ocr(tmp_path):
    stop=threading.Event();messages=[]
    u=Updater(tmp_path,None,Names(),stop.is_set,lambda:True)
    stop.set()
    assert not u._idle(messages.append) and messages

def test_migration_rejects_mislabeled_board_before_any_write(tmp_path):
    src=tmp_path/'source';dst=tmp_path/'target'
    write_json(src/'settings.json',{'selected_mode':'auto'})
    board=BoardStore(tmp_path/'seed').board
    write_json(src/'boards/wrong-mode/current.json',board)
    write_json(dst/'settings.json',{'important':'keep'})
    with pytest.raises(ValueError):import_data(src,dst)
    assert read_json(dst/'settings.json')=={'important':'keep'}

def test_migration_backup_and_config_preserved(tmp_path):
    src=tmp_path/'source';dst=tmp_path/'target'
    write_json(src/'settings.json',{'recommendation':{'enabled':False,'hotkey':'custom'}})
    write_json(dst/'settings.json',{'old':1})
    backup=import_data(src,dst)
    assert read_json(backup/'settings.json')=={'old':1}
    assert read_json(dst/'settings.json')==read_json(src/'settings.json')
