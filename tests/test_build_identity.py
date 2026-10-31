import json
import subprocess
from pathlib import Path

import pytest

from mjs_assistant import build_identity as bi

SHA = 'a' * 40


def stub_git(monkeypatch, root, *, dirty='', tag=SHA, untracked=''):
    calls = []
    def run(where, *args):
        calls.append(args)
        if args == ('rev-parse', '--show-toplevel'): return str(root)
        if args == ('rev-parse', 'HEAD'): return SHA
        if args == ('status', '--porcelain', '--untracked-files=no'): return dirty
        if args == ('status', '--porcelain'): return dirty or untracked
        return tag
    monkeypatch.setattr(bi, 'git', run)
    return calls


def test_source_clean_dirty_and_untracked(monkeypatch, tmp_path):
    stub_git(monkeypatch, tmp_path, untracked='?? screenshot.png')
    identity = bi.source_identity(tmp_path)
    assert identity.display == f'{bi.VERSION}-dev · gaaaaaaaa'
    assert identity.dirty is False
    stub_git(monkeypatch, tmp_path, dirty=' M main.py')
    assert '未提交修改' in bi.source_identity(tmp_path).display


@pytest.mark.parametrize('error', [FileNotFoundError(), subprocess.TimeoutExpired('git', .7)])
def test_unknown_git_is_safe(monkeypatch, tmp_path, error):
    def fail(*args): raise error
    monkeypatch.setattr(bi, 'git', fail)
    assert '提交未知' in bi.source_identity(tmp_path).display
    assert bi.source_identity(tmp_path).channel == 'development'


def test_enclosing_private_git_is_not_provenance(monkeypatch, tmp_path):
    monkeypatch.setattr(bi, 'git', lambda *args: str(tmp_path.parent))
    assert bi.source_identity(tmp_path).commit is None


def test_git_has_timeout_and_no_shell(monkeypatch, tmp_path):
    def run(args, **kwargs):
        assert args[:3] == ['git', '-C', str(tmp_path)]
        assert 0 < kwargs['timeout'] <= 1
        assert not kwargs.get('shell')
        return subprocess.CompletedProcess(args, 0, 'abc\n')
    monkeypatch.setattr(subprocess, 'run', run)
    assert bi.git(tmp_path, 'rev-parse', 'HEAD') == 'abc'


def test_cached_source_identity(monkeypatch, tmp_path):
    (tmp_path / '.git').mkdir()
    monkeypatch.setattr(bi, 'ROOT', tmp_path)
    calls=[]
    monkeypatch.setattr(bi, 'source_identity', lambda: calls.append(1) or bi.BuildIdentity(commit=SHA))
    bi.get_build_identity.cache_clear()
    try:
        assert bi.get_build_identity() == bi.get_build_identity()
        assert len(calls) == 1
    finally:
        bi.get_build_identity.cache_clear()


def test_frozen_metadata_does_not_call_git(monkeypatch, tmp_path):
    identity=bi.BuildIdentity(commit=SHA, dirty=False)
    bi.write_identity(tmp_path / bi.METADATA, identity)
    monkeypatch.setattr(bi.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(bi.sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr(bi, 'git', lambda *a: pytest.fail('Frozen app called Git'))
    bi.get_build_identity.cache_clear()
    try: assert bi.get_build_identity() == identity
    finally: bi.get_build_identity.cache_clear()


def test_exported_metadata_without_git(monkeypatch, tmp_path):
    identity=bi.BuildIdentity(commit=SHA,dirty=True)
    bi.write_identity(tmp_path/bi.METADATA, identity)
    monkeypatch.setattr(bi,'ROOT',tmp_path)
    bi.get_build_identity.cache_clear()
    try: assert bi.get_build_identity()==identity
    finally: bi.get_build_identity.cache_clear()


@pytest.mark.parametrize('changes', [dict(dirty=' M main.py'),dict(tag='b'*40),dict(untracked='?? new.py')])
def test_release_rejects_wrong_source(monkeypatch, tmp_path, changes):
    stub_git(monkeypatch,tmp_path,**changes)
    with pytest.raises(ValueError): bi.build_identity(tmp_path,release=True)


def test_release_payload_must_match_tagged_build(monkeypatch,tmp_path):
    stub_git(monkeypatch,tmp_path)
    expected=bi.build_identity(tmp_path,release=True)
    assert expected.channel=='release'
    path=tmp_path/'_internal'/bi.METADATA
    bi.write_identity(path,bi.BuildIdentity(commit=SHA,dirty=False))
    with pytest.raises(ValueError): bi.validate_release_payload(tmp_path,expected)
    bi.write_identity(path,bi.BuildIdentity(channel='release',commit='b'*40,dirty=False))
    with pytest.raises(ValueError): bi.validate_release_payload(tmp_path,expected)
    bi.write_identity(path,expected)
    assert bi.validate_release_payload(tmp_path,expected)==expected


def test_bad_metadata_never_claims_release(tmp_path):
    path=tmp_path/bi.METADATA
    path.write_text(json.dumps({'version':bi.VERSION,'channel':'release','commit':SHA,'dirty':True}))
    assert bi.read_identity(path) is None
    path.write_text('{bad')
    assert bi.read_identity(path) is None
