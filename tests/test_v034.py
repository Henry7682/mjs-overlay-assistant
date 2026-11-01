from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from mjs_assistant.frame_timing import frame_fresh,query_state_alive
from mjs_assistant.mini_page import picker_range,result_range,find_page
from mjs_assistant.mini_worker import parse_document
from mjs_assistant.mini_picker import roster_names
from mjs_assistant.guide_state import BattleTracker
from mjs_assistant.recognition import Detection


def test_transition_fast_to_slow_pass_does_not_cancel_but_stalls_do():
    old=dict(stamp=100,processed_at=100.8,seconds=.8,generation=7)
    running=dict(active=True,stamp=101,began=101.1,generation=7)
    assert not frame_fresh(old,True,102.5)
    assert query_state_alive(old,running,True,102.5)
    assert not query_state_alive(old,running,True,106)
    for change in ({'stamp':100},{'generation':8},{'active':False},{'began':103}):
        assert not query_state_alive(old,dict(running,**change),True,102.5)
    assert not query_state_alive(old,None,True,102.5)
    delivered=dict(running,active=False,finished_at=102.4)
    assert query_state_alive(old,delivered,True,102.5)
    assert not query_state_alive(old,delivered,True,102.7)


def test_minimized_window_cancels_even_during_healthy_pass(monkeypatch):
    from mjs_assistant.app import MainWindow
    from test_ranked_retention import host
    w=host(busy=True,mode='peak_chuhan_2v2');w.window_box=NS(currentData=lambda:123)
    w.latest=dict(stamp=100,processed_at=100.8,seconds=.8,generation=7,scene='selection')
    w.worker.progress=dict(active=True,stamp=101,began=101.1,generation=7)
    w.enabled=False;w.overlay.hide=Mock();w.invalidate_recommendation=Mock();w.present_statistics_button=Mock()
    monkeypatch.setattr('mjs_assistant.app.time.monotonic',lambda:102.5)
    native=NS(IsWindow=lambda hwnd:True,IsIconic=lambda hwnd:False)
    monkeypatch.setattr('mjs_assistant.capture.user32',native)
    MainWindow.tick(w);w.invalidate_recommendation.assert_not_called()
    native.IsIconic=lambda hwnd:True
    MainWindow.tick(w)
    assert '最小化' in w.invalidate_recommendation.call_args.args[0]


class TextRange:
    """Public TextRange boundary semantics for scope/duplicate-name tests."""
    def __init__(self,text,start=0,end=None):self.text=text;self.start=start;self.end=len(text) if end is None else end
    def Clone(self):return TextRange(self.text,self.start,self.end)
    def FindText(self,text,backward,ignore):
        i=self.text.find(text,self.start,self.end)
        return None if i<0 else TextRange(self.text,i,i+len(text))
    def MoveEndpointByRange(self,endpoint,other,target):
        setattr(self,'start' if endpoint==0 else 'end',other.start if target==0 else other.end)
    def GetText(self,length):return self.text[self.start:self.end]


def test_bounded_page_ranges_exclude_same_name_search_and_guide_mentions():
    text='白起 筛选 已选武将（点击移除） 清空 孙权 ✕ 孙策 ✕ 未找到匹配的组合搭配 位置: 不限 相册 绘图区域 白起 50% 绘图区域 无关孙权'
    area=TextRange(text);roster,footer=picker_range(area)
    assert roster_names('相册 绘图区域 '+roster.GetText(-1)+' 绘图区域')==('白起',)
    assert parse_document(result_range(area).GetText(-1))==dict(selected=['孙权','孙策'],cards=[],no_result=True)
    assert area.GetText(-1)==text  # Input range not mutated across uses.
    for bad in ('白起 50%','相册 白起 50%'):
        with pytest.raises(RuntimeError):picker_range(TextRange(bad))


def test_page_is_relocated_and_changed_wrapper_has_fallback():
    ids=NS(TreeScope_Children=1,TreeScope_Descendants=4)
    condition=lambda **k:k
    page1=object();page2=object();root=Mock();root.FindFirst.return_value=None
    root.FindFirst.side_effect=[None,page1,None,page2]
    assert find_page(root,ids,condition) is page1
    assert find_page(root,ids,condition) is page2


def test_page_cache_is_a_fresh_provider_snapshot_each_time():
    ids=NS(TreeScope_Element=1,TreeScope_Descendants=4,UIA_BoundingRectanglePropertyId=30001,
           UIA_IsOffscreenPropertyId=30022,UIA_TextPatternId=10014)
    root=Mock();uia=Mock();pages=[object(),object()];requests=[Mock(),Mock()]
    uia.CreateCacheRequest.side_effect=requests;root.FindFirstBuildCache.side_effect=pages
    for page,request in zip(pages,requests):
        assert find_page(root,ids,lambda **k:k,uia) is page
        assert request.AddProperty.call_count==2
        request.AddPattern.assert_called_once_with(10014)
    assert root.FindFirstBuildCache.call_args_list[0].args[2] is not root.FindFirstBuildCache.call_args_list[1].args[2]


def test_fresh_cached_visibility_avoids_extra_current_calls():
    from mjs_assistant.uia_wait import wait_visible
    class Cached:
        CachedBoundingRectangle=NS(left=0,top=0,right=200,bottom=300)
        CachedIsOffscreen=False
        @property
        def CurrentBoundingRectangle(self):raise AssertionError('unneeded remote query')
    element=Cached();guard=Mock()
    assert wait_visible(lambda:element,guard,10,clock=lambda:1,cached=True)==(element,'ready')
    assert guard.call_count==2


def test_seats_follow_hero_across_exchange_and_missing_glyphs():
    t=BattleTracker()
    def items(own='孟尝君',ally='卢莫愁',slot='roi2',enemy='刘邦'):
        return [Detection(n,n,(0,0,1,1),1,s,True) for s,n in [('roi0','项梁'),('roi1',enemy),(slot,ally),('roi4',own)]]
    badges={'roi0':dict(camp='汉军',seat=3),'roi1':dict(camp='汉军',seat=2),
            'roi2':dict(camp='楚军',seat=4),'roi4':dict(camp='楚军',seat=1)}
    t.update(items(),badges);t.update(items(),badges)
    changed={s:dict(camp=b['camp'],seat=None) for s,b in badges.items()}
    changed['roi3']=changed.pop('roi2')
    t.update(items('卢莫愁','孟尝君','roi3'),changed)
    r=t.update(items('卢莫愁','孟尝君','roi3'),changed)
    assert r.friendly==('卢莫愁','孟尝君') and r.friendly_seats==(4,1) and r.enemy_seats==(3,2)
    t.update(items('卢莫愁','孟尝君','roi3','张飞'),changed)
    r=t.update(items('卢莫愁','孟尝君','roi3','张飞'),changed)
    assert r.enemy_seats==(None,None)
