"""Publish only validated guide data to the dedicated data branch (fast-forward only)."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import getproxies

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mjs_assistant.jiangce import GuideBook
from mjs_assistant.jiangce_update import verify

REMOTES={'GitHub':'https://github.com/Henry7682/mjs-overlay-assistant.git',
         'Gitee':'https://gitee.com/henry7682/mjs-overlay-assistant.git'}
REF='refs/heads/jiangce-data'


def publish(folder,host,kind='guides'):
    ref=REF if kind=='guides' else 'refs/heads/boards-data'
    def git(*args,data=None):
        environment=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
        for scheme,url in getproxies().items():
            if scheme in ('http','https'):environment.setdefault(scheme.upper()+'_PROXY',url)
        return subprocess.run(['git',*args],cwd=ROOT,input=data,stdout=subprocess.PIPE,check=True,
                              env=environment,timeout=120).stdout
    raw=(folder/'channel.json').read_bytes()
    sig=(folder/'channel.sig').read_bytes()
    from mjs_assistant.board_channel import verify as verify_boards, validate_snapshot
    meta,name=(verify if kind=='guides' else verify_boards)(raw,sig)
    db=folder/name
    if db.stat().st_size!=meta['size'] or hashlib.sha256(db.read_bytes()).hexdigest()!=meta['sha256']:
        raise ValueError('Database hash mismatch')
    if kind=='guides':
        book=GuideBook(db)
        if len(book.cards)!=meta['count'] or book.content_hash!=meta['content_hash']:
            raise ValueError('Database content mismatch')
    else:validate_snapshot(db.read_bytes(),meta)
    remote=REMOTES[host]
    prior=git('ls-remote',remote,ref).split()
    parent=[]
    entries={}
    if prior:
        sha=prior[0].decode()
        git('fetch','--no-tags',remote,ref)
        if git('rev-parse','FETCH_HEAD').decode().strip()!=sha:
            raise ValueError('Remote advanced; retry')
        old,oldfile=(verify if kind=='guides' else verify_boards)(git('show',sha+':channel.json'),git('show',sha+':channel.sig'))
        if raw==git('show',sha+':channel.json'):
            print('Already published');return
        if old['version']>=meta['version']:
            raise ValueError('Refusing rollback or mutable version')
        parent=['-p',sha]
        for line in git('ls-tree',sha).splitlines():
            entries[line.split(b'\t')[1].decode()]=line
        if name in entries:
            raise ValueError('Immutable filename exists')
    for fname in (name,'channel.json','channel.sig'):
        blob=git('hash-object','-w','--no-filters',str((folder/fname).resolve())).strip()
        entries[fname]=b'100644 blob '+blob+b'\t'+fname.encode()
    tree=git('mktree',data=b'\n'.join(entries.values())+b'\n').strip().decode()
    sha=git('commit-tree',tree,*parent,'-m','Publish JiangCe guide data '+meta['version']).strip().decode()
    # Normal push rejects a concurrent publisher or a non-fast-forward update.
    git('push',remote,sha+':'+ref)
    print(host,sha)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('folder',type=Path)
    p.add_argument('host',choices=REMOTES)
    p.add_argument('--kind',choices=('guides','boards'),default='guides')
    args=p.parse_args()
    publish(args.folder,args.host,args.kind)

