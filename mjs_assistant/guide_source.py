"""Display attribution is independent of legacy storage keys and source URLs."""
DEFAULT_SOURCE = 'jiangce'
ATTRIBUTION = '《名将小助手》小程序'
LOCAL_LABEL = ATTRIBUTION + '（内置数据库）'
WECHAT_LABEL = ATTRIBUTION + '（在线查询）'


def selected_source(settings):
    value = settings.get('source', DEFAULT_SOURCE)
    return value if value in ('jiangce', 'wechat') else DEFAULT_SOURCE
