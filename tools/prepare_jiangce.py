"""Stage an immutable data file and its signed manifest for the jiangce-data branch."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mjs_assistant.jiangce import GuideBook
from mjs_assistant.jiangce_update import verify


def prepare(database, channel):
    book=GuideBook(database)
    channel.mkdir(parents=True,exist_ok=True)
    pointer=channel/'channel.json'
    prior={}
    if pointer.exists():
        prior, prior_name=verify(pointer.read_bytes(),pointer.with_suffix('.sig').read_bytes())
        if prior['content_hash']==book.content_hash:
            if hashlib.sha256((channel/prior_name).read_bytes()).hexdigest()!=prior['sha256']:
                raise ValueError('Existing snapshot is corrupt')
            print('Unchanged',prior_name)
            return
    raw=database.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    version=datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    if version<=prior.get('version',''):
        raise ValueError('Data version must advance')
    m=dict(kind='jiangce-v1',version=version,sha256=sha,size=len(raw),date=book.date,
           count=len(book.cards),content_hash=book.content_hash)
    with tempfile.TemporaryDirectory(dir=channel) as temp:
        manifest=Path(temp)/'channel.json'
        manifest.write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
        subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                        str(ROOT/'release/sign.ps1'),'-Manifest',str(manifest.resolve())],check=True)
        _,name=verify(manifest.read_bytes(),manifest.with_suffix('.sig').read_bytes())
        with (channel/name).open('xb') as out:
            out.write(raw)
        manifest.with_suffix('.sig').replace(pointer.with_suffix('.sig'))
        manifest.replace(pointer)
    print(name)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('database',type=Path)
    p.add_argument('channel',type=Path)
    args=p.parse_args()
    prepare(args.database,args.channel)

