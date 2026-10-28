from unittest.mock import Mock
import pytest
from mjs_assistant.mini_content import activate_content


class Windows:
    def GetForegroundWindow(self):return 7
    def IsWindowVisible(self,h):return True
    def IsWindowEnabled(self,h):return True
    def IsIconic(self,h):return False
    def GetWindowText(self,h):return '名将小助手'
    def GetClassName(self,h):return 'Chrome_WidgetWin_0'
    def GetWindowRect(self,h):return (969,99,1590,1269)
    def WindowFromPoint(self,p):return 9
    def GetAncestor(self,h,k):return 7


def test_header_activation_is_dpi_scaled_and_bound_to_target():
    gui=Windows();click=Mock();guard=Mock()
    point=activate_content(7,guard,click,gui,144)
    assert point==(1279,139)
    click.assert_called_once_with(point)
    assert guard.call_count==2


@pytest.mark.parametrize('method,value',[
    ('GetForegroundWindow',8),('IsWindowEnabled',False),('IsWindowVisible',False),
    ('IsIconic',True),('GetAncestor',8),('GetWindowText','other app'),
    ('GetWindowRect',(0,0,100,200)),('GetClassName','other class')])
def test_wrong_or_occluded_window_is_never_clicked(method,value):
    gui=Windows();setattr(gui,method,lambda *args:value);click=Mock()
    with pytest.raises(RuntimeError):activate_content(7,lambda:None,click,gui,144)
    click.assert_not_called()


def test_cancellation_immediately_before_input_prevents_click():
    guard=Mock(side_effect=[None,RuntimeError('cancelled')]);click=Mock()
    with pytest.raises(RuntimeError,match='cancelled'):
        activate_content(7,guard,click,Windows(),144)
    click.assert_not_called()
