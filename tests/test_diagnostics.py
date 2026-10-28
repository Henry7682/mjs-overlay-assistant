import json
import time
from pathlib import Path
import zipfile
import numpy as np
import pytest
from mjs_assistant import diagnostics as d
from tools.replay_diagnostics import inspect

def wait_until(fn):
    until=time.monotonic()+3
    while time.monotonic()<until:
        if fn():return
        time.sleep(.02)
    assert fn()

def test_redaction_keeps_urls_and_drops_credentials():
    value=d.clean({'token':'secret','path':'C:'+r'\Users\Private\data.log','source':'https://example.com/source','note':'ghp_'+'a'*30})
    assert 'token' not in value and 'Private' not in value['path'] and value['source']=='https://example.com/source'
    assert 'ghp_' not in value['note']

def test_public_export_has_no_images_and_roundtrips(tmp_path):
    r=d.Recorder(tmp_path,enabled=False)
    try:
        r.event('query',request_id='request1',cards=[{'heroes':['甲','乙']}],password='not logged')
        image=r.root/'20260101-010101-abcdef'/'0000-game.png';image.parent.mkdir();image.write_bytes(b'private')
        parts=r.export(tmp_path/'export')
        result=inspect(parts[0])
        assert result['validated'] and any(x.get('request_id')=='request1' for x in result['events'])
        with zipfile.ZipFile(parts[0]) as z:
            assert not any(n.endswith('.png') for n in z.namelist())
            assert b'not logged' not in b''.join(z.read(n) for n in z.namelist())
    finally:r.close()

def test_only_target_sources_capture_and_disable_clears_ring(tmp_path):
    r=d.Recorder(tmp_path)
    try:
        image=np.ones((32,32,3),np.uint8)*127
        r.frame('desktop',image);assert r.q.empty()
        r.frame('game',image);wait_until(lambda:len(r.ring)==1)
        r.set_enabled(False);assert not r.ring
        r.frame('game',image);assert r.q.empty()
        r.trigger('disabled');r.close()
        assert not list(r.root.rglob('*.png'))
    finally:
        if not r.stopping.is_set():r.close()

def test_stale_ring_not_saved_and_failure_does_not_unwind(tmp_path,monkeypatch):
    r=d.Recorder(tmp_path)
    try:
        r.ring.append(('game',b'stale',time.monotonic()-31,{}));r.bytes=5
        r.trigger('new');assert not r.active['pending']
        monkeypatch.setattr(d,'_recorder',r)
        monkeypatch.setattr(r,'event',lambda *a,**k:(_ for _ in ()).throw(OSError('full disk')))
        d.event('safe')
    finally:r.close()

def test_export_parts_bounds_and_modified_bundle_rejected(tmp_path):
    parts=d.export_parts(tmp_path,{'a.txt':b'a'*200000,'b.txt':b'b'*200000},limit=350000)
    assert len(parts)==2 and all(p.stat().st_size<350000 for p in parts)
    assert all(inspect(p)['validated'] for p in parts)
    with zipfile.ZipFile(parts[0],'a') as z:z.writestr('unexpected.txt','x')
    with pytest.raises(ValueError):inspect(parts[0])

def test_clear_only_registered_incidents_and_stop_inflight_capture(tmp_path):
    r=d.Recorder(tmp_path)
    try:
        registered=r.root/'20260101-010101-abcdef';registered.mkdir()
        (registered/'incident.json').write_text(json.dumps({'kind':'mjs-diagnostic-incident','id':registered.name}))
        (registered/'0000-game.png').write_bytes(b'image')
        unregistered=r.root/'20260101-010101-aaaaaa';unregistered.mkdir()
        (unregistered/'incident.json').write_text('{}');(unregistered/'keep.png').write_bytes(b'keep')
        r.trigger('before clear');r.clear_incidents()
        assert not registered.exists() and (unregistered/'keep.png').read_bytes()==b'keep'
        assert r.active is None and not r.ring
    finally:r.close()

@pytest.mark.parametrize('expired',[False,True])
def test_prune_registered_incident_age_and_capacity(tmp_path,expired):
    import os
    r=d.Recorder(tmp_path,enabled=False)
    try:
        folder=r.root/'20260101-010101-abcdef';folder.mkdir()
        (folder/'incident.json').write_text(json.dumps({'kind':'mjs-diagnostic-incident','id':folder.name}))
        (folder/'0000-game.png').write_bytes(b'pixels')
        if expired:os.utime(folder,(time.time()-8*86400,)*2)
        r.prune(reserve=0 if expired else 500_000_000)
        assert not folder.exists()
    finally:r.close()
