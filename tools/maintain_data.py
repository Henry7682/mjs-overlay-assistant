"""Logged-in maintainer job. Independent data jobs; never runs game automation."""
import argparse
from datetime import datetime, timezone
import json
import msvcrt
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mjs_assistant.storage import BoardStore, write_json, read_json
from mjs_assistant.boards import validate_board
from mjs_assistant.board_channel import newer
from mjs_assistant.ocr import Ocr, Names
from mjs_assistant.updater import Updater
from tools.prepare_boards import prepare
from tools.publish_jiangce import publish


def run(publish_data=False, force=False):
    home=ROOT/'.research/maintenance';home.mkdir(parents=True,exist_ok=True)
    prior=read_json(home/'status.json',{})
    if not force and prior.get('finished') and prior.get('jobs') and all(j.get('success') for j in prior['jobs'].values()):
        if datetime.fromisoformat(prior['finished']).astimezone().date()==datetime.now().date():return True
    lock=(home/'run.lock').open('a+b');lock.seek(0);lock.write(b'1');lock.flush();lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:lock.close();raise RuntimeError('已有维护任务运行')
    report={'started':datetime.now(timezone.utc).isoformat(),'jobs':{}}
    def record(name,ok,text):
        previous=prior.get('jobs',{}).get(name,{})
        report['jobs'][name]={'success':ok,'message':text,'last_success':report['started'] if ok else previous.get('last_success')}
        write_json(home/'status.json',report)
    try:
        store=BoardStore(home/'official-state')
        try:
            drafts,message=Updater(home/'official-state',Ocr(),Names()).check(store.all_current(),force=True)
            for board in drafts or []:
                if not validate_board(board) and newer(board,store.all_current().get(board['mode_id'],{})):store.install(board)
            inputs=home/'boards-current';inputs.mkdir(exist_ok=True)
            for board in store.all_current().values():
                if board.get('completeness',{}).get('complete') and not validate_board(board):write_json(inputs/(board['mode_id']+'.json'),board)
            if list(inputs.glob('*.json')):prepare(inputs,home/'boards-channel')
            status=read_json(home/'official-state/update_state.json',{})
            record('official',status.get('status')=='success',message)
        except Exception as exc:record('official',False,type(exc).__name__+': '+str(exc)[:240])
        try:
            subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/sync-jiangce.ps1')],cwd=ROOT,check=True,timeout=3600)
            record('guides',True,'完整采集和候选库核验完成')
        except Exception as exc:record('guides',False,type(exc).__name__)
        if publish_data:
            for kind,channel in [('boards',home/'boards-channel'),('guides',ROOT/'.research/jiangce/channel')]:
                for host in ('GitHub','Gitee'):
                    try:
                        publish(channel,host,kind)
                        from mjs_assistant.jiangce_update import get_bytes
                        branch='boards-data' if kind=='boards' else 'jiangce-data'
                        base=('https://raw.githubusercontent.com/Henry7682/mjs-overlay-assistant/' if host=='GitHub' else 'https://gitee.com/henry7682/mjs-overlay-assistant/raw/')+branch+'/'
                        raw=(channel/'channel.json').read_bytes();meta=json.loads(raw)
                        name=meta['version']+'-'+meta['sha256']+('.json' if kind=='boards' else '.sqlite')
                        for filename,limit in [('channel.json',8192),('channel.sig',2048),(name,meta['size'])]:
                            if get_bytes(base+filename,limit)!=(channel/filename).read_bytes():raise ValueError('匿名回读不一致')
                        record(kind+'-'+host,True,'发布与匿名字节核验通过')
                    except Exception as exc:record(kind+'-'+host,False,type(exc).__name__)
        report['finished']=datetime.now(timezone.utc).isoformat();write_json(home/'status.json',report)
        write_json(home/('run-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json'),report)
        return all(x['success'] for x in report['jobs'].values())
    finally:lock.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');p.add_argument('--force',action='store_true');args=p.parse_args()
    raise SystemExit(0 if run(args.publish,args.force) else 1)
