from types import SimpleNamespace
import pytest
from mjs_assistant.album_location import album_point,unique_point,locate_album,AlbumNotReady
from test_album_open import Clock,Windows,run

BOUNDS=(100,100,700,1000)

@pytest.mark.parametrize("boxes,expected",[
 ([200,500,40,20],(220,510)),
 ([200,500,20,20,220,500,20,20],(220,510)),
 ([200,500,20,20,500,500,20,20],None),
 ([200,500,20,20,200,700,20,20],None),
 ([200,110,40,20],None),
 ([690,500,40,20],None),
 ([200,500,0,20],None),
 ([200,float('nan'),40,20],None),
 ([],None),([200,500,40],None)])
def test_rectangle_geometry(boxes,expected):
 assert album_point(boxes,BOUNDS)==expected


def test_duplicate_controls_and_ambiguous_targets():
 assert unique_point([(100,100),None,(102,103)])==(100,100)
 assert unique_point([(100,100),(100,200)]) is None


def resolve(text,control,image,clock=None,guard=lambda:None,allowed=lambda:True,deadline=15):
 clock=clock or Clock()
 return locate_album(text,control,image,guard,allowed,deadline,clock=clock,sleep=clock.sleep)


def forbidden():raise AssertionError('unexpected expensive path')


def test_fast_path_never_initializes_image_ocr_or_control_scan():
 assert resolve(lambda:(220,510),forbidden,forbidden)==(220,510)


def test_controls_work_with_empty_text_rectangles():
 assert resolve(lambda:None,lambda:(220,510),forbidden)==(220,510)


def test_image_fallback_runs_only_after_two_fresh_lookup_attempts():
 calls=[]
 def text():calls.append('text')
 def control():calls.append('control')
 def image():calls.append('image');return (220,510)
 assert resolve(text,control,image)==(220,510)
 assert calls==['text','control','text','control','image']


def test_no_image_initialization_near_deadline():
 with pytest.raises(AlbumNotReady):resolve(lambda:None,lambda:None,forbidden,deadline=3)


def test_modal_race_prevents_control_fallback_and_click():
 allowed=[True]
 def text():allowed[0]=False;return (220,510)
 assert resolve(text,forbidden,forbidden,allowed=lambda:allowed[0]) is None


def test_cancellation_propagates_without_fallback():
 def cancel():raise RuntimeError('配阵已取消')
 with pytest.raises(RuntimeError,match='已取消'):resolve(forbidden,forbidden,forbidden,guard=cancel)


def test_localization_failure_retries_then_observes_file_dialog():
 clock=Clock();gui=Windows(clock,appear=99,ready=99);calls=[]
 def click():
  calls.append(clock())
  if len(calls)==1:raise AlbumNotReady('相册无矩形')
  gui.appear=clock()+.1;gui.ready=clock()+.2
 assert run(gui,clock,click)==10
 assert len(calls)==2


def test_location_failure_reports_location_not_file_dialog_timeout():
 clock=Clock();gui=Windows(clock,appear=99,ready=99)
 def click():raise AlbumNotReady('相册无矩形')
 with pytest.raises(AlbumNotReady,match='无矩形'):run(gui,clock,click,deadline=7)
 assert .25<=clock()<1


def test_other_errors_do_not_get_retried():
 clock=Clock();gui=Windows(clock,appear=99,ready=99)
 def click():raise RuntimeError('输入目标变化')
 with pytest.raises(RuntimeError,match='输入目标变化'):run(gui,clock,click)
 assert clock()==0


def test_cancel_after_image_read_does_not_return_a_target():
 clock=Clock()
 def image():clock.now=15;return (220,510)
 def guard():
  if clock()>=15:raise TimeoutError('配阵超时')
 with pytest.raises(TimeoutError):resolve(lambda:None,lambda:None,image,clock=clock,guard=guard)


def worker_function(name,scope):
 import ast
 from pathlib import Path
 source=Path(__file__).parents[1]/'mjs_assistant'/'mini_worker.py'
 node=next(n for n in ast.walk(ast.parse(source.read_text('utf8')))
           if isinstance(n,ast.FunctionDef) and n.name==name)
 node.body=[ast.copy_location(ast.Global(names=n.names),n) if isinstance(n,ast.Nonlocal) else n
            for n in node.body]
 scope['__name__']='mjs_assistant.mini_worker'
 scope['__package__']='mjs_assistant'
 exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),scope)
 return scope[name]


@pytest.mark.parametrize('moved,confidence,expected',[(False,.99,(250,530)),(True,.99,None),(False,.5,None)])
def test_worker_visual_coordinates_cleanup_and_window_move(monkeypatch,moved,confidence,expected):
 import numpy as np
 import mjs_assistant.capture as capture_module
 import mjs_assistant.ocr as ocr_module
 import mjs_assistant.mini_dialogs as dialogs
 clock=Clock();closed=[];reads=[]
 rect=(100,100,600,900)
 class Capture:
  def __init__(self,hwnd):assert hwnd==123
  def read(self):return np.zeros((900,600,3),dtype=np.uint8),rect,0
  def stop(self):closed.append(True)
 class Ocr:
  def read(self,frame):
   reads.append(frame.shape)
   return [ocr_module.Word('相册',confidence,(130,240,170,260))]
 monkeypatch.setattr(capture_module,'Capture',Capture)
 monkeypatch.setattr(capture_module,'client_rect',lambda hwnd:(101,100,600,900) if moved else rect)
 monkeypatch.setattr(ocr_module,'Ocr',Ocr)
 monkeypatch.setattr(dialogs,'album_click_allowed',lambda *args:True)
 scope=dict(album_visual_used=False,mini=123,deadline=15,guard=lambda:None,
            win32gui=SimpleNamespace(GetWindowRect=lambda hwnd:BOUNDS),
            stage=lambda s:None,album_point=album_point,unique_point=unique_point,
            time=SimpleNamespace(monotonic=clock,sleep=clock.sleep))
 fn=worker_function('album_image_point',scope)
 assert fn()==expected
 assert closed==[True] and reads==[(720,600,3)]
 assert fn() is None and closed==[True]  # Only one model/capture attempt per request.
