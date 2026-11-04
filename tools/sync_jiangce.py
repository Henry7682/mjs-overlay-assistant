"""Archive public combination pages. Resume by supplying the same snapshot directory."""
import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
import time

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.jiangce.online'
ID = re.compile(r'/combos/([0-9A-Z]{26})')


def listing(raw, page):
    soup = BeautifulSoup(raw.decode('utf-8'), 'html.parser')
    nav = soup.select_one('nav.pagination')
    match = nav and re.search(r'第\s*(\d+)\s*/\s*(\d+)\s*页', nav.get_text())
    if not match or int(match[1]) != page or page > int(match[2]):
        raise ValueError(f'Invalid pagination on page {page}')
    cards = []
    for a in soup.select('a.combo-card'):
        href = a['href'].removeprefix(BASE)
        found = ID.fullmatch(href)
        if not found:
            raise ValueError(f'Unexpected detail URL: {href}')
        cards.append(found[1])
    if not cards or len(cards) != len(set(cards)):
        raise ValueError(f'Missing or duplicate cards on page {page}')
    return int(match[2]), cards


def digest(data):
    return hashlib.sha256(data).hexdigest()


def collect(folder):
    folder.mkdir(parents=True, exist_ok=True)
    index_path = folder/'index.json'
    index = json.loads(index_path.read_text('utf-8')) if index_path.exists() else {}
    session = requests.Session()
    session.headers['User-Agent'] = 'MjsOverlay-JiangCeSync/1 (maintainer snapshot)'

    def fetch(url, name):
        path = folder/(name+'.html')
        if name in index and path.is_file():
            data = path.read_bytes()
            if index[name]['url'] == url and index[name]['sha256'] == digest(data):
                return data
        for attempt in range(4):
            time.sleep(.30)
            try:
                r = session.get(url, timeout=(8, 20), allow_redirects=False)
                if r.status_code in (429, 503):
                    retry = r.headers.get('Retry-After','')
                    if retry:
                        delay = float(retry) if retry.isdigit() else parsedate_to_datetime(retry).timestamp()-time.time()
                        if delay > 120:
                            raise RuntimeError(f'Resume after {retry}')
                        time.sleep(max(0,delay))
                r.raise_for_status()
                if r.status_code != 200:
                    raise ValueError(f'Unexpected status {r.status_code}')
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
        data = r.content
        path.write_bytes(data)
        index[name] = dict(url=url, sha256=digest(data), time=datetime.now(timezone.utc).isoformat())
        tmp = index_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(index, ensure_ascii=False),encoding='utf-8')
        tmp.replace(index_path)
        return data

    def pages(prefix):
        result = []
        total = None
        seen = set()
        page = 1
        while total is None or page <= total:
            url = BASE + ('/' if page == 1 else f'/?page={page}')
            count, ids = listing(fetch(url,f'{prefix}-{page:04}'),page)
            if (total is not None and count != total) or seen.intersection(ids):
                raise ValueError('Listing changed during capture; start a fresh snapshot')
            total = count
            seen.update(ids)
            result.append(ids)
            page += 1
        return result

    groups = pages('page')
    for n, ident in enumerate(x for group in groups for x in group):
        fetch(f'{BASE}/combos/{ident}', ident)
        if n % 50 == 0:
            print('Details',n+1,flush=True)
    if pages('verify') != groups:
        raise ValueError('Pagination changed; retain archive and start a fresh snapshot')
    print('Verified pages and details:',len(groups),sum(map(len,groups)),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot',type=Path)
    collect(parser.parse_args().snapshot)

