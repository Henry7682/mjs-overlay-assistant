"""Real name strips placed back at their captured coordinates; no personal UI."""
from pathlib import Path
import cv2
import numpy as np
import pytest
from mjs_assistant.ocr import Ocr,Names,Word
from mjs_assistant.recognition import Recognizer,Stabilizer
from mjs_assistant.storage import ASSETS


def test_ranked_four_glyph_name_has_full_first_character():
    if not all((ASSETS/'models'/name).exists() for name in ('det.onnx','rec.onnx','cls.onnx')):
        pytest.skip('Restore pinned local OCR models before running image recognition tests')
    strips=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/ranked-nameplates.png',dtype=np.uint8),1)
    frame=np.zeros((1334,2560,3),np.uint8)
    for i,x in enumerate((.092,.194,.296,.398,.522,.624,.726,.828)):
        a,c=int(x*2560),int((x+.019)*2560)
        frame[300:430,a:c]=strips[:,i*49:i*49+c-a]
    r=Recognizer(Ocr(),Names());s=Stabilizer()
    # Header/controls are outside the saved name strips; supply only the scene title.
    r.read_region=lambda key,image:[Word('武将选择',1,(0,0,100,30))] if key=='header' else []
    for _ in range(2):
        scene,items,_=r.analyze(frame,mode_id='ranked_chuhan_2v2');items=s.update(scene,items)
    assert [d.name for d in items if d.confirmed]==['张辽','孙策','庞统','马超','平阳公主','马钧','左思','王导']
    assert Names().resolve('十阳公主') is None
