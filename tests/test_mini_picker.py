from mjs_assistant.mini_picker import roster_names,catalogue_ready,portrait_point


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
