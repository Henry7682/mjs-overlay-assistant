"""Signed official-board distribution; never substitutes community hero rates."""
import hashlib
import json
import re
from urllib.parse import urlparse

from .boards import validate_board
from .jiangce_update import get_bytes, verify_signature
from .modes import MODES
from .storage import write_json

ROOTS = (
    'https://raw.githubusercontent.com/Henry7682/mjs-overlay-assistant/boards-data/',
    'https://gitee.com/henry7682/mjs-overlay-assistant/raw/boards-data/',
)


def validate_snapshot(raw, meta):
    if len(raw)!=meta['size'] or hashlib.sha256(raw).hexdigest()!=meta['sha256']:
        raise ValueError('榜单包大小或哈希不一致')
    payload=json.loads(raw)
    boards=payload.get('boards', [])
    if payload.get('schema_version')!=1 or not boards or len(boards)>len(MODES):
        raise ValueError('榜单快照结构不兼容')
    modes=set()
    for board in boards:
        if validate_board(board) or not board.get('completeness',{}).get('complete'):
            raise ValueError('签名榜单未通过内容及完整性校验')
        if board['mode_id'] in modes:
            raise ValueError('榜单模式重复')
        modes.add(board['mode_id'])
        source=urlparse(board['source_url'])
        if source.scheme!='https' or source.hostname!='www.taptap.cn' or not re.fullmatch(r'/moment/\d+',source.path):
            raise ValueError('不是登记的官方榜单出处')
    return boards


def verify(raw, sig):
    meta=verify_signature(raw,sig)
    if (meta.get('kind')!='official-boards-v1' or
        not re.fullmatch(r'\d{14}',str(meta.get('version',''))) or
        not re.fullmatch(r'[0-9a-f]{64}',str(meta.get('sha256',''))) or
        type(meta.get('size')) is not int or not 0<meta['size']<=8*1024*1024):
        raise ValueError('榜单清单无效')
    return meta, meta['version']+'-'+meta['sha256']+'.json'


def newer(candidate, current):
    if candidate['period_end']>current.get('period_end',''):
        return True
    # A same-period revision needs explicit provenance tying it to the replaced image.
    revision=candidate.get('revision',{})
    return (candidate['period_end']==current.get('period_end') and
            candidate['image_sha256']!=current.get('image_sha256') and
            revision.get('replaces_sha256')==current.get('image_sha256') and
            bool(revision.get('source_url')) and revision.get('status')=='source-reviewed')


def discover(folder, current):
    candidates=[]; errors=[]
    for root in ROOTS:
        try:
            raw=get_bytes(root+'channel.json',8192);sig=get_bytes(root+'channel.sig',2048)
            meta,name=verify(raw,sig)
            candidates.append((meta['version'],root,meta,name,raw,sig))
        except Exception as exc:errors.append(type(exc).__name__)
    best={}; sources=[]
    for version,root,meta,name,manifest,sig in sorted(candidates,reverse=True,key=lambda x:x[0]):
        try:
            cache=folder/'board-channel'/name
            raw=cache.read_bytes() if cache.exists() else get_bytes(root+name,meta['size'])
            boards=validate_snapshot(raw,meta)
            cache.parent.mkdir(parents=True,exist_ok=True)
            if not cache.exists():
                temp=cache.with_suffix('.tmp');temp.write_bytes(raw);temp.replace(cache)
            sources.append(root)
            for board in boards:
                mode=board['mode_id']
                if newer(board,best.get(mode,current.get(mode,{}))):
                    best[mode]=dict(board,distribution={'source':root,'version':version})
        except Exception as exc:errors.append(type(exc).__name__)
    state={'status':'success' if sources else 'unavailable','sources':sources,'errors':errors}
    write_json(folder/'board-channel-state.json',state)
    return list(best.values()),state
