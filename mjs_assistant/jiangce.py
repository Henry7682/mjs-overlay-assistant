"""Read-only, round-pinned JiangCe strategy data."""
from contextlib import closing
from pathlib import Path
import json
import re
import hashlib
import sqlite3

from .storage import ASSETS

SEED = ASSETS/'jiangce'/'guides.sqlite'


class GuideBook:
    def __init__(self, path):
        with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA quick_check').fetchone()!=('ok',):
                raise ValueError('《名将小助手》小程序内置库完整性检查失败')
            self.date,self.content_hash=db.execute('SELECT date,content_hash FROM meta').fetchone()
            self.cards=[]
            bodies=[]
            for ident,body in db.execute('SELECT id,body FROM guide ORDER BY seq'):
                c=json.loads(body)
                if (c['id']!=ident or not re.fullmatch('[0-9A-Z]{26}',ident)
                        or c['url']!=f'https://www.jiangce.online/combos/{ident}'
                        or len(c['heroes'])!=2 or len(set(c['heroes']))!=2):
                    raise ValueError('无效的《名将小助手》小程序组合')
                c['seats']=[(a,sa,b,sb) for v in c['variants'] if v.get('seats')
                            for (a,sa),(b,sb) in [v['seats']]]
                for v in c['variants']:
                    seats=v.get('seats',[])
                    if seats and (len(seats)!=2 or {h for h,s in seats}!=set(c['heroes'])
                                  or len({s for h,s in seats})!=2 or any(s not in (1,2,3,4) for h,s in seats)):
                        raise ValueError('《名将小助手》小程序站位无效')
                    if v.get('rating') and not re.fullmatch('[0-5]/5',v['rating']):
                        raise ValueError('《名将小助手》小程序评分无效')
                self.cards.append(c)
                bodies.append(body)
            if hashlib.sha256('\n'.join(bodies).encode()).hexdigest()!=self.content_hash:
                raise ValueError('《名将小助手》小程序内置库内容校验失败')
            if not self.cards:
                raise ValueError('《名将小助手》小程序内置库没有攻略')

    def selection(self, own, ally, locked=None):
        own=set(own)
        ally={locked} if locked else set(ally)
        return tuple(c for c in self.cards for a,b in [c['heroes']]
                     if (a in own and b in ally) or (b in own and a in ally))

    def battle(self,names,partial=False):
        heroes=set(names)
        if len(heroes)==1 and partial:
            return tuple(c for c in self.cards if heroes.intersection(c['heroes']))
        return tuple(c for c in self.cards if heroes==set(c['heroes'])) if len(heroes)==2 else ()


def preferred(folder):
    """Only finalized, hash-named files can be visible to a new round."""
    from .jiangce_update import installed
    for path in installed(folder):
        try:
            return GuideBook(path)
        except (OSError,sqlite3.Error,ValueError,TypeError,KeyError):
            continue
    return GuideBook(SEED)

