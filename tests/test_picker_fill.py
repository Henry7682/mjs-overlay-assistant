from types import SimpleNamespace
import pytest
from mjs_assistant.picker_fill import fill_pool,CandidateUnavailable,peak_return_deadline
from test_album_open import Clock


def setup(names=('甲将','乙将','丙将'),effect=None,read_cost=.1,deadline=20):
    clock=Clock();selected=[];clicks=[];searches=[];batches=[];stages=[];reads=[]
    def click(name,until):
        clicks.append(name)
        if effect is None or effect(name,clicks):
            if name not in selected:selected.append(name)
    def read():
        reads.append(clock());clock.sleep(read_cost)
        return '',dict(selected=list(selected),cards=[],no_result=True)
    def run(**kwargs):
        return fill_pool(names,searches.append,click,read,batches.append,stages.append,
                         kwargs.get('guard',lambda:None),deadline,clock=clock,sleep=clock.sleep)
    return SimpleNamespace(**locals())


def test_fast_path_one_post_click_read_per_name_no_catalogue_or_final_reread():
    s=setup();result,limit=s.run()
    assert result['selected']==list(s.names) and not limit
    assert len(s.reads)==len(s.names)==len(s.clicks)


def test_one_empty_click_retries_then_continues_rest_of_pool():
    s=setup(effect=lambda name,clicks:len(clicks)!=1)
    result,limit=s.run()
    assert result['selected']==list(s.names) and not limit
    assert s.clicks==['甲将','甲将','乙将','丙将']


def test_unavailable_hero_does_not_abort_other_names():
    s=setup(effect=lambda name,clicks:name!='乙将')
    result,limit=s.run()
    assert result['selected']==['甲将','丙将'] and '乙将' in limit
    assert s.clicks.count('乙将')==2


def test_late_first_click_is_observed_before_retry_no_toggle():
    s=setup(names=('甲将','乙将'),effect=lambda name,clicks:name=='乙将')
    original=s.read
    def read():
        if len(s.reads)==5 and '甲将' not in s.selected:s.selected.append('甲将')
        return original()
    result,limit=fill_pool(s.names,s.searches.append,s.click,read,s.batches.append,s.stages.append,
        lambda:None,20,clock=s.clock,sleep=s.clock.sleep)
    assert result['selected']==list(s.names) and s.clicks==list(s.names) and not limit


def test_input_deadline_leaves_verified_subset_and_names_missing():
    s=setup(read_cost=1,deadline=2)
    result,limit=s.run()
    assert result['selected']==['甲将','乙将'] and '丙将' in limit
    assert s.clicks==['甲将','乙将'] and s.batches


def test_foreign_candidate_rejected_not_published():
    s=setup();s.selected.append('外来武将')
    with pytest.raises(RuntimeError,match='非本次候选'):s.run()
    assert not s.batches


def test_cancel_does_not_retry():
    s=setup()
    def cancel():raise RuntimeError('配阵已取消')
    with pytest.raises(RuntimeError,match='取消'):s.run(guard=cancel)
    assert not s.clicks


def test_candidate_exception_skips_only_that_name():
    s=setup()
    def click(name,until):
        if name=='乙将':raise CandidateUnavailable(name)
        s.click(name,until)
    result,limit=fill_pool(s.names,s.searches.append,click,s.read,s.batches.append,s.stages.append,
        lambda:None,20,clock=s.clock,sleep=s.clock.sleep)
    assert result['selected']==['甲将','丙将'] and '乙将' in limit


def test_runtime_error_is_not_swallowed_as_empty_click():
    s=setup()
    def click(*args):raise RuntimeError('输入目标已变化')
    with pytest.raises(RuntimeError,match='输入目标'):
        fill_pool(s.names,s.searches.append,click,s.read,s.batches.append,s.stages.append,
            lambda:None,20,clock=s.clock,sleep=s.clock.sleep)


def test_budget_expiring_in_search_does_not_click_another_hero():
    s=setup(deadline=1)
    def search(name):s.clock.sleep(2)
    result,limit=fill_pool(s.names,search,s.click,s.read,s.batches.append,s.stages.append,
        lambda:None,1,clock=s.clock,sleep=s.clock.sleep)
    assert result is None and not s.clicks and '甲将' in limit


def test_confirmed_hero_disappearing_stops_without_publishing_wrong_pool():
    s=setup()
    def click(name,until):
        s.click(name,until)
        if name=='丙将':s.selected.remove('甲将')
    with pytest.raises(RuntimeError,match='已选名单发生变化'):
        fill_pool(s.names,s.searches.append,click,s.read,s.batches.append,s.stages.append,
            lambda:None,20,clock=s.clock,sleep=s.clock.sleep)
    assert s.batches[-1]['selected']==['甲将','乙将']


def test_empty_initial_result_gets_fresh_verification():
    from test_album_location import worker_function
    from mjs_assistant.mini_worker import parse_document
    calls=[];events=[]
    def document(**kw):
        calls.append(kw)
        return '已选武将（点击移除） 清空 甲将 ✕ 乙将 ✕ 未找到匹配的组合搭配 位置: 不限'
    scope=dict(last_input=0,input_limit='',guard=lambda:None,document=document,
               parse_document=parse_document,connection=SimpleNamespace(send=events.append))
    result=worker_function('collect_results',scope)(
        dict(selected=['甲将','乙将'],cards=[],no_result=True),verify_empty=True)
    assert len(calls)==1 and result['no_result'] and result['complete']


