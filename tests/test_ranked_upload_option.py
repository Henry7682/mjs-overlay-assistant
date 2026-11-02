from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from mjs_assistant.mini_dialogs import filename_edits,validate_image_path,dialog_state


def node(handle,ident,parent=None,visible=True):
    return NS(handle=handle,control_id=lambda:ident,parent=lambda:parent,
              is_visible=lambda:visible,is_enabled=lambda:True)


def test_nested_filename_host_excludes_shell_search_edit():
    dialog=node(1,0)
    host=node(2,1148,dialog);combo=node(3,100,host)
    target=node(4,1001,combo);search=node(5,1001,dialog)
    dialog.descendants=lambda **kw:[search,target]
    assert filename_edits(dialog)==[target]


def test_ambiguous_filename_edits_are_not_arbitrarily_chosen():
    dialog=node(1,0);host=node(2,1152,dialog)
    dialog.descendants=lambda **kw:[node(3,1001,host),node(4,1001,host)]
    assert len(filename_edits(dialog))==2


def test_owned_picker_with_nested_controls_and_no_file_type():
    from test_mini_dialogs import Windows
    gui=Windows();gui.rows={10:(123,'#32770',True,False)}
    gui.EnumChildWindows=lambda h,fn,arg:[fn(i,arg) for i in (1,2,1148)]
    gui.GetDlgCtrlID=lambda h:h
    assert dialog_state(123,gui)==([10],[10])


def test_missing_image_rejected_before_upload(tmp_path):
    with pytest.raises(RuntimeError,match='不存在'):validate_image_path(tmp_path/'missing.png')
    path=tmp_path/'中文 空格.png';path.write_bytes(b'png')
    assert validate_image_path(path)==str(path.resolve())


def test_ranked_search_snapshot_and_default_image_route():
    from test_ranked_retention import host
    from mjs_assistant.recognition import Detection
    names=('孙权','刘邦','白起','王异','周瑜','蒙恬','子婴','荀彧')
    for search in (False,True):
        w=host();w.config.setdefault('recommendation',{})['ranked_search']=search
        w.latest=dict(scene='selection',phase='selection',layout='ranked8',
            items=[Detection(n,n,(10,10,20,30),.99,str(i),True) for i,n in enumerate(names)],
            stamp=10.,frame=__import__('numpy').zeros((1080,1920,3),dtype='uint8'))
        w.update_selection(w.latest)
        assert w.snapshot.image_only is not search
        assert w.snapshot.can_request(True)
        assert w.snapshot.own_pool==names and w.snapshot.shared_pool_assumed
        if search:assert w.peak_auto_ready


def test_ranked_search_requires_full_local_pool_but_image_does_not():
    from dataclasses import replace
    from test_automatic_query import snapshot
    snap=snapshot('ranked_chuhan_2v2')
    assert snap.can_request(True)
    assert not replace(snap,image_only=False,own_pool=('孙权','刘邦')).can_request(True)


def test_setting_default_off_and_preserves_other_preferences(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from mjs_assistant.recommendation_ui import RecommendationSettings
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('mjs_assistant.mini_windows.mini_windows',lambda:[])
    dialog=RecommendationSettings({'automatic':False,'custom':'keep'})
    assert not dialog.ranked_search.isChecked()
    dialog.ranked_search.setChecked(True);dialog.save()
    assert dialog.result_settings['ranked_search']
    assert not dialog.result_settings['automatic'] and dialog.result_settings['custom']=='keep'
    restored=RecommendationSettings(dialog.result_settings)
    assert restored.ranked_search.isChecked()
    restored.close();dialog.close()
