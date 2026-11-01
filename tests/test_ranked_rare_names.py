from pathlib import Path

import cv2
import numpy as np
import pytest

from mjs_assistant.ocr import Names, Ocr
from mjs_assistant.recognition import Recognizer, Stabilizer
from mjs_assistant.storage import ASSETS
from mjs_assistant.nameplate_match import verify_ranked_name

XS = (.092, .194, .296, .398, .522, .624, .726, .828)
EXPECTED = [
    ['周勃', '子婴', '赵姬', '王异', '刘邦', '桑弘羊', '左棻', '樊哙'],
    ['魏延', '杨艳', '卫玠', '司马相如', '蔡文姬', '赵云', '周勃', '吕蒙'],
]


def frame_from_strips(index, width=2559):
    strips = cv2.imdecode(np.fromfile(Path(__file__).parent / f'fixtures/ranked-rare-{index}.png', np.uint8), 1)
    frame = np.zeros((1334, 2559, 3), np.uint8)
    offset = 0
    for x in XS:
        a, c = int(x * 2559), int((x + .019) * 2559)
        frame[300:440, a:c] = strips[:, offset:offset + c - a]
        offset += c - a
    if width != 2559:
        frame = cv2.resize(frame, (width, round(1334 * width / 2559)))
    return frame


@pytest.fixture(scope='module')
def ocr():
    if not all((ASSETS / 'models' / n).exists() for n in ('det.onnx', 'rec.onnx', 'cls.onnx')):
        pytest.skip('Pinned local OCR models required')
    return Ocr()


@pytest.mark.parametrize('width', [2559, 1920, 1280])
@pytest.mark.parametrize('index', [1, 2])
def test_real_ranked_name_strips_at_three_sizes(ocr, index, width):
    frame = frame_from_strips(index, width)
    recognizer = Recognizer(ocr, Names())
    recognizer.read_region = lambda key, image: []
    stable = Stabilizer()
    scene, items, _ = recognizer.analyze(frame, scene_override='selection', mode_id='ranked_chuhan_2v2')
    assert [d.name for d in items] == EXPECTED[index - 1]
    first = stable.update(scene, items, now=1)
    assert not any(d.confirmed for d in first)
    scene, items, _ = recognizer.analyze(frame, scene_override='selection', mode_id='ranked_chuhan_2v2')
    assert all(d.confirmed for d in stable.update(scene, items, now=1.5))
    if width == 1280:
        rare = '左棻' if index == 1 else '卫玠'
        item = next(d for d in items if d.name == rare)
        assert item.method == 'glyph_verified'
        assert item.raw != rare  # Keep the failed OCR spelling for diagnostics.


@pytest.mark.parametrize('size',[(1920,1080),(2560,1440)])
@pytest.mark.parametrize('index',[1,2])
def test_rare_strips_with_center_height_conversion_and_padding(ocr,index,size):
    # Synthetic placement of existing real glyph strips, not a new live sample.
    w,h=size;scale=h/1334;offset=(w-2559*scale)/2
    frame=cv2.warpAffine(frame_from_strips(index),np.float32([[scale,0,offset],[0,scale,0]]),(w,h))
    # Keep the real rare-consensus path: mocking every read_region call would
    # disable precisely the independent verification this regression covers.
    recognizer=Recognizer(ocr,Names())
    _,items,_=recognizer.analyze(frame,scene_override='selection',mode_id='ranked_chuhan_2v2')
    assert [d.name for d in items]==EXPECTED[index-1]


def box(width, slot):
    return (int(XS[slot] * width), 0, int((XS[slot] + .019) * width), 0)


def test_wrong_spelling_alone_never_becomes_a_dictionary_alias():
    names = Names()
    for raw in ('左菜', '左菲', '左柒', '樊哈', '卫盼', '卫酚', '卫', '马相如'):
        assert names.resolve(raw) is None


def test_all_other_names_reject_even_with_a_matching_ocr_prefix():
    names = Names()
    for index in (1, 2):
        frame = frame_from_strips(index)
        for slot, name in enumerate(EXPECTED[index - 1]):
            if name in ('左棻', '樊哙', '卫玠'):
                continue
            for raw in ('左菜', '樊哈', '卫盼'):
                assert verify_ranked_name(frame, box(2559, slot), raw, names) is None


@pytest.mark.parametrize('side', ['upper', 'lower'])
def test_occluded_half_name_cannot_match(side):
    frame = frame_from_strips(2)
    a, _, c, _ = box(2559, 2)
    start, end = (344, 379) if side == 'upper' else (379, 414)
    frame[start:end, a:c] = 0
    assert verify_ranked_name(frame, box(2559, 2), '卫盼', Names()) is None


def test_short_or_wrong_prefix_and_missing_reference_fail_closed(monkeypatch):
    frame = frame_from_strips(2)
    for raw in ('卫', '赵盼', '卫盼技能', ''):
        assert verify_ranked_name(frame, box(2559, 2), raw, Names()) is None
    import mjs_assistant.nameplate_match as module
    monkeypatch.setattr(module, 'references', lambda: {n: [] for n in module.REFERENCES})
    assert verify_ranked_name(frame, box(2559, 2), '卫盼', Names()) is None


def test_conflicting_reference_images_stay_pending(monkeypatch):
    import mjs_assistant.nameplate_match as module
    same = module.references()['卫玠']
    monkeypatch.setattr(module, 'references', lambda: {n: same for n in module.REFERENCES})
    assert verify_ranked_name(frame_from_strips(2), box(2559, 2), '卫盼', Names()) is None


def test_same_surname_other_hero_is_not_replaced():
    frame = frame_from_strips(1)
    old = cv2.imdecode(np.fromfile(Path(__file__).parent / 'fixtures/ranked-nameplates.png', np.uint8), 1)
    a, _, c, _ = box(2559, 6)
    frame[300:440, a:c] = 0
    frame[300:430, a:c] = old[:, 6 * 49:6 * 49 + c - a]  # 左思
    assert verify_ranked_name(frame, box(2559, 6), '左菜', Names()) is None


def test_calibration_excludes_default_layout_glyph_verifier(ocr, monkeypatch):
    import mjs_assistant.nameplate_match as module
    from mjs_assistant.recognition import profile_key
    def forbidden(*args):
        raise AssertionError('Calibrated regions must not use default-layout templates')
    monkeypatch.setattr(module, 'verify_ranked_name', forbidden)
    frame = frame_from_strips(1)
    recognizer = Recognizer(ocr, Names())
    recognizer.read_region = lambda key, image: []
    profiles = {profile_key('selection', 2559, 1334): {'regions': [(XS[7], .246, XS[7] + .019, .321)]}}
    recognizer.analyze(frame, 'selection', profiles, 'ranked_chuhan_2v2')