def test_soft_target_preserves_first_batch_without_extra_uia_lookup():
    from test_album_location import worker_function
    events=[]
    card=dict(heroes=['甲将','乙将'],reason='真实攻略')
    scope=dict(last_input=0,input_limit='',guard=lambda:None,manual_review=False,
               quick_peak=True,result_deadline=30,time=SimpleNamespace(monotonic=lambda:30),
               connection=SimpleNamespace(send=events.append))
    result=worker_function('collect_results',scope)(
        dict(selected=['甲将','乙将'],cards=[card],no_result=False))
    assert result['cards']==[card] and not result['complete']
    assert '优先返回' in result['limits'][0]


def test_return_target_includes_recognition_and_start_delay():
    assert peak_return_deadline(104,100)==130
    assert peak_return_deadline(104)==134  # Manual retry starts a new budget.
    assert peak_return_deadline(140,100)==150  # Late connection still gets a useful attempt.
    assert peak_return_deadline(100,104)==130  # Do not extend for invalid future stamps.


def test_selection_timestamp_does_not_invalidate_cached_guides():
    from dataclasses import replace
    from test_automatic_query import snapshot
    snap=snapshot('peak_chuhan_2v2')
    assert replace(snap,selection_started_at=10).fingerprint==snap.fingerprint


def test_guide_prose_does_not_stop_input_while_chip_update_is_late():
    s=setup(effect=lambda name,clicks:name!='乙将')
    original=s.read
    def read():
        # The first post-click snapshot is stale; subsequent snapshots catch up.
        if s.clicks[-1]=='乙将' and len(s.reads)>=2:
            s.selected.append('乙将')
        _,parsed=original()
        parsed['cards']=[dict(heroes=['甲将','乙将'],reason='提高上限。个人建议配合使用')]
        return '配阵结果 提高上限。个人建议配合使用',parsed
    result,limit=fill_pool(s.names,s.searches.append,s.click,read,s.batches.append,s.stages.append,
        lambda:None,20,clock=s.clock,sleep=s.clock.sleep)
    assert result['selected']==list(s.names) and not limit
    assert s.clicks==list(s.names)  # Late completion must not toggle a hero off.


def test_capacity_like_text_cannot_abort_remaining_candidates():
    s=setup(effect=lambda name,clicks:name!='乙将')
    def read():
        _,parsed=s.read()
        return '配阵结果 最多影响两个武将',parsed
    result,limit=fill_pool(s.names,s.searches.append,s.click,read,s.batches.append,s.stages.append,
        lambda:None,20,clock=s.clock,sleep=s.clock.sleep)
    assert result['selected']==['甲将','丙将']
    assert s.clicks==['甲将','乙将','乙将','丙将'] and '乙将' in limit
    assert '数量限制' not in limit


def worker_deadlines(budget=40,first_seen=0,query_at=3):
    """Execute the production budget assignments without activating any window."""
    import ast,inspect
    from mjs_assistant import mini_worker
    tree=ast.parse(inspect.getsource(mini_worker._worker))
    assignments=[n for n in tree.body[0].body if isinstance(n,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id in
                         ('quick_peak','result_deadline','input_deadline') for t in n.targets)]
    scope=dict(deadline=query_at+budget-.7,budget=budget,picker_only=True,read_existing=False,
               return_deadline=peak_return_deadline(query_at,first_seen),
               PEAK_RETURN_TARGET=mini_worker.PEAK_RETURN_TARGET,
               PEAK_RESULT_RESERVE=mini_worker.PEAK_RESULT_RESERVE)
    exec(compile(ast.Module(body=assignments,type_ignores=[]),'<worker-budget>','exec'),scope)
    return scope


def test_progressing_14_name_pool_continues_past_30_second_soft_target():
    limits=worker_deadlines()
    s=setup(names=tuple(f'武将{i}' for i in range(14)),read_cost=2.1,
            deadline=limits['input_deadline'])
    s.clock.sleep(5)  # Startup, activation and clearing are inside the same budget.
    result,limit=s.run()
    assert s.clock()>limits['result_deadline']
    assert result['selected']==list(s.names) and not limit
    assert len(s.reads)==len(s.names)  # No extra reads/waits on the healthy path.


def test_slow_input_still_reserves_result_time_under_hard_limit():
    limits=worker_deadlines()
    s=setup(names=tuple(f'武将{i}' for i in range(14)),read_cost=4,
            deadline=limits['input_deadline'])
    result,limit=s.run()
    assert 2<len(result['selected'])<14 and '输入时限已到' in limit
    assert s.clock()<limits['deadline'] and s.batches
    assert limits['input_deadline']==limits['deadline']-4


def test_ordinary_picker_keeps_15_second_budget():
    limits=worker_deadlines(budget=15)
    assert not limits['quick_peak']
    assert limits['input_deadline']==limits['result_deadline']==limits['deadline']
