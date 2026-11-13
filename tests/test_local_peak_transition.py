from dataclasses import replace
from types import SimpleNamespace

import pytest

from mjs_assistant.guide_controller import GuideController, local_source
from mjs_assistant.guide_source import selected_source, ATTRIBUTION
from mjs_assistant.guide_state import PeakDraft
from mjs_assistant.modes import PEAK_CHUHAN
from mjs_assistant.recognition import Detection, peak_phase
from mjs_assistant.recommendations import ModeContext, SelectionSnapshot
from tests.test_ranked_retention import host, data


def test_fourteen_selection_is_not_a_ban_phase():
    for geometry in ('draft14',):
        assert peak_phase('请选择本局要使用的武将', True, '', draft_layout=geometry) == ('selection', 'draft14')
        assert peak_phase('请禁止武将', True, '', draft_layout=geometry) == ('ban', 'ban14')
    assert peak_phase('', True, '', draft_layout='draft14') == ('transition', 'ban14')
    # Outer-card probes also light up in 13-card layouts; they are not a count.
    assert peak_phase('本局要使用', True, '', draft_layout=None) == ('transition', 'ban14')
    p=PeakDraft(); names=tuple(f'将{i}' for i in range(14))
    p.update('ban','ban14',names,14,0)
    p.update('selection','ban14',names,14,1)
    p.update('selection','draft14',names,14,3)
    assert p.frozen and p.selection_count==14 and not p.excluded
    p.update('selection','draft9',names[:9],9,5)
    assert not p.excluded


def test_battle_ends_pending_filter_without_guessing():
    p=PeakDraft();names=tuple(f'将{i}' for i in range(14))
    p.update('ban','ban14',names,14,0)
    p.update('selection','draft11',names[:10],11,1)
    p.update('battle','default',names[:2],2,20)
    p.update('selection','draft11',names[:11],11,21)
    assert not p.frozen and not p.excluded and p.auto_closed


@pytest.mark.parametrize('count',[8,11,14])
def test_local_cache_filters_once_and_survives_lock_and_dropout(tmp_path,monkeypatch,count):
    window=host(mode=PEAK_CHUHAN);window.config['recommendation']['source']='jiangce'
    window.folder=tmp_path;window.enabled=True
    pool=tuple(f'将{i}' for i in range(14))
    cards=({'heroes':[pool[0],pool[1]]}, {'heroes':[pool[0],pool[-1]]})
    class Book:
        date='test'
        calls=0
        def selection(self,own,ally,locked=None):
            self.calls+=1
            return tuple(c for c in cards if set(c['heroes'])<=set(own)|set(ally))
    window.local_book=Book();window.book_round=window.game_id
    def emit(phase,layout,names,now,lock=None):
        monkeypatch.setattr('mjs_assistant.guide_controller.time.monotonic',lambda:now)
        frame=data();frame.update(phase=phase,layout=layout,stamp=now,ally_locked=lock,
            items=[Detection(n,n,(0,0,20,100),1,f'roi{i}',True) for i,n in enumerate(names)])
        window.update_selection(frame)
    emit('ban','ban14',pool,0)
    assert window.guide_cache.raw_cards==cards
    emit('selection',f'draft{count}',(),1)
    emit('selection',f'draft{count}',pool[:count-1],3.3)
    assert not window.guide_cache.frozen
    emit('selection',f'draft{count}',pool[:count],12.5)
    assert window.guide_cache.frozen and window.guide_cache.excluded==set(pool[count:])
    visible=window.guide_cache.visible_cards()
    assert len(visible)==(2 if count==14 else 1)
    calls=window.local_book.calls
    emit('selection',f'draft{count}',pool[2:4],20,lock=pool[2])
    emit('selection',f'draft{count}',('迟到的错误姓名',),22)
    assert window.guide_cache.visible_cards()==visible
    assert window.guide_cache.raw_cards==cards  # Original banned guides remain cached.
    assert window.local_book.calls==calls


def test_default_local_and_explicit_online_choice_are_consistent(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from mjs_assistant.recommendation_ui import RecommendationSettings
    monkeypatch.setattr('mjs_assistant.mini_windows.mini_windows',lambda:[])
    app=QApplication.instance() or QApplication([])
    for config,expected in (({},'jiangce'),({'source':'wechat'},'wechat'),({'source':'jiangce'},'jiangce')):
        controller=SimpleNamespace(config={'recommendation':config})
        assert local_source(controller)==(expected=='jiangce')
        dialog=RecommendationSettings(config)
        assert dialog.source.currentData()==selected_source(config)==expected
        assert ATTRIBUTION in dialog.source.currentText() and '将策' not in dialog.source.currentText()
        dialog.save()
        assert dialog.result_settings['source']==expected
        dialog.close()
