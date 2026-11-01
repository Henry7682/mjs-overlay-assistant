from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from mjs_assistant.widgets import Overlay
from mjs_assistant.modes import PEAK_CHUHAN,RANKED_CHUHAN
from test_entry_and_isolation import window,deliver


def test_statistics_refresh_never_raises_above_visible_guide(monkeypatch):
    positions=[]
    monkeypatch.setattr('mjs_assistant.widgets.C.windll.user32.SetWindowPos',
                        lambda hwnd,after,*args:positions.append((hwnd,after.value,args[-1])))
    layer=NS(hwnd=100,isVisible=lambda:True,show=Mock(),update=Mock())
    # Also covers resize/move while the guide is expanded or compact: its HWND
    # stays the same and every statistics update is inserted behind that HWND.
    for rect in ((0,0,2560,1440),(100,70,1920,1080),(100,70,1920,1080)):
        Overlay.present(layer,rect,rect[2:],[],{},above_hwnd=200)
    assert positions==[(100,200,0x50)]*3
    layer.show.assert_not_called()
    assert layer.update.call_count==3


def test_hidden_and_unaccompanied_statistics_layer(monkeypatch):
    calls=[]
    monkeypatch.setattr('mjs_assistant.widgets.C.windll.user32.SetWindowPos',
                        lambda hwnd,after,*args:calls.append((after.value,args[-1])))
    state={'visible':False}
    layer=NS(hwnd=100,isVisible=lambda:state['visible'],show=Mock(),update=Mock())
    Overlay.present(layer,(0,0,1920,1080),(1920,1080),[],{})
    layer.show.assert_called_once()
    assert calls[-1][1]==0x50  # First display establishes topmost, no activation.
    state['visible']=True;layer.show.reset_mock()
    Overlay.present(layer,(0,0,1920,1080),(1920,1080),[],{})
    assert calls[-1][1]==0x54  # Later refresh preserves z-order, no activation.
    layer.show.assert_not_called()
    state['visible']=False
    Overlay.present(layer,(0,0,1920,1080),(1920,1080),[],{},above_hwnd=200)
    assert calls[-1]==(200,0x50)


@pytest.mark.parametrize('mode',[PEAK_CHUHAN,RANKED_CHUHAN])
@pytest.mark.parametrize('scene',['selection','battle'])
def test_tick_places_statistics_below_guides_without_coupling_visibility(window,monkeypatch,mode,scene):
    w=window
    w.mode_box.setCurrentIndex(w.mode_box.findData(mode))
    monkeypatch.setattr(w,'update_selection',lambda d:None)
    deliver(w,None,scene)
    monkeypatch.setattr(w.guide_panel,'isVisible',lambda:True)
    for compact in (False,True):
        w.guide_panel.compact=compact;w.tick()
        assert w.overlay.present.call_args.kwargs['above_hwnd']==int(w.guide_panel.winId())
    monkeypatch.setattr(w.guide_panel,'isVisible',lambda:False)
    w.tick();assert w.overlay.present.call_args.kwargs['above_hwnd'] is None
    w.config['statistics_visible']=False;w.overlay.present.reset_mock();w.guide_panel.present.reset_mock()
    w.tick();w.overlay.present.assert_not_called();w.guide_panel.present.assert_called_once()
