import copy
from types import SimpleNamespace
import threading

import numpy as np
import pytest

from mjs_assistant import board_verification as module
from mjs_assistant.boards import assemble_rows, parse_words, validate_board
from mjs_assistant.ocr import Names, Word
from mjs_assistant.storage import BoardStore, read_json, write_json


def chart():
    names = Names()
    heroes = sorted(names.names)[:60]
    left = [dict(name=n, raw_name=n, win_rank=i, win_rate=90-i*.1,
                 y=200+i*35, confidence=.99, name_confidence=.99, rate_confidence=.99)
            for i, n in enumerate(heroes, 1)]
    right = [dict(name=r['name'], raw_name=r['raw_name'], pick_rank=r['win_rank'],
                  y=r['y'], confidence=.99, name_confidence=.99) for r in left]
    draft = dict(schema_version=2, mode_id='ranked_chuhan_2v2', mode='排位·楚汉争霸（二二对战）',
                 period_start='2026-10-22', period_end='2026-11-04', source_url='https://www.taptap.cn/moment/1',
                 raw_win_rows=left, raw_pick_rows=right, review_status='ocr')
    return assemble_rows(draft, names), names


def mock_reader(monkeypatch, original, fail=()):
    calls = []
    def read(image, ocr, names, side, rank, y, pitch, before):
        before(); calls.append((side, rank))
        if (side, rank) in fail:
            return None, []
        r = copy.deepcopy(original['raw_'+side+'_rows'][rank-1])
        return r, [copy.deepcopy(r), copy.deepcopy(r)]
    monkeypatch.setattr(module, 'reread_row', read)
    return calls


def test_missing_rank_is_read_not_inferred(monkeypatch):
    draft, names = chart(); original = copy.deepcopy(draft)
    draft['raw_pick_rows'].pop(0)
    calls = mock_reader(monkeypatch, original)
    result = module.verify_chart(draft, None, None, names)
    assert ('pick', 1) in calls and not validate_board(result)
    mock_reader(monkeypatch, original, fail={('pick', 1)})
    bad = module.verify_chart(draft, None, None, names)
    assert validate_board(bad) and bad['heroes'][0]['pick_rank'] is None


def test_new_name_requires_two_reads_in_each_table(monkeypatch):
    draft, names = chart()
    for side in ('win', 'pick'):
        draft['raw_'+side+'_rows'][3].update(name='新武将', raw_name='新武将')
    mock_reader(monkeypatch, draft)
    result = module.verify_chart(draft, None, None, names)
    assert not validate_board(result)
    assert result['auto_verification']['new_names'] == ['新武将']
    assert '新武将' not in names.names
    mock_reader(monkeypatch, draft, fail={('pick', 4)})
    result = module.verify_chart(draft, None, None, names)
    assert any('姓名待核对' in e for e in validate_board(result))


def test_cancel_and_layout_rejection_are_bounded(monkeypatch):
    draft, names = chart(); draft['raw_win_rows'][0]['confidence'] = .7
    mock_reader(monkeypatch, draft)
    def cancel(): raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError, match='cancelled'):
        module.verify_chart(draft, None, None, names, cancel)
    for row in draft['raw_win_rows']: row['confidence'] = .7
    calls = mock_reader(monkeypatch, draft)
    assert validate_board(module.verify_chart(draft, None, None, names))
    assert not calls


def test_duplicate_pick_names_cannot_pass():
    draft, names = chart()
    draft['raw_pick_rows'][1]['name'] = draft['raw_pick_rows'][0]['name']
    assert '出场榜存在重复姓名' in validate_board(assemble_rows(draft, names))


class RowOcr:
    def __init__(self, scores=(.8, .8), rates=('80.00%', '80.00%')):
        self.scores = iter(scores); self.rates = iter(rates); self.calls = 0
    def read(self, image):
        self.calls += 1
        return [Word('1', next(self.scores), (30,30,50,50)),
                Word('司马睿', .999, (150,30,250,50)),
                Word(next(self.rates), .999, (350,30,480,50))]


