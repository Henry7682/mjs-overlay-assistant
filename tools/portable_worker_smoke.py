"""Verify frozen multiprocessing/UIA readiness without input or uploads."""
import json,multiprocessing as mp,time
from pathlib import Path
from mjs_assistant.mini_worker import worker


def run(output):
    parent,child=mp.get_context('spawn').Pipe();began=time.monotonic()
    process=mp.get_context('spawn').Process(target=worker,args=(child,None,[],True))
    process.start();child.close();result={'ready':False,'no_input':True}
    try:
        while time.monotonic()-began<10:
            if not parent.poll(.1):continue
            message=parent.recv()
            if message.get('ready'):
                parent.send('cancel');result['ready']=True;break
            if message.get('status')=='failed':result['error']=message.get('error');break
        process.join(.5)
    finally:
        if process.is_alive():process.terminate();process.join(.2)
        result['seconds']=time.monotonic()-began
        Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8');parent.close()
    if not result['ready']:raise RuntimeError(result.get('error','worker initialization timed out'))
