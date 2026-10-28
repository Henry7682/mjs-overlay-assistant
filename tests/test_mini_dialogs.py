from unittest.mock import Mock
import pytest
from mjs_assistant.mini_dialogs import image_dialogs,close_image_dialogs


class Windows:
    def __init__(self):
        self.rows={10:(123,'#32770',True,True),11:(999,'#32770',True,True),
                   12:(123,'#32770',True,False),13:(123,'Other',True,True)}
        self.messages=[]
    def EnumWindows(self,fn,arg):
        for h in list(self.rows):fn(h,arg)
    def IsWindowVisible(self,h):return self.rows[h][2]
    def GetClassName(self,h):return self.rows[h][1]
    def GetAncestor(self,h,k):return self.rows[h][0]
    def GetDlgItem(self,h,i):return h+i if self.rows[h][3] else 0
    def PostMessage(self,h,*args):self.messages.append((h,args));self.rows.pop(h)


def test_only_bound_standard_file_picker_is_selected():
    gui=Windows()
    assert image_dialogs(123,gui)==[10]


def test_leftover_is_cancelled_without_touching_other_dialogs():
    gui=Windows();guard=Mock()
    assert close_image_dialogs(123,guard,10,gui,clock=lambda:0)
    assert gui.messages==[(10,(0x111,2,0))]
    assert set(gui.rows)=={11,12,13}


def test_user_input_prevents_dialog_cancel():
    gui=Windows()
    with pytest.raises(RuntimeError,match='input'):
        close_image_dialogs(123,Mock(side_effect=RuntimeError('input')),10,gui)
    assert gui.messages==[]


def test_unresponsive_picker_has_bounded_wait():
    gui=Windows();gui.PostMessage=Mock();clock=[0.]
    def sleep(t):clock[0]+=t
    with pytest.raises(RuntimeError,match='未能关闭'):
        close_image_dialogs(123,lambda:None,.2,gui,lambda:clock[0],sleep)
    assert .2<=clock[0]<.25


def test_multiple_pickers_are_not_blindly_cancelled():
    gui=Windows();gui.rows[20]=gui.rows[10]
    with pytest.raises(RuntimeError,match='多个'):
        close_image_dialogs(123,lambda:None,10,gui)
    assert gui.messages==[]