def test_repeated_low_rank_score_is_evidence_not_forged_confidence():
    ocr = RowOcr()
    row, reads = module.reread_row(np.zeros((500,1000,3), np.uint8), ocr, Names(), 'win', 1, 200, 35, lambda:None)
    assert row['confidence'] == .8 and len(reads) == 2 and ocr.calls == 2


def test_one_failed_scale_gets_only_one_extra_attempt():
    ocr = RowOcr((.9,.61,.8), ('80.00%',)*3)
    row, reads = module.reread_row(np.zeros((500,1000,3), np.uint8), ocr, Names(), 'win', 1, 200, 35, lambda:None)
    assert row and ocr.calls == 3


def test_conflicting_rates_and_wrong_rank_are_not_voted_away():
    image = np.zeros((500,1000,3), np.uint8)
    row, _ = module.reread_row(image, RowOcr(rates=('80.00%','80.01%')), Names(), 'win', 1, 200, 35, lambda:None)
    assert row is None
    row, _ = module.reread_row(image, RowOcr((.9,)*3, ('80.00%',)*3), Names(), 'win', 2, 200, 35, lambda:None)
    assert row is None


def test_generic_peak_identity_never_borrows_old_mode_evidence(monkeypatch):
    draft, names = chart();draft.update(mode_id=None, mode='未确认模式')
    mock_reader(monkeypatch, draft)
    result = module.verify_chart(draft, None, None, names)
    assert any('模式' in e for e in validate_board(result))


def test_install_results_are_isolated_and_do_not_reset_round(tmp_path):
    from mjs_assistant.app import MainWindow
    store = BoardStore(tmp_path)
    good = copy.deepcopy(store.board)
    bad = copy.deepcopy(good);bad.update(mode_id=None, mode='未确认模式')
    class Widget:
        def setEnabled(self, v): pass
        def setText(self, v): self.text = v
        def setToolTip(self, v): pass
        def update(self): pass
    fake = SimpleNamespace(check_btn=Widget(), import_btn=Widget(), data_status=Widget(),
        data_worker=SimpleNamespace(path=None),store=store,folder=tmp_path,overlay=Widget(),
        worker=SimpleNamespace(lock=threading.Lock(),extra=[]),current_mode=lambda:store.mode_id,
        update_board_label=lambda:None,tray=SimpleNamespace(showMessage=lambda *a:None))
    write_json(store.pending_path,good)
    MainWindow.data_done(fake,[bad,good],'check')
    assert read_json(store.path) == good
    assert read_json(store.previous) == good
    assert read_json(store.pending_path) is None
    assert '自动更新 1' in fake.data_status.text and '待核验 1' in fake.data_status.text
    # No configure/reset_round method: installation must leave current guides intact.


def test_install_exception_does_not_block_other_modes(tmp_path):
    from mjs_assistant.app import MainWindow
    from mjs_assistant.modes import PEAK_CHUHAN, board_mode
    store = BoardStore(tmp_path)
    boards = [copy.deepcopy(store.board), BoardStore(tmp_path, PEAK_CHUHAN).board]
    install = store.install
    def failing_first(board):
        if board_mode(board) == board_mode(boards[0]): raise OSError('locked')
        install(board)
    store.install = failing_first
    class W:
        def setEnabled(self,v): pass
        def setText(self,v): self.text=v
        def setToolTip(self,v): pass
        def update(self): pass
    fake = SimpleNamespace(check_btn=W(),import_btn=W(),data_status=W(),data_worker=SimpleNamespace(path=None),
        folder=tmp_path,store=store,current_mode=lambda:store.mode_id,update_board_label=lambda:None,
        worker=SimpleNamespace(lock=threading.Lock(),extra=[]),overlay=W(),tray=SimpleNamespace(showMessage=lambda *a:None))
    MainWindow.data_done(fake,boards,'check')
    assert read_json(tmp_path/'boards'/PEAK_CHUHAN/'current.json') == boards[1]
    assert '自动更新 1' in fake.data_status.text and '失败 1' in fake.data_status.text
