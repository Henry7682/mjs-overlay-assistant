"""Bounded readiness waits for external UIA providers, including restore delays."""
import time


def wait_visible(fetch,guard,deadline,timeout=1,clock=time.monotonic,sleep=time.sleep,cached=False):
    until=min(deadline,clock()+timeout)
    state='not_found'
    while clock()<until:
        guard()
        element=fetch()
        if element:
            try:
                if not cached:raise AttributeError()
                rect=element.CachedBoundingRectangle;offscreen=element.CachedIsOffscreen
            except Exception:
                rect=element.CurrentBoundingRectangle;offscreen=element.CurrentIsOffscreen
            if rect.right>rect.left and rect.bottom>rect.top and not offscreen:
                guard()
                return element,'ready'
            state='not_visible'
        sleep(min(.05,max(0,until-clock())))
    guard()
    return None,state
