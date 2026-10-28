"""Bounded public clear-dialog transaction, independent of the UIA transport."""
import time


def clear_pool(read, is_empty, confirmation, confirm_click, clear_click, guard,
               deadline, initial=None, clock=time.monotonic, sleep=time.sleep):
    until=min(deadline,clock()+7)
    attempts=0;clicked=float('-inf');confirmed=False;empty_hits=0
    confirmed_at=0.;confirm_attempts=0
    while clock()<until:
        guard()
        # Read the resulting pool first after confirmation. The dismissed modal
        # may remain briefly in the accessibility tree; never immediately reclick.
        button=confirmation() if not confirmed else None
        if button and confirm_click(button):
            confirmed=True;confirm_attempts+=1;confirmed_at=clock()
            initial=None;sleep(.15);continue
        text=initial if initial is not None else read()
        initial=None
        if is_empty(text):
            empty_hits+=1
            if empty_hits>=2:return
        else:
            empty_hits=0
            if confirmed and confirm_attempts<2 and clock()-confirmed_at>=.8:
                confirmed=False
                # On the next pass verify the exact modal before another input.
                sleep(.08);continue
            if not confirmed and attempts<2 and clock()-clicked>=1:
                clear_click(attempts);attempts+=1;clicked=clock()
        sleep(.08)
    guard()
    raise RuntimeError('旧候选未清空，已停止；可重新配阵')
