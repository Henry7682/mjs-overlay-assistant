from dataclasses import replace

import numpy as np

from mjs_assistant.frame_timing import frame_fresh
from mjs_assistant.recognition import Recognizer, Stabilizer, Detection
from mjs_assistant.ocr import Names, Word
from mjs_assistant.modes import PEAK_CHUHAN


def test_slow_result_survives_next_pass_but_not_a_stalled_worker():
    data={'stamp':100, 'processed_at':102.6, 'seconds':2.6}
    assert frame_fresh(data,True,now=105.2)
    assert not frame_fresh(data,True,now=106.1)
    # A freshly delivered result from an obsolete capture remains obsolete.
    assert not frame_fresh(dict(data,stamp=90),True,now=102.7)
    assert not frame_fresh(data,True,now=102)


def test_fast_results_and_legacy_timestamps_remain_bounded():
    data={'stamp':100,'processed_at':100.5,'seconds':.5}
    assert frame_fresh(data,now=101.5)
    assert not frame_fresh(data,now=102.1)
    assert frame_fresh({'stamp':100},True,now=104)
    assert not frame_fresh({'stamp':100},False,now=104)
    assert not frame_fresh(None,now=100)


def test_same_canonical_name_stays_confirmed_but_replacement_does_not():
    s=Stabilizer();d=Detection('芈八子','芈八子',(0,0,10,100),.99,'roi0')
    assert not s.update('selection',[d],0)[0].confirmed
    assert s.update('selection',[replace(d,raw='羋八子')],.5)[0].confirmed
    assert s.update('selection',[d],1)[0].confirmed
    other=replace(d,name='白起',raw='白起')
    assert not s.update('selection',[other],1.5)[0].confirmed
    assert s.update('selection',[other],2)[0].confirmed
    assert s.update('selection',[],2.5)==[]
    assert not s.update('selection',[other],3)[0].confirmed


def test_identical_pixels_reuse_ocr_but_changed_pixels_are_reread(monkeypatch):
    class Reader:
        calls=0
        def read(self,image):
            self.calls+=1
            return [Word(str(self.calls),1,(0,0,1,1))]
    reader=Reader();r=Recognizer(reader,Names());pixels=np.zeros((20,20,3),np.uint8)
    first=r.read_region('header',pixels)
    monkeypatch.setattr('mjs_assistant.recognition.time.monotonic',lambda:9999999999)
    assert r.read_region('header',pixels.copy())==first and reader.calls==1
    pixels[0,0,0]=1
    assert r.read_region('header',pixels)!=first and reader.calls==2


def test_round_landmark_keeps_one_visible_hero_without_inventing_hidden_heroes():
    class Reader:
        def read(self,image):return [Word('白起',.99,(20,20,55,85))]
    r=Recognizer(Reader(),Names())
    r.read_region=lambda key,image: [Word('第1轮',1,(0,0,80,20))] if key=='header' else []
    r.read_battle_badges=lambda frame:{}
    frame=np.zeros((667,1280,3),np.uint8)
    scene,items,_=r.analyze(frame,mode_id=PEAK_CHUHAN)
    assert scene=='battle' and [d.name for d in items]==['白起']
    # Without an actual battle landmark, a name-like word is not a scene.
    r.read_region=lambda key,image:[]
    assert r.analyze(frame,mode_id=PEAK_CHUHAN)[:2]==('unknown',[])
