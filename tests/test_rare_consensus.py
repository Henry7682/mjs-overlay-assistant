from pathlib import Path

import cv2
import numpy as np
import pytest

from mjs_assistant.ocr import Names, Ocr, Word
from mjs_assistant.rare_names import candidate, confirm
from mjs_assistant.recognition import Recognizer, Stabilizer
from mjs_assistant.storage import ASSETS


def word(text, score):
    return Word(text, score, (0, 0, 30, 90))


@pytest.mark.parametrize('raw,score,second,second_score,expected', [
    ('左棻', .74583, '左棻', .75346, '左棻'),
    ('左菜', .62073, '左棻', .75, '左棻'),
    ('樊哙', .77424, '樊哙', .74941, '樊哙'),
    ('樊哈', .68556, '樊哙', .74941, '樊哙'),
    ('赵婕好', .92525, '赵婕妤', .91842, '赵婕妤'),
    ('赵婕好', .92525, '赵婕好', .88921, '赵婕妤'),
])
def test_observed_readings_require_two_agreeing_name_reads(raw, score, second, second_score, expected):
    result = confirm(raw, score, [word(second, second_score)], Names())
    assert result == (expected, min(score, second_score))
    if raw != expected:
        assert Names().resolve(raw) is None  # Never alters official board parsing.


@pytest.mark.parametrize('raw,score,second,second_score', [
    ('左菜', .9, '左慈', .99), ('左思', .99, '左棻', .9),
    ('赵婕', .999, '赵婕妤', .9), ('赵婕好技能', .99, '赵婕好', .99),
    ('左菜', .599, '左棻', .99), ('左菜', .67, '左棻', .67),
    ('樊哈', .9, '樊哙', .599), ('樊哈', float('nan'), '樊哙', .9),
    ('樊哈', .9, '樊哙', float('nan')),
])
def test_partial_conflicting_and_too_weak_readings_stay_unknown(raw, score, second, second_score):
    assert confirm(raw, score, [word(second, second_score)], Names()) is None


def test_future_canonical_name_never_replaced_by_reviewed_variant():
    assert candidate('左菜', Names(extra=['左菜'])) is None
    assert confirm('樊哈', .9, [], Names()) is None
    assert candidate('左慈', Names()) is None


@pytest.fixture(scope='module')
def ocr():
    if not all((ASSETS/'models'/n).exists() for n in ('det.onnx','rec.onnx','cls.onnx')):
        pytest.skip('Pinned local OCR models required')
    return Ocr()


@pytest.mark.parametrize('width', [2559, 2560, 1920, 1280])
def test_real_zhao_battle_name_and_two_frame_confirmation(ocr, width):
    frame = np.zeros((1334, 2559, 3), np.uint8)
    strip = cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/zhaojieyu-battle.png', np.uint8), 1)
    frame[106:250,747:844] = strip
    frame = cv2.resize(frame, (width, round(1334*width/2559)))
    r = Recognizer(ocr, Names()); s = Stabilizer()
    for tick in (1, 1.5):
        scene, items, _ = r.analyze(frame, 'battle', mode_id='ranked_chuhan_2v2')
        items = s.update(scene, items, now=tick)
        assert [d.name for d in items] == ['赵婕妤']
        assert items[0].confirmed == (tick == 1.5)
    assert items[0].method == 'rare_consensus'


@pytest.mark.parametrize('width,shift', [(2560,0),(1920,-1),(1920,1),(1280,-1),(1280,1)])
def test_tiny_resampling_shifts_do_not_break_rare_selection(ocr, width, shift):
    from test_ranked_rare_names import frame_from_strips, EXPECTED
    frame = frame_from_strips(1, width)
    frame = cv2.warpAffine(frame, np.float32([[1,0,shift],[0,1,shift]]), (frame.shape[1],frame.shape[0]))
    r = Recognizer(ocr, Names())
    scene, items, _ = r.analyze(frame, 'selection', mode_id='ranked_chuhan_2v2')
    assert [d.name for d in items] == EXPECTED[0]


def test_rare_names_in_the_newly_reported_slots(ocr):
    from test_ranked_rare_names import frame_from_strips, EXPECTED, XS
    frame = frame_from_strips(1, 2560)
    expected = EXPECTED[0].copy()
    for source, dest in ((6, 1), (7, 2)):
        a,c = int(XS[source]*2560), int((XS[source]+.019)*2560)
        b,d = int(XS[dest]*2560), int((XS[dest]+.019)*2560)
        source_strip, dest_strip = frame[:,a:c].copy(), frame[:,b:d].copy()
        frame[:,a:c] = cv2.resize(dest_strip, (c-a, frame.shape[0]))
        frame[:,b:d] = cv2.resize(source_strip, (d-b, frame.shape[0]))
        expected[source], expected[dest] = expected[dest], expected[source]
    _,items,_ = Recognizer(ocr,Names()).analyze(frame,'selection',mode_id='ranked_chuhan_2v2')
    assert [d.name for d in items] == expected
