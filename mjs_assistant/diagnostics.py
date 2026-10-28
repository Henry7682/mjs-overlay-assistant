"""Local, bounded diagnostics. No uploader, desktop capture, or UIA traversal."""
from __future__ import annotations
import collections
import dataclasses
import datetime as dt
import hashlib
import json
import logging
import logging.handlers
import os
import platform
import queue
import re
import threading
import time
import uuid
import zipfile
from pathlib import Path
from .version import VERSION
from .storage import write_json,read_json

_recorder=None
FIELDS={'mode','scene','phase','layout','items','seconds','request_id','round_id','stage','elapsed','selected',
        'cards','complete','reason','source','version','error','kind','status','dropped','rect','config','board','models','environment'}

def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items() if str(k).lower() not in {'token','password','cookie','authorization','clipboard','image_path','source_path'}}
    if isinstance(value,(tuple,list)):return [clean(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'(?i)(?<![a-z0-9])[A-Z]:[\\/](?!/)[^\s\"<>|]*','<local-path>',value)
        value=re.sub(r'(?i)(?:gh[pousr]_[a-z0-9_]+|github_pat_[a-z0-9_]+|bearer\s+\S+)','<secret>',value)
        return value[:16000]
    if value is None or isinstance(value,(bool,int,float)):return value
    return str(type(value).__name__)

def event(kind,**fields):
    if _recorder:
        try:_recorder.event(kind,**fields)
        except Exception:pass  # Diagnostics never unwind recognition/query.

def fault(reason):
    if _recorder:
        try:return _recorder.trigger(reason)
        except Exception:return None

def frame(source,image,**metadata):
    if _recorder:
        try:_recorder.frame(source,image,metadata,owned=True)
        except Exception:pass

class RedactedFormatter(logging.Formatter):
    def format(self,record):return clean(super().format(record))

def setup(folder,enabled=True,context=None):
    global _recorder
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    handler=logging.handlers.RotatingFileHandler(folder/'assistant.log',maxBytes=5_000_000,backupCount=9,encoding='utf8')
    handler.setFormatter(RedactedFormatter('%(asctime)s %(levelname)s %(message)s'))
    logger=logging.getLogger();logger.setLevel(logging.INFO);logger.addHandler(handler)
    _recorder=Recorder(folder,enabled=enabled,context=context)
    _recorder.text_handler=handler
    return _recorder

class Recorder:
    def __init__(self,folder,enabled=True,context=None):
        self.root=Path(folder)/'diagnostics';self.root.mkdir(parents=True,exist_ok=True)
        self.session=uuid.uuid4().hex;self.enabled=enabled;self.context=clean(context or {})
        self.q=queue.Queue(maxsize=2);self.events=queue.Queue(maxsize=256);self.ring=collections.deque();self.bytes=0;self.last={};self.active=None
        self.lock=threading.RLock();self.stopping=threading.Event();self.dropped=0;self.last_trigger={}
        self.mini_hwnd=0
        self.capture_generation=0
        self.handler=logging.handlers.RotatingFileHandler(self.root/'events.jsonl',maxBytes=5_000_000,backupCount=9,encoding='utf8')
        self.handler.setFormatter(logging.Formatter('%(message)s'))
        self.thread=threading.Thread(target=self._run,name='diagnostic-encoder',daemon=True);self.thread.start()
        self.capture_thread=threading.Thread(target=self._mini_loop,name='diagnostic-mini-capture',daemon=True);self.capture_thread.start()
        self.event('session',version=VERSION,environment={'os':platform.platform(),'architecture':platform.machine()},config=self.context)
        self.prune()

    def event(self,kind,**fields):
        row={'schema_version':1,'session_id':self.session,'event':str(kind)[:80],
             'time':dt.datetime.now(dt.timezone.utc).isoformat(),'monotonic':time.monotonic(),
             **clean({k:v for k,v in fields.items() if k in FIELDS})}
        try:self.events.put_nowait(json.dumps(row,ensure_ascii=False))
        except queue.Full:self.dropped+=1

    def set_enabled(self,enabled):
        with self.lock:
            self.enabled=bool(enabled)
            if not enabled:
                self.capture_generation+=1
                self.ring.clear();self.bytes=0
                while True:
                    try:self.q.get_nowait()
                    except queue.Empty:break
                if self.active:self.active['pending']=[];self.active['until']=time.monotonic()
        self.event('capture_setting',status='enabled' if enabled else 'disabled')

    def frame(self,source,image,metadata=None,owned=False):
        if source not in ('game','mini') or not self.enabled or image is None:return
        now=time.monotonic();gap=1 if source=='game' else .5
        if now-self.last.get(source,0)<gap:return
        self.last[source]=now
        # Capture.read already returns an owned immutable-for-consumers frame.
        # Keep a bounded reference rather than copying that full image on the UI
        # thread again. Other callers retain the safe copy default.
        if self.q.full() or image.nbytes>32_000_000:self.dropped+=1;return
        try:
            snapshot=image.view() if owned else image.copy()
            snapshot.flags.writeable=False
            self.q.put_nowait((source,snapshot,now,clean(metadata or {}),self.capture_generation))
        except queue.Full:self.dropped+=1

    def trigger(self,reason):
        now=time.monotonic();reason=clean(reason)
        with self.lock:
            while self.ring and now-self.ring[0][2]>30:self.bytes-=len(self.ring.popleft()[1])
            if now-self.last_trigger.get(reason,0)<60:return self.active['id'] if self.active else None
            self.last_trigger[reason]=now
            if self.active:return self.active['id']  # Do not extend a repeated fault indefinitely.
            if len(self.last_trigger)>64:self.last_trigger={reason:now}
            ident=dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
            self.active={'id':ident,'reason':reason,'until':now+10,'rows':[],'pending':list(self.ring) if self.enabled else []}
        self.event('fault',reason=reason,status=ident,dropped=self.dropped)
        return ident

    def _save(self,active,item):
        source,data,stamp,meta=item;folder=self.root/active['id'];folder.mkdir(exist_ok=True)
        saved=active.get('saved_bytes',0)
        if saved+len(data)>250_000_000:self.dropped+=1;return
        self.prune(reserve=saved+len(data)+1_000_000)
        if not (folder/'incident.json').exists():
            write_json(folder/'incident.json',{'schema_version':1,'kind':'mjs-diagnostic-incident','id':active['id'],
                'session_id':self.session,'incomplete':True,'frames':[],'reason':active['reason']})
        name=f'{len(active["rows"]):04d}-{source}.png'
        (folder/name).write_bytes(data)
        active['saved_bytes']=saved+len(data)
        active['rows'].append({'file':name,'source':source,'monotonic':stamp,'sha256':hashlib.sha256(data).hexdigest(),'metadata':meta})

    def _flush(self):
        with self.lock:
            active=self.active
            if not active:return
            pending=active.pop('pending',[])
        for item in pending:
            with self.lock:
                if self.enabled:self._save(active,item)
        with self.lock:
            if time.monotonic()>=active['until'] or self.stopping.is_set():
                folder=self.root/active['id'];folder.mkdir(exist_ok=True)
                write_json(folder/'incident.json',{'schema_version':1,'kind':'mjs-diagnostic-incident','id':active['id'],'session_id':self.session,'reason':active['reason'],
                    'version':VERSION,'frames':active['rows'],'dropped':self.dropped,'context':self.context,
                    'limitations':['画面为抽样；可能缺帧或在崩溃前丢失，不能重放Windows实时响应。']})
                self.active=None;self.prune()

    def _run(self):
        import cv2
        while not self.stopping.is_set() or not self.q.empty():
            try:
                self._flush_events()
                source,image,stamp,meta,generation=self.q.get(timeout=.2)
                if self.enabled and generation==self.capture_generation:
                    ok,encoded=cv2.imencode('.png',image,[cv2.IMWRITE_PNG_COMPRESSION,1])
                    if ok:
                        item=(source,encoded.tobytes(),stamp,meta)
                        with self.lock:
                            if self.enabled and generation==self.capture_generation:
                                self.ring.append(item);self.bytes+=len(item[1])
                                while self.ring and (stamp-self.ring[0][2]>30 or self.bytes>128_000_000):self.bytes-=len(self.ring.popleft()[1])
                                if self.active:self.active.setdefault('pending',[]).append(item)
            except queue.Empty:pass
            except Exception:self.dropped+=1
            try:self._flush()
            except Exception:self.dropped+=1
        self._flush()
        self._flush_events()

    def _flush_events(self):
        while True:
            try:message=self.events.get_nowait()
            except queue.Empty:break
            self.handler.handle(logging.LogRecord('diagnostic',logging.INFO,'',0,message,(),None))

    def _mini_loop(self):
        cap=None;bound=0
        while not self.stopping.wait(.5):
            hwnd=self.mini_hwnd if self.enabled else 0
            try:
                if hwnd!=bound:
                    if cap:cap.stop();cap=None
                    bound=0
                    if hwnd:
                        from .mini_windows import mini_windows
                        from .capture import Capture
                        if hwnd in mini_windows():cap=Capture(hwnd);bound=hwnd
                if cap:
                    image,rect,stamp=cap.read();self.frame('mini',image,{'rect':rect},owned=True)
            except Exception:
                if cap:
                    try:cap.stop()
                    except Exception:pass
                cap=None;bound=0
        if cap:
            try:cap.stop()
            except Exception:pass

    def prune(self,reserve=0):
        now=time.time();folders=[]
        for path in self.root.parent.glob('assistant.log*'):
            if path.is_file() and now-path.stat().st_mtime>14*86400:path.unlink(missing_ok=True)
        for path in self.root.iterdir():
            if path.is_file() and path.name.startswith('events.jsonl') and now-path.stat().st_mtime>14*86400:path.unlink(missing_ok=True)
            if path.is_dir() and re.fullmatch(r'\d{8}-\d{6}-[0-9a-f]{6}',path.name) and (path/'incident.json').is_file():
                if self.active and self.active['id']==path.name:continue
                marker=read_json(path/'incident.json',{})
                if marker.get('kind')!='mjs-diagnostic-incident' or marker.get('id')!=path.name:continue
                files=list(path.iterdir())
                if any(not p.is_file() or p.is_symlink() for p in files):continue
                folders.append((path.stat().st_mtime,path,files,sum(p.stat().st_size for p in files)))
        total=sum(x[3] for x in folders)
        for stamp,path,files,size in sorted(folders):
            if now-stamp>7*86400 or total+reserve>500_000_000:
                for p in files:p.unlink(missing_ok=True)
                path.rmdir();total-=size

    def close(self):
        self.stopping.set();self.capture_thread.join(timeout=2);self.thread.join(timeout=4)
        if not self.thread.is_alive():self.handler.close()
        handler=getattr(self,'text_handler',None)
        if handler:logging.getLogger().removeHandler(handler);handler.close()

    def export(self,destination,selected=None):
        """selected maps approved image paths to replacement PNG bytes (redactions)."""
        selected=selected or {};files={}
        self._flush_events()
        for path in self.root.glob('events.jsonl*'):
            if path.is_file():files['logs/'+path.name]=path.read_bytes()
        for folder in self.root.iterdir():
            if folder.is_dir() and re.fullmatch(r'\d{8}-\d{6}-[0-9a-f]{6}',folder.name):
                p=folder/'incident.json'
                if p.is_file():files['incidents/'+folder.name+'.json']=p.read_bytes()
        for path,data in selected.items():
            p=Path(path).resolve()
            if not p.is_relative_to(self.root.resolve()) or p.suffix!='.png' or not p.is_file():raise ValueError('只允许导出已预览的诊断图片')
            files['images/'+p.parent.name+'/'+p.name]=data
        summary={'schema_version':1,'app_version':VERSION,'session_id':self.session,'contains_images':bool(selected),
                 'context':self.context,'limitations':['不包含未采集画面；外部UIA时序不可离线完全复现。']}
        files['summary.json']=json.dumps(summary,ensure_ascii=False,indent=2).encode('utf8')
        return export_parts(destination,files)

def export_parts(destination,files,limit=20_000_000):
    dest=Path(destination);dest.mkdir(parents=True,exist_ok=True)
    ident='feedback-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
    batches=[];current={};size=0
    for name,data in files.items():
        if len(data)>limit-100_000:raise ValueError('单个文件超过附件上限，请减少画面尺寸后重试')
        if size+len(data)>limit-100_000 and current:batches.append(current);current={};size=0
        current[name]=data;size+=len(data)
    if current:batches.append(current)
    outputs=[]
    for i,batch in enumerate(batches,1):
        path=dest/f'{ident}-{i:02d}.zip'
        manifest={'schema_version':1,'bundle_id':ident,'part':i,'parts':len(batches),'files':[
            {'name':n,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in batch.items()]}
        with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as archive:
            for n,b in batch.items():archive.writestr(n,b)
            archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
        outputs.append(path)
    return outputs
