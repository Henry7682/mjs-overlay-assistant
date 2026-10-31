from pathlib import Path
from unittest.mock import Mock
from contextlib import nullcontext

import pytest

from tools import start_source as source


def test_explicit_data_directory_is_kept(monkeypatch,tmp_path):
    monkeypatch.setenv('MJS_ASSISTANT_HOME',str(tmp_path/'data'))
    assert source.prepare()==tmp_path/'data'


def test_wrong_package_fails(monkeypatch,tmp_path):
    import mjs_assistant
    monkeypatch.setattr(mjs_assistant,'__file__',str(tmp_path/'__init__.py'))
    with pytest.raises(RuntimeError,match='Wrong source'): source.prepare()


def test_existing_instance_is_not_reopened(monkeypatch,tmp_path):
    QtCore=pytest.importorskip('PySide6.QtCore')
    monkeypatch.setattr(source,'prepare',lambda:tmp_path)
    monkeypatch.setattr(source.sys,'argv',['start_source.py'])
    from mjs_assistant import source_instance_guard as guard
    monkeypatch.setattr(guard, 'source_instance_guard', nullcontext)
    lock=Mock();lock.tryLock.return_value=False
    monkeypatch.setattr(QtCore,'QLockFile',lambda p:lock)
    monkeypatch.setattr(source.runpy,'run_path',lambda *a,**k:pytest.fail('Started duplicate assistant'))
    with pytest.raises(RuntimeError,match='already running'):source.main()


def test_cross_data_instance_blocks_before_running_source(monkeypatch, tmp_path):
    pytest.importorskip('PySide6.QtCore')
    from mjs_assistant import source_instance_guard as guard
    monkeypatch.setattr(source, 'prepare', lambda: tmp_path)
    monkeypatch.setattr(source.sys, 'argv', ['start_source.py'])
    def occupied(): raise RuntimeError('Assistant already running')
    monkeypatch.setattr(guard, 'source_instance_guard', occupied)
    monkeypatch.setattr(source.runpy, 'run_path', lambda *a, **k: pytest.fail('Started duplicate'))
    with pytest.raises(RuntimeError, match='already running'): source.main()
