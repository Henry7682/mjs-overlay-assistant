"""Explicit bounded live check: switch windows only, never interact with game UI."""
import argparse
import json
import sys
import threading
import time
import logging
from dataclasses import asdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mjs_assistant.capture import windows,enable_dpi
from mjs_assistant.mini_windows import mini_windows
from mjs_assistant.input_watch import PhysicalInputWatch
from mjs_assistant.provider import input_idle_seconds
from mjs_assistant.window_focus import NativeFocus,activate_window


class ExerciseBridge(NativeFocus):
    """Skip only the first direct request to exercise the real fallback explicitly."""
    def __init__(self):super().__init__();self.first=True
    def request(self,hwnd):
        if self.first:self.first=False;return
        super().request(hwnd)


def run(output,exercise_bridge=False):
    enable_dpi()
    games=windows();minis=mini_windows()
    if len(games)!=1 or len(minis)!=1:raise RuntimeError('需要唯一游戏与小程序窗口')
    game=games[0].hwnd;mini=minis[0];api=NativeFocus()
    deadline=time.monotonic()+45
    while api.foreground()!=game or input_idle_seconds()<.5:
        if time.monotonic()>deadline:raise RuntimeError('未等到游戏前台静止，未执行切换')
        time.sleep(.1)
    stop=threading.Event();watch=PhysicalInputWatch(stop)
    report={'exercise_bridge':exercise_bridge,'game':game,'mini':mini}
    try:
        began=time.monotonic()
        factory=ExerciseBridge if exercise_bridge else NativeFocus
        result=activate_window(mini,game,stop.is_set,api=factory())
        report['outbound']=asdict(result);report['outbound_foreground']=api.foreground()
        if result.ok:
            time.sleep(.25)
            report['return']=asdict(activate_window(game,mini,stop.is_set,api=factory()))
        report['final_foreground']=api.foreground();report['seconds']=time.monotonic()-began
        report['user_intervened']=stop.is_set()
    finally:watch.close()
    Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--exercise-bridge',action='store_true')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run(args.output,args.exercise_bridge)
