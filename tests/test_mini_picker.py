from mjs_assistant.mini_picker import roster_names,catalogue_ready,portrait_point,search_ready
import pytest


def test_picker_excludes_search_chips_and_recommendations():
    text='石崇 已选武将（点击移除） 清空 石崇 ✕ 配阵结果 石崇 50% 相册 绘图区域 S 孙策 46.98% 孙权 58.08% 绘图区域'
    assert roster_names(text)==('孙策','孙权')
    assert not catalogue_ready(text)


def test_no_invented_empty_catalogue_or_stats_as_names():
    assert not catalogue_ready('相册 加载中')
    assert roster_names('相册 绘图区域 陶侃 - 芈八子 47.58% 芈八子 47.58% 绘图区域')==('陶侃','芈八子')


def test_portrait_must_be_above_fixed_footer_and_fully_in_window():
    bounds=(100,100,700,1200)
    assert portrait_point((150,600,40,20),bounds,1000)==(170,560)
    for box in ((),(150,990,40,20),(150,130,40,20),(150,500,0,20),(690,600,40,20)):
        assert portrait_point(box,bounds,1000) is None


@pytest.mark.parametrize('roster,ready',[
    ('D 东方朔 31.79%',True),
    ('D 东方朔 -',True),
    ('D 东方朔 31.79% 白起 59.69%',False),
    ('白起 59.69%',False),
    ('加载中',False),
])
def test_search_requires_filtered_picker_not_just_name_membership(roster,ready):
    text='东方朔 已选武将（点击移除） 清空 东方朔 ✕ 配阵结果 东方朔 31.79% 相册 绘图区域 '+roster+' 绘图区域'
    assert search_ready(text,'东方朔') is ready


def test_worker_waits_for_filtered_roster_before_using_rectangles(monkeypatch):
    from types import SimpleNamespace
    from test_album_location import worker_function
    from test_album_open import Clock
    import mjs_assistant.mini_page as page
    clock=Clock();clicks=[];lookups=[];reads=[]
    class Area:
        def __init__(self,stale):self.stale=stale
        def GetText(self,n):return '东方朔 31.79% 白起 59.69%' if self.stale else '东方朔 31.79%'
        def FindText(self,*args):
            lookups.append(self.stale)
            return SimpleNamespace(GetBoundingRectangles=lambda:[400 if self.stale else 150,600,60,20])
    def find(*args):
        reads.append(clock())
        return Area(len(reads)<=3)
    monkeypatch.setattr(page,'picker_range',lambda area:(area,SimpleNamespace(GetBoundingRectangles=lambda:[500,1000,40,20])))
    scope=dict(last_input=0,guard=lambda:None,expected=['东方朔'],deadline=15,
        time=SimpleNamespace(monotonic=clock,sleep=clock.sleep),find=find,text_area=lambda doc:doc,
        win32gui=SimpleNamespace(GetWindowRect=lambda hwnd:(100,100,700,1200)),mini=1,
        fast_click=lambda point:clicks.append(point),input_tick=lambda:1,
        connection=SimpleNamespace(send=lambda event:None))
    worker_function('click',scope)('东方朔')
    assert len(reads)==4 and lookups==[False] and clicks==[(180,560)]


def test_worker_stale_roster_times_out_without_clicking(monkeypatch):
    from types import SimpleNamespace
    from test_album_location import worker_function
    from test_album_open import Clock
    import mjs_assistant.mini_page as page
    clock=Clock()
    area=SimpleNamespace(GetText=lambda n:'东方朔 31.79% 白起 59.69%')
    monkeypatch.setattr(page,'picker_range',lambda doc:(area,None))
    scope=dict(last_input=0,guard=lambda:None,expected=['东方朔'],deadline=.2,
        time=SimpleNamespace(monotonic=clock,sleep=clock.sleep),find=lambda *a:None,text_area=lambda d:d)
    with pytest.raises(RuntimeError,match='东方朔'):
        worker_function('click',scope)('东方朔')
    assert .2<=clock()<.3
