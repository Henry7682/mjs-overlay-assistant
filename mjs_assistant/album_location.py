"""Bounded album localization. No input, desktop capture or persistent page cache."""
import math
import time


class AlbumNotReady(RuntimeError):
    """Retryable localization failure, distinct from cancellation or focus loss."""


def album_point(rectangles, bounds):
    """Accept a single label split into adjacent text runs, never distant matches."""
    if not rectangles or len(rectangles) % 4:
        return None
    rows = [tuple(rectangles[i:i+4]) for i in range(0, len(rectangles), 4)]
    left, top, right, bottom = bounds
    for x, y, w, h in rows:
        if not all(math.isfinite(v) for v in (x, y, w, h)):
            return None
        if not (w > 0 and h > 0 and left <= x < x+w <= right
                and top+(bottom-top)*.20 < y < y+h <= bottom):
            return None
    x = min(r[0] for r in rows); y = min(r[1] for r in rows)
    r = max(a+c for a,b,c,d in rows); b = max(b+d for a,b,c,d in rows)
    height = max(row[3] for row in rows)
    if r-x > height*8 or b-y > height*1.5:
        return None
    ordered = sorted(rows)
    if any(n[0]-(v[0]+v[2]) > height for v,n in zip(ordered, ordered[1:])):
        return None
    return int((x+r)/2), int((y+b)/2)


def unique_point(points):
    points = [p for p in points if p is not None]
    if not points:
        return None
    if any(max(abs(a-b) for a,b in zip(points[0], p)) > 8 for p in points[1:]):
        return None
    return points[0]


def locate_album(text_lookup, control_lookup, image_lookup, guard, can_click,
                 deadline, stage=lambda text: None, clock=time.monotonic, sleep=time.sleep):
    """Normal text path stays fast; bounded fallbacks share the request deadline."""
    until = min(deadline, clock()+3)
    attempts = 0
    while clock() < until:
        guard()
        if not can_click():
            return None
        for name, lookup in (("文字", text_lookup), ("控件", control_lookup)):
            if clock() >= deadline:
                break
            point = lookup()
            guard()
            if not can_click():
                return None
            if point is not None:
                stage('相册定位成功：'+name)
                return point
        attempts += 1
        if attempts >= 2:
            break
        sleep(min(.12, max(0, until-clock())))
    # A lazy model load may be slow; the parent still owns the hard deadline.
    if deadline-clock() >= 4 and can_click():
        stage('相册文字位置不可用，尝试窗口局部识别')
        point = image_lookup()
        guard()
        if can_click() and point is not None:
            stage('相册定位成功：局部识别')
            return point
    raise AlbumNotReady('相册入口未定位：文字／控件无有效位置，局部识别未确认；请保持一键配阵页相册可见')
