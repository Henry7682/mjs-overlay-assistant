import json
from pathlib import Path

import pytest
from mjs_assistant.launcher_library import refresh_committed_library


def installation(tmp_path):
    root=tmp_path/'installed';payload=root/'versions/1.0.6'
    (root/'release').mkdir(parents=True);(payload/'release').mkdir(parents=True)
    (root/'current.json').write_text('{"version":"1.0.6"}')
    (root/'release/Release.ps1').write_bytes(b'old compatible helper')
    (payload/'release/Release.ps1').write_bytes(b'# MJS_DOWNLOAD_LIBRARY: 2\n# new helper\n')
    for directory in (root,payload):
        (directory/'release/public-key.xml').write_bytes(b'same public key')
    (root/'data').mkdir();(root/'data/settings.json').write_text('{"user":true}')
    return root,payload/'MjsOverlay.exe'


def test_old_launcher_migration_after_commit_preserves_data(tmp_path):
    root,exe=installation(tmp_path)
    assert refresh_committed_library(exe,'1.0.6')=='refreshed'
    assert (root/'release/Release.ps1.previous').read_bytes()==b'old compatible helper'
    assert (root/'release/Release.ps1').read_bytes()==(exe.parent/'release/Release.ps1').read_bytes()
    assert refresh_committed_library(exe,'1.0.6')=='unchanged'
    assert json.loads((root/'data/settings.json').read_text())=={'user':True}


@pytest.mark.parametrize('case',['uncommitted','journal','key','legacy','source'])
def test_no_refresh_before_commit_or_outside_installation(tmp_path,case):
    root,exe=installation(tmp_path)
    if case=='uncommitted':(root/'current.json').write_text('{"version":"1.0.5"}')
    if case=='journal':(root/'pending-update.json').write_text('{}')
    if case=='key':(root/'release/public-key.xml').write_bytes(b'other')
    if case=='legacy':(exe.parent/'release/Release.ps1').write_bytes(b'old payload')
    if case=='source':exe=tmp_path/'app/python.exe'
    assert refresh_committed_library(exe,'1.0.6')!='refreshed'
    assert (root/'release/Release.ps1').read_bytes()==b'old compatible helper'


def test_failed_atomic_replace_leaves_old_library_usable(tmp_path,monkeypatch):
    from mjs_assistant import launcher_library
    root,exe=installation(tmp_path)
    original=launcher_library.os.replace
    def fail(source,target):
        if Path(target).name=='Release.ps1':raise PermissionError('read only')
        return original(source,target)
    monkeypatch.setattr(launcher_library.os,'replace',fail)
    with pytest.raises(PermissionError):refresh_committed_library(exe,'1.0.6')
    assert (root/'release/Release.ps1').read_bytes()==b'old compatible helper'
    assert not list((root/'release').glob('*.tmp'))
