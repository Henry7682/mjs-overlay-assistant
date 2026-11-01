"""Geometry checks plus isolated real name strips, not full private screenshots."""
from pathlib import Path
import cv2
import numpy as np
import pytest
from mjs_assistant.identity_layout import mingdao_nine_grid, mingdao_nine_regions, IdentityNameLocator, add_identity_regions
from mjs_assistant.recognition import Recognizer, Stabilizer, profile_key
from mjs_assistant.region_geometry import center_x
from mjs_assistant.ocr import Ocr, Names, Word
from mjs_assistant.storage import ASSETS
from mjs_assistant.modes import MINGDAO


def panel(width=2560, height=1334, lower=6):
    frame=np.full((height,width,3),215,np.uint8)
    for count,y in ((3,.12),(lower,.39)):
        for i in range(count):
            x=.443-.112*(count-1)/2+i*.112
            frame[int(height*y):int(height*(y+.25)),int(width*center_x(x,width,height)):int(width*center_x(x+.098,width,height))]=(50,80,110)
    return frame


@pytest.mark.parametrize('size',[(1280,667),(1920,1080),(2560,1334)])
def test_identity_nine_grid_and_old_six_are_distinct(size):
    assert mingdao_nine_grid(panel(*size))
    assert not mingdao_nine_grid(panel(*size,lower=3))
    assert len(mingdao_nine_regions())==9


def test_missing_card_and_popup_do_not_confirm_nine():
    frame=panel();h,w=frame.shape[:2]
    frame[int(h*.39):int(h*.64),int(w*.387):int(w*.485)]=215
    assert not mingdao_nine_grid(frame)
    frame=panel();frame[int(h*.4):int(h*.65),int(w*.3):int(w*.7)]=30
    assert not mingdao_nine_grid(frame)


def test_nine_layout_ignores_legacy_calibration_but_accepts_own():
    class EmptyOcr:
        def read(self,image):return []
    r=Recognizer(EmptyOcr(),Names());frame=panel();key=profile_key('selection',2560,1334)
    r.analyze(frame,'selection',{key:{'regions':[(0,0,.01,.01)]}},MINGDAO)
    assert r.layout=='identity3_6' and len(r._names_cache[0][3])==9
    r.analyze(frame,'selection',{key+':identity3_6':{'regions':[(0,0,.01,.01)]}},MINGDAO)
    assert len(r._names_cache[0][3])==1


def test_real_mingdao_nine_names_confirm_twice():
    if not all((ASSETS/'models'/name).exists() for name in ('det.onnx','rec.onnx','cls.onnx')):
        pytest.skip('Restore pinned OCR models')
    strips=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/mingdao-nine-names.png',np.uint8),1)
    frame=panel();h,w=frame.shape[:2]
    for i,(a,b,c,d) in enumerate(mingdao_nine_regions()):
        x,y,x2,y2=int(a*w),int(b*h),int(c*w),int(d*h)
        frame[y:y2,x:x2]=strips[:y2-y,i*72:i*72+x2-x]
    r=Recognizer(Ocr(),Names());s=Stabilizer()
    r.read_region=lambda key,image:[Word('武将选择',1,(0,0,100,30))] if key=='header' else []
    for _ in range(2):
        scene,items,_=r.analyze(frame,mode_id=MINGDAO);items=s.update(scene,items)
    assert r.layout=='identity3_6'
    assert [d.name for d in items if d.confirmed]=='曹丕 孙策 曹操 姜维 钟离眜 贾诩 袁绍 华佗 平原君'.split()
    assert Names().resolve('钟离昧')=='钟离眜'
    assert Names().resolve('钟离未知') is None


def test_wide_locator_rejects_horizontal_prose_and_reuses_positions():
    class FakeOcr:
        def __init__(self):self.calls=0
        def read(self,image):
            self.calls+=1
            if self.calls%2==0:return []
            return [Word('孙策',.99,(300,70,330,140)),
                    Word('曹丕',.99,(100,50,170,80)), # horizontal prose
                    Word('未知字',.70,(400,90,430,180))] # position only
    f=np.full((1334,2560,3),80,np.uint8);o=FakeOcr();locator=IdentityNameLocator()
    first=locator.locate(f,('mode','layout'),o,Names(),now=0)
    assert len(first)==2 and o.calls==2
    assert locator.locate(f,('mode','layout'),o,Names(),now=10)==first and o.calls==2
    changed=f.copy();changed[:,:1280]=215
    locator.locate(changed,('mode','layout'),o,Names(),now=11)
    assert o.calls==4
    locator.locate(changed,('mode','another-layout'),o,Names(),now=11.1)
    assert o.calls==6
    assert add_identity_regions(first,first)==first


def test_wide_locator_needs_adjacent_portrait():
    class TextOnPaper:
        def read(self,image):return [Word('孙策',.99,(300,70,330,140))]
    assert not IdentityNameLocator().locate(np.full((1334,2560,3),215,np.uint8),'key',TextOnPaper(),Names())


def test_new_position_outside_default_rois_is_confirmed():
    if not (ASSETS/'models/rec.onnx').exists():pytest.skip('Restore pinned models')
    strips=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/mingdao-nine-names.png',np.uint8),1)
    f=np.full((1334,2560,3),215,np.uint8)
    a,b=int(.39*2560),int(.28*1334)
    f[b:b+260,a:a+240]=(50,80,110)
    f[b:b+145,a:a+72]=strips[:,72:144] # real 孙策 at synthetic, nonstandard coordinates
    r=Recognizer(Ocr(),Names());s=Stabilizer()
    r.read_region=lambda key,image:[Word('武将选择',1,(0,0,100,30))] if key=='header' else []
    for _ in range(2):
        scene,items,_=r.analyze(f,mode_id=MINGDAO);items=s.update(scene,items)
    assert [d.name for d in items if d.confirmed]==['孙策']
