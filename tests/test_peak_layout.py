from pathlib import Path
import cv2
import numpy as np
import pytest
from mjs_assistant.peak_layout import detect_draft_layout, draft_count, draft_regions
from mjs_assistant.region_geometry import center_x
from mjs_assistant.guide_state import PeakDraft
from mjs_assistant.recognition import Recognizer, Stabilizer, Detection
from mjs_assistant.ocr import Ocr, Names, Word
from mjs_assistant.storage import ASSETS


def panel(count, width=1280, height=667):
    """Synthetic paper/card geometry only; never presented as a live sample."""
    frame=np.full((height,width,3),215,np.uint8)
    for n,y in ((count//2,.15),((count+1)//2,.40)):
        for i in range(n):
            x=.459-.112*(n-1)/2+i*.112
            frame[int(height*y):int(height*(y+.225)),int(width*center_x(x,width,height)):int(width*center_x(x+.084,width,height))]=(50,80,110)
    return frame


@pytest.mark.parametrize('count',range(6,14))
@pytest.mark.parametrize('size',[(1280,667),(1920,1080),(2560,1334),(2560,1440)])
def test_draft_extent_counts_six_through_thirteen(count,size):
    image=panel(count,*size)
    assert detect_draft_layout(image)==f'draft{count}'
    assert len(draft_regions(f'draft{count}'))==count
    assert not draft_count('draft5') and not draft_count('draft14')


def test_missing_inner_portrait_or_tooltip_does_not_invent_smaller_roster():
    image=panel(11)
    image[100:250,570:700]=215
    assert detect_draft_layout(image) is None
    image=panel(11);image[100:440,500:900]=40
    assert detect_draft_layout(image) is None
    assert detect_draft_layout(np.full_like(image,215)) is None


@pytest.mark.parametrize('count',range(6,14))
def test_peak_filter_never_uses_late_ocr_after_transition_window(count):
    p=PeakDraft();pool=tuple(f'将{i}' for i in range(14))
    p.update('ban','ban14',pool,14,0)
    for now in (1,3,5):p.update('selection',f'draft{count}',pool[:count-1],count,now)
    assert not p.frozen
    p.update('selection',f'draft{count}',pool[:count],count,6)
    assert not p.frozen
    p.update('selection',f'draft{count}',pool[:count],count,7.5)
    assert not p.frozen and p.auto_closed and not p.excluded
    p.update('selection',f'draft{count}',pool[:2],2,9)
    assert not p.excluded


def test_slow_peak_frames_confirm_but_long_gap_does_not():
    s=Stabilizer();d=Detection('鲁仲连','鲁仲连',(0,0,10,100),1,'roi0')
    assert not s.update('selection',[d],1,max_gap=4.5)[0].confirmed
    assert s.update('selection',[d],4.4,max_gap=4.5)[0].confirmed
    assert not s.update('selection',[d],9,max_gap=4.5)[0].confirmed


def test_real_three_glyph_nameplates_keep_top_strokes():
    if not all((ASSETS/'models'/name).exists() for name in ('det.onnx','rec.onnx','cls.onnx')):
        pytest.skip('Restore pinned models for OCR fixture test')
    strips=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/peak-nameplates.png',np.uint8),1)
    frame=panel(11,2560,1334)
    for i,x in enumerate((.345,.681)):
        a,c=int(x*2560),int((x+.019)*2560)
        frame[244:373,a:c]=strips[:,i*50:i*50+c-a]
    r=Recognizer(Ocr(),Names())
    def landmarks(key,image):
        label={'header':'武将选择','footer':'请选择本局要使用的武将'}.get(key)
        return [Word(label,1,(0,0,100,30))] if label else []
    r.read_region=landmarks
    scene,items,_=r.analyze(frame,mode_id='peak_chuhan_2v2')
    assert scene=='selection' and r.layout=='draft11'
    assert {d.name for d in items if d.name}=={'鲁仲连','秦舞阳'}
    assert Names().resolve('晋仲连') is None and Names().resolve('奈舞阳') is None


def test_thirteen_selection_landmark_overrides_coarse_outer_card_probe():
    from mjs_assistant.recognition import peak_phase
    # The seven-card bottom row can occupy the old ban-grid outer probes.
    assert peak_phase('请等待其他玩家选择武将', True, '', draft_layout='draft13') == ('selection', 'draft13')
    assert peak_phase('请禁止武将', True, '', draft_layout='draft13') == ('ban', 'ban14')
    assert peak_phase('', True, '', draft_layout='draft13') == ('transition', 'ban14')
    assert peak_phase('请选择本局要使用的武将', False, '', draft_layout=None) == ('unknown', 'unknown')
    assert detect_draft_layout(panel(14, 2560, 1440)) is None


def test_thirteen_filter_keeps_raw_cache_and_filters_late_guides_once():
    from mjs_assistant.guide_state import RoundGuideCache
    from mjs_assistant.modes import PEAK_CHUHAN
    p=PeakDraft(); pool=tuple(f'将{i}' for i in range(14))
    p.update('ban', 'ban14', pool, 14, 0)
    p.update('selection', 'draft13', (), 13, 1)
    p.update('selection', 'draft13', pool[:13], 13, 2.6)
    assert p.frozen and p.excluded == {pool[13]}
    good={'heroes':[pool[0],pool[1]]}; banned={'heroes':[pool[0],pool[13]]}
    cache=RoundGuideCache(PEAK_CHUHAN, 'round', raw_cards=(good,banned))
    cache.freeze(p.excluded)
    assert cache.visible_cards() == (good,) and len(cache.raw_cards)==2
    p.update('selection', 'draft13', pool[:2], 2, 9)
    p.update('battle', 'default', pool[:2], 2, 10)
    cache.freeze({pool[1]})
    cache.raw_cards += ({'heroes':[pool[2],pool[13]]},)
    assert p.excluded==cache.excluded=={pool[13]} and cache.visible_cards()==(good,)


@pytest.mark.parametrize('count', [6, 9, 11, 12, 13])
@pytest.mark.parametrize('size', [(1920, 1080), (2560, 1440)])
def test_dimmed_hover_panel_keeps_layout_but_tooltip_remains_unknown(count, size):
    image=(panel(count,*size).astype(float)*.52).astype(np.uint8)
    assert detect_draft_layout(image)==f'draft{count}'
    h,w=image.shape[:2]
    image[int(h*.12):int(h*.65),int(w*.30):int(w*.70)]=25
    assert detect_draft_layout(image) is None
