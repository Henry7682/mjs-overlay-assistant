"""Reviewed traditional final glyph from the actual ranked selection nameplate."""
from pathlib import Path
from types import SimpleNamespace as NS
import cv2
import numpy as np
import pytest
from mjs_assistant.ocr import Names,Ocr,Word
from mjs_assistant.recognition import Detection,Recognizer,Stabilizer,profile_key
from mjs_assistant.storage import ASSETS


def test_full_name_variant_and_temporal_confirmation():
    names=Names();s=Stabilizer()
    for i,raw in enumerate(('公孙瓚','公孙瓒','公孙瓚')):
        assert names.resolve(raw)=='公孙瓒'
        d=Detection(names.resolve(raw),raw,(0,0,49,100),.84448,'roi5')
        assert s.update('selection',[d],i+1)[0].confirmed==(i>0)
    assert names.resolve('公孙衍') is None  # An unlisted name is never guessed as 瓒.
    assert Names(('公孙衍',)).resolve('公孙衍')=='公孙衍'
    for raw in ('公孙','瓚','公孙赞','公孙瓚技能'):
        assert names.resolve(raw) is None


@pytest.mark.parametrize('score,expected',[(.79,None),(.84448,'公孙瓒')])
def test_traditional_alias_still_requires_confidence(score,expected):
    r=Recognizer(NS(read=lambda image:[Word('公孙瓚',score,(17,20,23,100))]),Names())
    r.read_region=lambda key,image:[]
    profiles={profile_key('battle',1280,667):{'regions':[(.2,.2,.23,.35)]}}
    _,items,_=r.analyze(np.zeros((667,1280,3),np.uint8),scene_override='battle',profiles=profiles)
    assert items[0].name==expected


def test_real_nameplate_traditional_glyph_resolves_at_three_scales():
    if not all((ASSETS/'models'/n).exists() for n in ('det.onnx','rec.onnx','cls.onnx')):
        pytest.skip('Pinned OCR models required')
    crop=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/gongsunzan-nameplate.png',np.uint8),1)
    ocr=Ocr();names=Names();variant_seen=False
    for scale in (2,3,4):
        image=cv2.copyMakeBorder(cv2.resize(crop,None,fx=scale,fy=scale),24,24,24,24,cv2.BORDER_CONSTANT)
        words=ocr.read(image)
        assert len(words)==1 and words[0].confidence>=.80
        assert names.resolve(words[0].text)=='公孙瓒'
        variant_seen|=words[0].text=='公孙瓚'
    assert variant_seen
