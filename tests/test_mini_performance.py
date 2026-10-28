from unittest.mock import Mock
import pytest

from mjs_assistant.mini_page import WindowRoot
from mjs_assistant.mini_clear import clear_pool
from mjs_assistant.mini_page import result_text
from mjs_assistant.mini_worker import parse_document


@pytest.mark.parametrize('tail', ['配阵结果', '未找到匹配的组合搭配'])
def test_local_verification_scope_keeps_selected_pool_and_result(tail):
    text='一键配阵 搜索 郭嘉 已选武将（点击移除） 清空 孙权 ✕ 周瑜 ✕ '+tail+' 位置: 不限 相册 绘图区域 郭嘉'
    narrowed=result_text(text)
    assert '郭嘉' not in narrowed
    assert parse_document(narrowed)==parse_document(text)


@pytest.mark.parametrize('text', ['识别中', '以下位置需确认', '已选武将（点击移除） 清空 孙权 ✕', '位置: 不限 相册'])
def test_loading_or_incomplete_page_keeps_full_evidence(text):
    assert result_text(text)==text


def test_root_reused_but_each_control_is_located_again():
    root=object();create=Mock(return_value=root)
    query=WindowRoot(create,(RuntimeError,))
    lookup=Mock(side_effect=['old control','new control'])
    assert query.query(lookup)=='old control'
    assert query.query(lookup)=='new control'
    create.assert_called_once();assert lookup.call_count==2


@pytest.mark.parametrize('response',[None,RuntimeError('disconnected')])
def test_empty_or_disconnected_root_is_reacquired(response):
    create=Mock(side_effect=['root1','root2']);q=WindowRoot(create,(RuntimeError,))
    lookup=Mock(side_effect=[response,'live page'])
    if response is None:assert q.query(lookup) is None
    assert q.query(lookup)=='live page'
    assert [c.args[0] for c in lookup.call_args_list]==['root1','root2']


def test_root_retry_is_bounded_and_does_not_swallow_cancellation():
    create=Mock(return_value='root');q=WindowRoot(create,(RuntimeError,))
    with pytest.raises(RuntimeError):q.query(Mock(side_effect=RuntimeError('gone')))
    assert create.call_count==2
    with pytest.raises(TimeoutError):q.query(Mock(side_effect=TimeoutError('cancel')))


class Clock:
    def __init__(self):self.now=100.
    def __call__(self):return self.now
    def sleep(self,n):self.now+=n


def run_clear(read,modal,confirm,clear=None,guard=None,initial=None):
    clock=Clock()
    clear_pool(read,lambda text:text=='empty',modal,confirm,clear or Mock(),guard or Mock(),
               110,initial=initial,clock=clock,sleep=clock.sleep)


def test_stale_modal_is_not_clicked_after_successful_confirmation():
    modal=Mock(return_value='dialog');confirm=Mock(return_value=True)
    read=Mock(side_effect=['old','empty','empty'])
    run_clear(read,modal,confirm)
    confirm.assert_called_once_with('dialog');modal.assert_called_once()
    assert read.call_count==3


def test_swallowed_confirmation_retries_only_with_fresh_modal():
    modal=Mock(return_value='dialog');confirm=Mock(return_value=True)
    read=Mock(side_effect=lambda:'empty' if confirm.call_count==2 else 'old')
    clear=Mock();run_clear(read,modal,confirm,clear)
    assert confirm.call_count==2;clear.assert_not_called()


def test_unchanged_pool_fails_with_bounded_clicks():
    modal=Mock(return_value='dialog');confirm=Mock(return_value=True)
    with pytest.raises(RuntimeError,match='旧候选未清空'):
        run_clear(lambda:'old',modal,confirm)
    assert confirm.call_count==2


def test_empty_pool_must_be_observed_twice_and_cancel_propagates():
    read=Mock(side_effect=['old','empty','empty']);clear=Mock()
    run_clear(read,lambda:None,Mock(),clear,initial='empty')
    assert read.call_count==3;clear.assert_called_once()
    guard=Mock(side_effect=TimeoutError('cancel'))
    with pytest.raises(TimeoutError):run_clear(Mock(),Mock(),Mock(),guard=guard)


def test_clear_entrance_retry_requires_pool_still_present():
    clear=Mock();read=Mock(side_effect=lambda:'empty' if clear.call_count==2 else 'old')
    run_clear(read,lambda:None,Mock(),clear,initial='old')
    assert clear.call_count==2
