"""Bound displayed evidence by both capture age and completed OCR age."""
import time


def frame_fresh(data,peak=False,now=None):
    if not data or 'stamp' not in data:return False
    now=time.monotonic() if now is None else now
    if 'processed_at' not in data:
        return now-data['stamp']<=(4.5 if peak else 3)
    # The capture is already old by one OCR pass when published. Give that
    # completed result one more measured pass (bounded), not a second fixed
    # capture deadline that expires halfway through every slow next pass.
    duration=max(0,min(4,float(data.get('seconds',0))))
    grace=max(1.5,min(4,duration+.8))
    return (0<=now-data['processed_at']<=grace and
            now-data['stamp']<=duration+grace+.5)


def query_state_alive(data,progress=None,peak=False,now=None):
    """A display expiry is not a stalled recognizer while a newer frame is in flight.

    No repeated heartbeat can extend an old capture: both the start and capture
    timestamp of this one pass are bounded, and its generation must match.
    Explicit lifecycle invalidation stays with the controller.
    """
    now=time.monotonic() if now is None else now
    if frame_fresh(data,peak,now):return True
    if not data or not progress:return False
    if not progress.get('active') and not 0<=now-progress.get('finished_at',float('-inf'))<=.25:return False
    if data.get('generation')!=progress.get('generation'):return False
    limit=4.5 if peak else 3
    return (progress['stamp']>data.get('stamp',float('inf'))
            and 0<=now-progress['began']<=limit
            and 0<=now-progress['stamp']<=limit+.5)
