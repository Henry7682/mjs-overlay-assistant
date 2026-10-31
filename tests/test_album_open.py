"""Replay native picker timing without UIA, input, or a running mini-program."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from mjs_assistant.mini_dialogs import album_click_allowed,open_image_dialog


class Clock:
    now=0.
    def __call__(self):return self.now
    def sleep(self,seconds):self.now+=seconds


class Windows:
    def __init__(self,clock,appear=0.,ready=0.,owner=123):
        self.clock=clock;self.appear=appear;self.ready=ready;self.owner=owner
        self.enabled=True;self.foreground=123;self.multiple=False
    def EnumWindows(self,fn,arg):
        if self.clock()>=self.appear:
            fn(10,arg)
            if self.multiple:fn(20,arg)
    def IsWindowVisible(self,h):return True
    def GetClassName(self,h):return '#32770'
    def GetAncestor(self,h,k):return self.owner
    def GetDlgItem(self,h,i):return h+i if self.clock()>=self.ready else 0
    def IsWindowEnabled(self,h):return self.enabled
    def GetForegroundWindow(self):return self.foreground


def run(gui,clock,click,deadline=12,guard=lambda:None,stage=lambda text:None):
    return open_image_dialog(123,click,guard,deadline,stage,gui,clock,clock.sleep)


def test_ready_picker_does_not_click_album_again():
    clock=Clock();gui=Windows(clock);clicks=[]
    assert run(gui,clock,lambda:clicks.append(clock()))==10
    assert clicks==[] and clock()==0


def test_slow_initializing_picker_outlives_old_four_second_cutoff():
    clock=Clock();gui=Windows(clock,appear=.3,ready=5.2);clicks=[];stages=[]
    assert run(gui,clock,lambda:clicks.append(clock()),stage=stages.append)==10
    assert clicks==[0.] and 5.2<=clock()<5.3
    assert '文件窗口正在初始化，等待就绪' in stages


def test_disabled_owner_without_visible_dialog_never_reclicks():
    clock=Clock();gui=Windows(clock,appear=5,ready=5);clicks=[]
    def click():clicks.append(clock());gui.enabled=False
    assert run(gui,clock,click)==10
    assert clicks==[0.]


def test_ignored_click_is_relocated_once_and_succeeds():
    clock=Clock();gui=Windows(clock,appear=99,ready=99);clicks=[]
    def click():
        clicks.append(clock())
        if len(clicks)==2:gui.appear=clock()+.1;gui.ready=clock()+.4
    assert run(gui,clock,click)==10
    assert len(clicks)==2 and 4<=clicks[1]<4.1


def test_late_modal_during_retry_lookup_suppresses_second_input():
    clock=Clock();gui=Windows(clock,appear=99,ready=99);lookups=[];clicks=[]
    def click():
        lookups.append(clock())
        if len(lookups)==2:
            gui.appear=clock();gui.ready=clock()+.4
        if not album_click_allowed(123,gui):return False
        clicks.append(clock());return True
    assert run(gui,clock,click)==10
    assert len(lookups)==2 and clicks==[0.]


def test_no_dialog_has_bounded_retry_and_descriptive_timeout():
    clock=Clock();gui=Windows(clock,appear=99);clicks=[]
    with pytest.raises(TimeoutError,match='文件选择框仍未就绪'):
        run(gui,clock,lambda:clicks.append(clock()),deadline=7)
    assert len(clicks)==2 and clock()==7


def test_foreign_file_dialog_is_never_returned_or_typed_into():
    clock=Clock();gui=Windows(clock,owner=999);gui.foreground=999;clicks=[]
    with pytest.raises(TimeoutError):run(gui,clock,lambda:clicks.append(clock()),deadline=.2)
    assert clicks==[]


def test_incomplete_owned_modal_blocks_album_but_foreign_modal_does_not():
    clock=Clock();gui=Windows(clock,ready=99)
    assert not album_click_allowed(123,gui)
    gui.owner=999
    assert album_click_allowed(123,gui)
    gui.foreground=999
    assert not album_click_allowed(123,gui)


def test_cancel_and_multiple_pickers_do_not_trigger_input():
    clock=Clock();gui=Windows(clock);clicks=[]
    def cancel():raise RuntimeError('配阵已取消')
    with pytest.raises(RuntimeError,match='已取消'):run(gui,clock,lambda:clicks.append(1),guard=cancel)
    gui.multiple=True
    with pytest.raises(RuntimeError,match='多个'):run(gui,clock,lambda:clicks.append(1))
    assert clicks==[]


def test_ready_picker_plus_unknown_owned_modal_waits_without_input():
    clock=Clock();gui=Windows(clock);gui.multiple=True
    gui.GetDlgItem=lambda h,i:h+i if h==10 else 0
    clicks=[]
    with pytest.raises(TimeoutError):run(gui,clock,lambda:clicks.append(1),deadline=.2)
    assert clicks==[]


def test_actual_worker_click_rechecks_modal_after_cursor_move():
    # Execute the production input function with native APIs replaced. The
    # modal appears during its 30ms cursor-settle wait, after initial checks.
    source=Path(__file__).parents[1]/'mjs_assistant'/'mini_worker.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='fast_click')
    node.body=[ast.copy_location(ast.Global(names=n.names),n) if isinstance(n,ast.Nonlocal) else n
               for n in node.body]
    clock=Clock();events=[]
    gui=SimpleNamespace(GetForegroundWindow=lambda:123,WindowFromPoint=lambda coords:123,
                        GetAncestor=lambda h,k:123)
    api=SimpleNamespace(GetSystemMetrics=lambda i:2560,GetCursorPos=lambda:(100,100),
                        mouse_event=lambda *args:events.append(args[0]))
    scope=dict(previous_click=None,read_only_results=False,guard=lambda:None,
               check_request=lambda:None,win32gui=gui,win32api=api,mini=123,
               time=SimpleNamespace(sleep=clock.sleep,monotonic=clock),stage=lambda s:None)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),scope)
    assert scope['fast_click']((100,100),lambda:clock()<.02) is False
    assert events==[0xC001]  # Cursor positioning only: no mouse-down/up.
