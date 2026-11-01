"""Bounded public-picker input: salvage verified subsets, never invent selection."""
import time


class CandidateUnavailable(RuntimeError):
    """Only a missing/unready hero tile is recoverable; cancellation is not."""


def peak_return_deadline(query_at, selection_at=None):
    """30s from first observed draft, including OCR/activation/startup delay.

    A mini program opened very late still gets a bounded useful attempt rather
    than failing immediately with an expired target. Manual retries start fresh.
    """
    origin=query_at if selection_at is None else min(query_at,selection_at)
    return max(query_at+10,min(query_at+30,origin+30))


def fill_pool(names, search, click, read, publish, stage, guard, input_deadline,
              *, clock=time.monotonic, sleep=time.sleep):
    names=tuple(dict.fromkeys(names))
    allowed=set(names);confirmed=set();last=None

    def observe():
        nonlocal confirmed,last
        guard()
        text,parsed=read()
        selected=set(parsed['selected'])
        if selected-allowed:
            raise RuntimeError('小程序出现非本次候选，保留此前已读攻略')
        if not confirmed<=selected:
            raise RuntimeError('小程序已选名单发生变化，保留此前已读攻略')
        confirmed=selected;last=parsed
        if len(selected)>=2 and (parsed['cards'] or parsed['no_result']):
            publish(parsed)
        return text

    for name in names:
        guard()
        if clock()>=input_deadline:break
        if name in confirmed:continue
        search(name)
        for attempt in range(2):
            guard()
            if clock()>=input_deadline:break
            if attempt:
                # A late first click may already have selected the hero. Re-read
                # before retrying so a second click cannot toggle it back off.
                observe()
                if name in confirmed:break
                if clock()>=input_deadline:break
                stage('重新定位未响应的武将：'+name)
            try:
                click(name,input_deadline)
            except CandidateUnavailable:
                # A tile failure is local to this name. Other errors (focus,
                # cancellation, window close, hard deadline) propagate.
                stage('武将暂不可点击：'+name)
            until=min(input_deadline,clock()+.65)
            while True:
                observe()
                if name in confirmed:break
                # Page text contains guide prose, not a trusted capacity signal.
                # A late chip update must use the normal bounded retry path.
                if clock()>=until:break
                sleep(.06)
            if name in confirmed:break
        if name not in confirmed:
            stage('暂跳过未确认武将，继续其他候选：'+name)
        stage(f'填入候选 {len(confirmed)}/{len(names)}')

    missing=[name for name in names if name not in confirmed]
    reason=''
    if missing:
        reason=('输入时限已到，保留已读攻略；未确认候选' if clock()>=input_deadline
                else '部分武将重试后仍未选入')+'：'+'、'.join(missing)
    return last,reason
