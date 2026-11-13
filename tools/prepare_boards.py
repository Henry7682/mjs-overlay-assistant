"""Sign validated per-mode official boards; raw images remain in the private archive."""
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
from mjs_assistant.board_channel import validate_snapshot, verify


def prepare(inputs, channel):
    boards=[]
    for path in sorted(inputs.glob('*.json')):
        board=json.loads(path.read_text('utf8'))
        # No private filesystem paths, raw OCR dump or unrelated runtime state.
        keys=('schema_version','mode_id','mode','period_start','period_end','source_url',
              'image_sha256','review_status','heroes','expected_count','issues','mode_evidence',
              'completeness','revision')
        boards.append({key:board[key] for key in keys if key in board})
    raw=json.dumps({'schema_version':1,'boards':boards},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    sha=hashlib.sha256(raw).hexdigest()
    channel.mkdir(parents=True,exist_ok=True)
    prior=channel/'channel.json'
    if prior.exists():
        old,name=verify(prior.read_bytes(),prior.with_suffix('.sig').read_bytes())
        if old['sha256']==sha:
            validate_snapshot((channel/name).read_bytes(),old);return name
    version=datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    meta={'kind':'official-boards-v1','version':version,'sha256':sha,'size':len(raw)}
    validate_snapshot(raw,meta)
    with tempfile.TemporaryDirectory(dir=channel) as temp:
        manifest=Path(temp)/'channel.json';manifest.write_text(json.dumps(meta,indent=2)+'\n','utf8')
        subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'release/sign.ps1'),'-Manifest',str(manifest)],check=True)
        _,name=verify(manifest.read_bytes(),manifest.with_suffix('.sig').read_bytes())
        with (channel/name).open('xb') as out:out.write(raw)
        manifest.with_suffix('.sig').replace(prior.with_suffix('.sig'));manifest.replace(prior)
    return name


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('inputs',type=Path);p.add_argument('channel',type=Path)
    args=p.parse_args();print(prepare(args.inputs,args.channel))
