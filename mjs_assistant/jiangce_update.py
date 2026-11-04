"""Independent signed data channel. Never downloads code or touches software updates."""
import base64
from datetime import date
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading

import requests
from .storage import ASSETS, write_json

ROOTS=(
    'https://raw.githubusercontent.com/Henry7682/mjs-overlay-assistant/jiangce-data/',
    'https://gitee.com/henry7682/mjs-overlay-assistant/raw/jiangce-data/',
)
FILENAME=re.compile(r'(\d{14})-([0-9a-f]{64})\.sqlite')
MAX_BYTES=16*1024*1024


def get_bytes(url, limit):
    with requests.get(url,timeout=(4,8),stream=True) as r:
        r.raise_for_status()
        buf=bytearray()
        for part in r.iter_content(65536):
            buf.extend(part)
            if len(buf)>limit:
                raise ValueError('组合库文件超过大小限制')
        return bytes(buf)


def verify(raw,sig):
    key=(ASSETS/'jiangce/public-key.xml').read_text('utf-8')
    script="""$ErrorActionPreference='Stop'; $v=[Console]::In.ReadToEnd()|ConvertFrom-Json;
$r=New-Object Security.Cryptography.RSACryptoServiceProvider; $r.PersistKeyInCsp=$false;
try {$r.FromXmlString($v.key); if(-not $r.VerifyData([Convert]::FromBase64String($v.data),'SHA256',[Convert]::FromBase64String($v.sig))){exit 1}} finally {$r.Dispose()}"""
    ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.run([str(ps),'-NoProfile','-NonInteractive','-Command',script],input=json.dumps(dict(
        key=key,data=base64.b64encode(raw).decode(),sig=sig.decode('ascii'))).encode(),timeout=8,
        creationflags=subprocess.CREATE_NO_WINDOW,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    m=json.loads(raw)
    filename=f"{m['version']}-{m['sha256']}.sqlite"
    if m.get('kind')!='jiangce-v1' or not FILENAME.fullmatch(filename) or not 0<m['size']<=MAX_BYTES:
        raise ValueError('不兼容的将策更新清单')
    return m,filename


def installed(folder):
    seed_version=json.loads((ASSETS/'jiangce/channel.json').read_text('utf-8'))['version']
    paths=sorted((folder/'jiangce').glob('*.sqlite'),reverse=True)
    for path in paths:
        match=FILENAME.fullmatch(path.name)
        if match and match[1]>seed_version and path.stat().st_size<=MAX_BYTES and hashlib.sha256(path.read_bytes()).hexdigest()==match[2]:
            yield path


def refresh(folder):
    from .jiangce import GuideBook
    dest=folder/'jiangce'
    dest.mkdir(exist_ok=True,parents=True)
    seed=json.loads((ASSETS/'jiangce/channel.json').read_text('utf-8'))
    version=max([seed['version']]+[p.name[:14] for p in installed(folder)])
    candidates=[]
    for root in ROOTS:
        try:
            m,filename=verify(get_bytes(root+'channel.json',8192),get_bytes(root+'channel.sig',2048))
            candidates.append((m['version'],root,m,filename))
        except Exception as exc:
            logging.info('jiangce manifest unavailable: %s',type(exc).__name__)
    if not candidates:
        return '未取得有效签名清单，沿用本地组合库'
    failed=False
    for newer,root,m,filename in sorted(candidates,key=lambda item:item[0],reverse=True):
        if newer<=version:
            continue
        tmp=None
        try:
            raw=get_bytes(root+filename,m['size'])
            if len(raw)!=m['size'] or hashlib.sha256(raw).hexdigest()!=m['sha256']:
                raise ValueError('数据包校验失败')
            with tempfile.NamedTemporaryFile(dir=dest,delete=False) as f:
                tmp=Path(f.name)
                f.write(raw)
            book=GuideBook(tmp)
            if book.content_hash!=m['content_hash'] or len(book.cards)!=m['count']:
                raise ValueError('数据清单与组合库不一致')
            tmp.replace(dest/filename)
            return '已更新组合库，新对局使用'
        except Exception as exc:
            failed=True
            logging.info('jiangce candidate unavailable: %s',type(exc).__name__)
        finally:
            if tmp:tmp.unlink(missing_ok=True)
    return '新版下载失败，沿用本地组合库' if failed else '组合库已是当前可用版本'


class DailyCheck:
    def __init__(self,folder):
        self.folder=folder
        self.state=folder/'jiangce-check.json'
        try:self.last=json.loads(self.state.read_text('utf-8'))
        except (ValueError,OSError):self.last={}
        self.thread=None

    def check(self):
        today=date.today().isoformat()
        if self.last.get('date')==today or (self.thread and self.thread.is_alive()):
            return
        self.last={'date':today,'status':'正在检查组合库'}
        def run():
            try:status=refresh(self.folder)
            except Exception:
                logging.exception('jiangce sync failed')
                status='更新失败，沿用本地组合库'
            self.last={'date':today,'status':status}
            write_json(self.state,self.last)
        self.thread=threading.Thread(target=run,name='jiangce-update',daemon=True)
        self.thread.start()

