from test_ranked_retention import host
from mjs_assistant.app import MainWindow


def test_capture_failure_retains_cache_and_explanation():
    window=host(busy=True);cache=window.guide_cache
    window.provider.cancel.side_effect=lambda reason:window.recommendation_status(reason+'；已保留已读攻略')
    MainWindow.invalidate_recommendation(window,'游戏截图不可用')
    assert window.guide_cache is cache
    assert '还原游戏窗口' in window.overlay.recommendation_status
    assert '已保留已读攻略' in window.overlay.recommendation_status
    window.provider.cancel.assert_called_once_with('游戏窗口暂时无法截图；请还原游戏窗口。已读攻略保留')


def test_frame_reconfirmation_does_not_erase_cancellation_notice():
    window=host()
    MainWindow.invalidate_recommendation(window,'游戏截图不可用')
    notice=window.overlay.recommendation_status
    window.provider.busy=False
    MainWindow.invalidate_recommendation(window,'正在确认选将状态')
    assert window.overlay.recommendation_status==notice


def test_new_round_explicitly_clears_old_notice_and_cache():
    window=host()
    window.overlay.recommendation_status='old cancellation'
    window.reset_round('new game')
    assert window.overlay.recommendation_status=='' and window.overlay.recommendation is None
    assert window.game_id!='round'
