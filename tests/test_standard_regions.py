"""Coordinate and lifecycle regressions; synthetic cases are not live evidence."""
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from mjs_assistant.region_geometry import (is_standard_client, center_x, map_region,
                                          map_regions, pixel_box, NAME_MARGIN)
from mjs_assistant.recognition import Recognizer, profile_key
from mjs_assistant.ocr import Names
from mjs_assistant.modes import RANKED_CHUHAN


@pytest.mark.parametrize('size,expected', [((1920,1080),True),((2560,1440),True),
    ((1919,1080),True),((1920,1082),True),((1920,1083),False),
    ((1924,1127),False),((1920,1200),False),((2559,1334),False),((0,0),False)])
def test_actual_client_ratio_not_monitor_or_outer_window(size,expected):
    assert is_standard_client(*size)==expected


def test_center_height_mapping_preserves_pixels_and_margins():
    r=(.092,.246,.111,.321)
    mapped=map_region(r,1920,1080,'center_height',NAME_MARGIN)
    a,b,c,d=pixel_box(mapped,1920,1080)
    assert (a,b,c,d)==(108,257,160,354)
    # The actual name observed around x=125 is outside the old strip at x=176.
    assert a<=125<=c and not .092*1920<=125<=.111*1920
    assert np.allclose(mapped,map_region(r,2560,1440,'center_height',NAME_MARGIN))
    assert center_x(.5,1920,1080)==.5
    assert map_region(r,2559,1334,'center_height',NAME_MARGIN)==r
    assert map_region(r,1920,1080)==r
    assert map_region(r,1920,1080,'center_height',NAME_MARGIN) is mapped
    with pytest.raises(ValueError):map_region(r,1920,1080,'guess')


def test_margin_is_bounded_and_does_not_overlap_ranked_neighbours():
    rs=map_regions([(x,.246,x+.019,.321) for x in (.092,.194,.296,.398,.522,.624,.726,.828)],
                   1920,1080,'center_height',NAME_MARGIN)
    assert all(left[2]<right[0] for left,right in zip(rs,rs[1:]))
    assert map_region((0,0,1,1),1920,1080,margin=NAME_MARGIN)==(0,0,1,1)


def test_custom_calibration_never_transforms_or_accumulates_padding():
    r=Recognizer(SimpleNamespace(read=lambda image:[]),Names())
    frame=np.zeros((1080,1920,3),np.uint8);region=(.2,.2,.23,.35)
    profile={profile_key('selection',1920,1080):{'regions':[region]}}
    for _ in range(2):
        r.analyze(frame,'selection',profile,RANKED_CHUHAN)
        assert r.name_regions==(region,)
    assert profile[profile_key('selection',1920,1080)]['regions']==[region]


def test_worker_rejects_wrong_aspect_before_any_ocr_or_automation(monkeypatch):
    import mjs_assistant.app as app
    worker=app.RecognitionThread();worker.hwnd=123
    recognizer=Mock();cap=Mock()
    cap.read.return_value=(np.zeros((1200,1920,3),np.uint8),(0,0,1920,1200),1.)
    monkeypatch.setattr(app,'Capture',lambda hwnd:cap)
    monkeypatch.setattr(app,'Ocr',lambda:object())
    monkeypatch.setattr(app,'Recognizer',lambda *args:recognizer)
    monkeypatch.setattr(worker,'isInterruptionRequested',Mock(side_effect=[False,True]))
    monkeypatch.setattr(worker,'msleep',lambda ms:None)
    received=[];worker.result.connect(received.append)
    worker.run()
    assert len(received)==1 and '16:9' in received[0]['unsupported_aspect']
    assert received[0]['items']==[]
    recognizer.analyze.assert_not_called();cap.stop.assert_called_once()


def test_known_six_geometry_keeps_fallback_for_missing_extra_or_shifted_cards():
    from mjs_assistant.identity_layout import six_lord_grid
    frame=np.full((1080,1920,3),215,np.uint8)
    for x in (.286,.392,.500,.606,.714,.821):
        a=round(center_x(x,1920,1080)*1920)
        frame[270:500,a:a+178]=(40,80,120)
    assert six_lord_grid(frame)
    missing=frame.copy();missing[:,720:940]=215
    assert not six_lord_grid(missing)
    extra=frame.copy();extra[270:500,460:511]=(40,80,120)
    assert not six_lord_grid(extra)
    shifted=np.roll(frame,45,axis=1)
    assert not six_lord_grid(shifted)
    assert not six_lord_grid(np.full_like(frame,215))
