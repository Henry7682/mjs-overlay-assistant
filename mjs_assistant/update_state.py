"""Persistent scheduling shared by independent data updaters (UTC timestamps)."""
from datetime import datetime, timezone
import random

DELAYS = (300, 1800, 7200, 21600)


def utcnow():
    return datetime.now(timezone.utc).timestamp()


def due(state, now=None, force=False):
    if force:
        return True
    now = utcnow() if now is None else now
    try:
        deadline = float(state.get('next_attempt', 0))
    except (ValueError, TypeError):
        return True
    # Recover from a clock correction instead of waiting for an arbitrary future.
    return now >= deadline or deadline - now > 90000


def begin(state, now=None):
    now = utcnow() if now is None else now
    return dict(state, last_attempt=now, status='checking', next_attempt=now + 300)


def finish(state, success, message, now=None, jitter=None, source=None):
    now = utcnow() if now is None else now
    failures = 0 if success else int(state.get('failure_count', 0)) + 1
    delay = 86400 if success else DELAYS[min(failures - 1, len(DELAYS) - 1)]
    spread = random.uniform(0, .1) if jitter is None else jitter
    result = dict(state, status='success' if success else 'retry', message=message,
                  failure_count=failures, next_attempt=now + delay * (1 + (0 if success else spread)))
    if success:
        result['last_success'] = now
    if source is not None:
        result['source'] = source
    return result
