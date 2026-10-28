from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from mjs_assistant.mini_page import find_page,locate_control

def ids():
    return NS(TreeScope_Element=1,TreeScope_Children=2,TreeScope_Descendants=4,
              UIA_BoundingRectanglePropertyId=30001,UIA_IsOffscreenPropertyId=30022,UIA_TextPatternId=10014)

@pytest.mark.parametrize('failure',['empty','exception'])
def test_fast_page_failure_falls_back_to_live_lookup(failure):
    root=Mock();uia=Mock();page=object()
    if failure=='empty':root.FindFirstBuildCache.return_value=None
    else:root.FindFirstBuildCache.side_effect=RuntimeError('provider unavailable')
    root.FindFirst.side_effect=[None,page]
    assert find_page(root,ids(),lambda **kw:kw,uia) is page

def test_png_route_does_not_use_picker_cache_or_wrapper_tree():
    root=Mock();page=object();root.FindFirst.return_value=page;uia=Mock()
    assert locate_control(root,ids(),lambda **kw:kw,'Page-Frame','Document',uia,optimized=False) is page
    root.FindFirst.assert_called_once_with(4,dict(title='Page-Frame',control_type='Document'))
    root.FindFirstBuildCache.assert_not_called();uia.CreateCacheRequest.assert_not_called()
