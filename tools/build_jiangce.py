"""Rebuild the guide database strictly from a verified private archive."""
import argparse
import json
import sqlite3
from pathlib import Path
import re
import tempfile
from contextlib import closing

from bs4 import BeautifulSoup
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.sync_jiangce import BASE, digest, listing

ROOT = Path(__file__).resolve().parents[1]


def parse_detail(raw, ident):
    page = BeautifulSoup(raw.decode('utf-8'), 'html.parser')
    detail = page.select_one('.combo-detail')
    if not detail:
        raise ValueError('Missing detail')
    heroes = [n.get_text(strip=True) for n in detail.select('.combo-members-grid .general-card-name')]
    if len(heroes) != 2 or heroes[0] == heroes[1]:
        raise ValueError('Expected two distinct members')
    reason = detail.select_one('.prose')
    author = detail.find('p', string=re.compile('分享者：'))
    if reason is None or not author or not detail.select_one('.position-grid'):
        raise ValueError('Incomplete detail structure')
    variants = []
    for item in detail.select('.position-grid > div'):
        group = item.strong.get_text(strip=True)
        positions = item.p.get_text(' ',strip=True)
        variant = {'group':group}
        if positions != '站位未提供':
            pairs = re.findall(r'(\S+)：\s*([1-4])\s*号位',positions)
            if len(pairs)!=2 or {p[0] for p in pairs}!=set(heroes) or pairs[0][1]==pairs[1][1]:
                raise ValueError(f'Unknown seating: {positions}')
            variant['seats'] = list((hero,int(seat)) for hero,seat in pairs)
        rating = item.select_one('.source-rating[aria-label]')
        if rating:
            m = re.fullmatch(r'来源评分\s*([0-5]/5)',rating['aria-label'])
            if not m:
                raise ValueError('Unknown rating')
            variant['rating'] = m[1]
        variants.append(variant)
    return dict(id=ident,heroes=heroes,variants=variants,reason=reason.get_text('\n',strip=True),
                author=author.get_text(strip=True).split('：',1)[1].strip(),url=f'{BASE}/combos/{ident}')


def build(snapshot, output):
    index = json.loads((snapshot/'index.json').read_text('utf-8'))

    def raw(name, url):
        data = (snapshot/(name+'.html')).read_bytes()
        if index[name]['url']!=url or digest(data)!=index[name]['sha256']:
            raise ValueError(f'Archive verification failed: {name}')
        return data

    count = listing(raw('page-0001',BASE+'/'),1)[0]
    ids = []
    page_counts = []
    for page in range(1,count+1):
        url = BASE + ('/' if page==1 else f'/?page={page}')
        n, group = listing(raw(f'page-{page:04}',url),page)
        if listing(raw(f'verify-{page:04}',url),page)!=(n,group) or n!=count or set(ids).intersection(group):
            raise ValueError(f'Pagination inconsistent at {page}')
        ids.extend(group)
        page_counts.append(len(group))
    cards = []
    for ident in ids:
        try:
            cards.append(parse_detail(raw(ident, f'{BASE}/combos/{ident}'), ident))
        except Exception as exc:
            raise ValueError(f'{ident}: {exc}') from exc
    known = set(json.loads((ROOT/'assets/names.json').read_text('utf-8'))['names'])
    unknown = sorted({h for c in cards for h in c['heroes']} - known)
    serial = [json.dumps(c,ensure_ascii=False,separators=(',',':')) for c in cards]
    date = index['page-0001']['time'][:10]
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent,delete=False) as f:
        tmp = Path(f.name)
    try:
        with closing(sqlite3.connect(tmp)) as conn:
            conn.execute('CREATE TABLE guide (seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, body TEXT NOT NULL)')
            conn.execute('CREATE TABLE meta (date TEXT, content_hash TEXT)')
            conn.execute('INSERT INTO meta VALUES (?,?)',(date,digest('\n'.join(serial).encode())))
            conn.executemany('INSERT INTO guide VALUES (?,?,?)',((i,c['id'],s) for i,(c,s) in enumerate(zip(cards,serial))))
            conn.commit()
        tmp.replace(output)
    finally:
        tmp.unlink(missing_ok=True)
    report = dict(pages=count,page_counts=page_counts,unique=len(ids),database_sha256=digest(output.read_bytes()),unknown_names=unknown)
    (snapshot/'build-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(report)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('snapshot', type=Path)
    p.add_argument('output', type=Path)
    args=p.parse_args()
    build(args.snapshot,args.output)


