"""Source check only: verify metadata through the same launcher, never install."""
import json
import os
from pathlib import Path
import subprocess
from PySide6.QtCore import QThread,Signal
from .version import VERSION

class SourceUpdateCheck(QThread):
    message=Signal(str)
    def run(self):
        try:
            script=Path(__file__).resolve().parents[1]/'release/check.ps1'
            ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
            result=subprocess.run([str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)],
                capture_output=True,timeout=13,creationflags=subprocess.CREATE_NO_WINDOW)
            for line in reversed(result.stdout.decode('utf8',errors='replace').splitlines()):
                if line.startswith('{'):
                    info=json.loads(line)
                    if info.get('status')=='verified' and tuple(map(int,info['version'].split('.')))>tuple(map(int,VERSION.split('.'))):
                        self.message.emit('发现助手新版 '+info['version']+'；源码目录不会自动覆盖，请从项目 Releases 下载。')
                    break
        except Exception:pass  # Offline or unavailable metadata cannot stop statistics.
