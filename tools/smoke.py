"""Offline model/packaging smoke entry point. Does not capture game or download."""
import json
import socket
import time
from pathlib import Path


def run(output, sample=None):
    import os
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    from PIL import Image, ImageDraw, ImageFont
    import cv2
    import numpy as np
    from mjs_assistant.ocr import Ocr, Names
    from mjs_assistant.storage import BoardStore, ASSETS
    from mjs_assistant.boards import validate_board
    def blocked(*a, **k): raise RuntimeError('offline smoke: network disabled')
    socket.socket.connect = blocked
    store=BoardStore(); engine=Ocr()
    img=Image.new('RGB',(600,140),'white')
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',45)
    ImageDraw.Draw(img).text((20,25),'司马睿 64.38%',font=font,fill='black')
    words=engine.read(cv2.cvtColor(np.asarray(img),cv2.COLOR_RGB2BGR))
    assert any('司马睿' in x.text for x in words), [x.text for x in words]
    assert not validate_board(store.board)
    boards=store.all_current()
    assert len(boards)==4 and all(not validate_board(b) for b in boards.values())
    from pywinauto.uia_defines import IUIA
    assert IUIA().iuia is not None
    from mjs_assistant.entry_detection import detect_entry
    from mjs_assistant.guide_controller import GuideController
    from types import SimpleNamespace
    assert callable(detect_entry)
    assert Names().resolve('赢政')=='嬴政'
    assert Names().resolve('公孙瓚')=='公孙瓒'
    assert GuideController.guides_enabled(SimpleNamespace(config={}))
    from mjs_assistant.mini_page import WindowRoot
    from mjs_assistant.mini_clear import clear_pool
    assert callable(clear_pool) and callable(WindowRoot)
    from mjs_assistant.recommendation_ui import RecommendationSettings
    from unittest.mock import patch
    with patch('mjs_assistant.mini_windows.mini_windows',return_value=[]):
        settings=RecommendationSettings({})
        assert settings.enabled.isChecked() and settings.guides.isChecked() and settings.auto.isChecked()
        assert settings.keys['request'].text()=='Ctrl+Alt+P'
        settings.close()
    result={'offline':True,'qt_version':qVersion(),'models':{x.name:x.stat().st_size for x in (ASSETS/'models').glob('*.onnx')},
            'board_rows':{key:len(b['heroes']) for key,b in boards.items()},'words':[x.text for x in words],
            'uia_initialized':True,'entry_detection_bundled':True,
            'yingzheng_alias':True,'gongsunzan_alias':True,'guides_default_on':True,
            'query_default_on':True,'automatic_default_on':True,'request_hotkey':'Ctrl+Alt+P',
            'query_optimizations_bundled':True}
    if sample:
        from mjs_assistant.recognition import Recognizer, Stabilizer
        frame=cv2.imdecode(np.fromfile(sample,dtype=np.uint8),cv2.IMREAD_COLOR)
        r=Recognizer(engine,Names());s=Stabilizer();start=time.monotonic()
        scene,items,_=r.analyze(frame);s.update(scene,items)
        scene,items,_=r.analyze(frame);items=s.update(scene,items)
        result.update(scene=scene,confirmed=[d.name for d in items if d.confirmed],two_frame_seconds=time.monotonic()-start)
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
