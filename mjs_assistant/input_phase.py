"""Keep a request alive while foreground input must wait for its target."""
import time


def wait_input_target(ready,check,notify,sleep=time.sleep):
    waiting=False
    while True:
        check()  # Explicit cancel, closed window and deadline still own the request.
        if ready():
            if waiting:notify(False)
            return waiting
        if not waiting:notify(True);waiting=True
        sleep(.05)
