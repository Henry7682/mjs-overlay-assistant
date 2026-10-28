"""Verify downloaded wheels against PyPI and create Windows CPython 3.11 locks."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT=Path(__file__).resolve().parents[1]

def record(path):
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    with zipfile.ZipFile(path) as z:
        meta=BytesParser().parsebytes(z.read(next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))))
    name,version=meta['Name'],meta['Version']
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as r: info=json.load(r)
    match=next((a for a in info['urls'] if a['filename']==path.name and a['digests']['sha256']==digest),None)
    if not match:raise ValueError(f'Wheel is not verified by PyPI: {path.name}')
    return canonicalize_name(name),dict(name=name,version=version,filename=path.name,bytes=path.stat().st_size,
        sha256=digest,source=match['url'],architecture='win_amd64 or platform-independent',
        license=meta['License-Expression'] or meta['License'] or 'See bundled upstream license',
        requires=meta.get_all('Requires-Dist',[]))

def main():
    p=argparse.ArgumentParser();p.add_argument('wheels',type=Path);a=p.parse_args()
    with ThreadPoolExecutor(max_workers=6) as pool:records=dict(pool.map(record,sorted(a.wheels.glob('*.whl'))))
    def closure(names):
        found=set();pending=list(names)
        while pending:
            name=canonicalize_name(pending.pop())
            if name in found:continue
            found.add(name)
            for raw in records[name]['requires']:
                req=Requirement(raw)
                if not req.marker or req.marker.evaluate({'extra':''}):pending.append(req.name)
        return found
    roots=[Requirement(line).name for line in (ROOT/'requirements-runtime.in').read_text().splitlines() if line and not line.startswith('#')]
    runtime=closure(roots);development=closure(roots+['pytest','pyinstaller'])
    for role,names in [('runtime',runtime),('dev',development)]:
        lines=['# Windows x64 / CPython 3.11; verified wheel hashes. Do not edit by hand.']
        for name in sorted(names):
            r=records[name];lines.append(f'{r["name"]}=={r["version"]} --hash=sha256:{r["sha256"]}')
        (ROOT/f'requirements-{role}.lock.txt').write_text('\n'.join(lines)+'\n','utf8')
    for name,r in records.items():r['role']='runtime' if name in runtime else 'development'
    (ROOT/'release/dependencies.json').write_text(json.dumps({'schema_version':1,'python':'3.11','platform':'win_amd64',
        'components':list(records.values()),'notes':['OpenCV distributions retained because windows-capture and RapidOCR declare different package names. No Qt Addons/PDF/WebEngine.']},ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({'runtime':len(runtime),'development':len(development),'verified_wheels':len(records)}))

if __name__=='__main__':main()
