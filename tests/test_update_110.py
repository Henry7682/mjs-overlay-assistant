import copy
import numpy as np
import pytest
from mjs_assistant.update_state import due,begin,finish
from mjs_assistant.board_completeness import inspect_end
from mjs_assistant.board_channel import newer, validate_snapshot


def test_retry_is_persistent_bounded_and_success_is_not_overwritten():
    state={'last_success':100}
    for delay in (300,1800,7200,21600,21600):
        state=finish(begin(state,200),False,'offline',200,jitter=0)
        assert state['next_attempt']==200+delay and state['last_success']==100
        assert not due(state,201) and due(state,201,force=True)
    state=finish(state,True,'ok',300,jitter=0)
    assert state['failure_count']==0 and state['last_success']==300 and due(state,86700)


def chart(n):
    pitch=20;last=100+n*pitch
    image=np.full((last+150,600,3),(49,33,21),np.uint8)
    image[60:last+24,30:290]=(43,28,19);image[60:last+24,310:580]=(43,28,19)
    tables={s:[{s+'_rank':i,'y':100+i*pitch} for i in range(1,n+1)] for s in ('win','pick')}
    return image,tables


@pytest.mark.parametrize('n',[50,190,191,194,201,230])
def test_count_can_increase_or_decrease_without_previous_count(n):
    image,tables=chart(n)
    assert inspect_end(image,tables)['complete']


@pytest.mark.parametrize('lost',[1,2,5])
def test_both_tables_missing_tail_do_not_self_certify(lost):
    image,tables=chart(194)
    tables={k:v[:-lost] for k,v in tables.items()}
    assert not inspect_end(image,tables)['complete']


def test_cropped_image_and_unknown_artwork_are_pending():
    image,tables=chart(194)
    assert not inspect_end(image[:-140],tables)['complete']
    assert not inspect_end(np.full_like(image,255),tables)['complete']


def test_same_period_revision_requires_explicit_replacement():
    old={'period_end':'2026-11-04','image_sha256':'old'}
    new={'period_end':'2026-11-04','image_sha256':'new'}
    assert not newer(new,old)
    new['revision']={'status':'source-reviewed','replaces_sha256':'old','source_url':'https://www.taptap.cn/moment/123'}
    assert newer(new,old)
    assert not newer(dict(new,period_end='2026-10-21'),old)


def test_signed_snapshot_still_requires_valid_content():
    import json,hashlib
    from mjs_assistant.storage import ASSETS,read_json
    board=read_json(ASSETS/'board.json')
    raw=json.dumps({'schema_version':1,'boards':[board]}).encode()
    meta={'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    with pytest.raises(ValueError):validate_snapshot(raw,meta)


def test_waf_is_not_no_update(tmp_path):
    from mjs_assistant.updater import Updater
    from types import SimpleNamespace
    client=SimpleNamespace(get=lambda *a,**k:SimpleNamespace(status_code=200,raise_for_status=lambda:None,text='CF_APP_WAF',headers={}))
    with pytest.raises(ValueError,match='访问受限'):Updater(tmp_path,None,None)._html(client,'https://example.com')


def test_data_trickle_times_out_and_size_is_bounded(monkeypatch):
    import mjs_assistant.jiangce_update as module
    from types import SimpleNamespace
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def raise_for_status(self):pass
        raw=SimpleNamespace(read1=lambda *a,**k:b'x')
    monkeypatch.setattr(module.requests,'get',lambda *a,**k:Response())
    clock=iter([0,8,16])
    monkeypatch.setattr(module.time,'monotonic',lambda:next(clock))
    with pytest.raises(TimeoutError):module.get_bytes('test',8192)
    monkeypatch.setattr(module.time,'monotonic',lambda:0)
    with pytest.raises(ValueError):module.get_bytes('test',2)
