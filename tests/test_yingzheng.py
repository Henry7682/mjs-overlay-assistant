"""Narrow correction for a reviewed real nameplate; no general fuzzy mapping."""
from pathlib import Path
from types import SimpleNamespace as NS
import cv2
import numpy as np
import pytest
from mjs_assistant.ocr import Names, Ocr, Word
from mjs_assistant.recognition import Detection, Recognizer, Stabilizer, profile_key
from mjs_assistant.storage import ASSETS


def test_only_observed_full_name_is_corrected():
    names=Names()
    assert names.resolve('赢政')==names.resolve('嬴政')=='嬴政'
    assert names.resolve('侯嬴')=='侯嬴'
    for raw in ('赢','政','羸政','赢异','侯赢','赢政技能'):
        assert names.resolve(raw) is None
    # Alternate OCR spellings must not repeatedly lose temporal confirmation.
    s=Stabilizer()
    for index,raw in enumerate(('嬴政','赢政','嬴政')):
        d=Detection(names.resolve(raw),raw,(0,0,48,100),.9,'roi4')
        assert s.update('selection',[d],index+1)[0].confirmed==(index>0)


@pytest.mark.parametrize('score,expected',[(.79,None),(.86,'嬴政')])
def test_alias_does_not_bypass_confidence_gate(score,expected):
    r=Recognizer(NS(read=lambda image:[Word('赢政',score,(17,20,23,100))]),Names())
    r.read_region=lambda key,image:[]
    profiles={profile_key('battle',1280,667):{'regions':[(.2,.2,.23,.35)]}}
    _,items,_=r.analyze(np.zeros((667,1280,3),np.uint8),scene_override='battle',profiles=profiles)
    assert items[0].name==expected


def test_real_nameplate_misread_is_resolved_without_changing_ocr_model():
    if not all((ASSETS/'models'/name).exists() for name in ('det.onnx','rec.onnx','cls.onnx')):
        pytest.skip('Restore pinned local OCR models before image regression')
    crop=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/yingzheng-nameplate.png',np.uint8),1)
    ocr=Ocr();names=Names();misread_seen=False
    for scale in (1,2,4):
        image=cv2.copyMakeBorder(cv2.resize(crop,None,fx=scale,fy=scale),24,24,24,24,cv2.BORDER_CONSTANT)
        words=ocr.read(image)
        assert len(words)==1 and words[0].confidence>=.80
        assert names.resolve(words[0].text)=='嬴政'
        misread_seen |= words[0].text=='赢政'
    assert misread_seen  # This fixture actually exercises the observed failure.
