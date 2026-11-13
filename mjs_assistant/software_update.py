"""Source check only: verify metadata through the same launcher, never install."""
import json
import os
from pathlib import Path
import subprocess
from PySide6.QtCore import QThread,Signal
from .version import VERSION
from .storage import user_dir, read_json, write_json
from .update_state import begin, finish
import sys

class SourceUpdateCheck(QThread):
    message=Signal(str)
    def run(self):
        path=user_dir()/'software-check.json'
        state=begin(read_json(path,{}));write_json(path,state)
        success=False;text='软件更新来源暂不可用，继续使用当前版本'
        try:
            script=Path(__file__).resolve().parents[1]/'release/check.ps1'
            ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
            result=subprocess.run([str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)],
                capture_output=True,timeout=13,creationflags=subprocess.CREATE_NO_WINDOW)
            for line in reversed(result.stdout.decode('utf8',errors='replace').splitlines()):
                if line.startswith('{'):
                    info=json.loads(line)
                    if info.get('status')=='verified':
                        success=True
                        text='当前可用发行版：'+info['version']
                        if tuple(map(int,info['version'].split('.')))>tuple(map(int,VERSION.split('.'))):
                            text+='；重启最外层 launch.cmd 自动升级' if getattr(sys,'frozen',False) else '；源码仅提示更新，不覆盖工作区'
                    break
        except Exception:pass  # Offline metadata cannot stop statistics.
        write_json(path,finish(state,success,text))
        self.message.emit(text)
