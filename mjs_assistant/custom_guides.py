"""User-owned overrides. Signed distribution databases are never edited."""
import copy
import json
import re
import shutil
import uuid
from .storage import write_json


def validate_card(card):
    heroes = card.get('heroes', [])
    if (len(heroes) != 2 or len(set(heroes)) != 2 or
            any(not isinstance(h, str) or not re.fullmatch(r'[\u3400-\u9fff]{2,6}', h) for h in heroes)):
        raise ValueError('请填写两名不同武将的完整中文姓名')
    if not isinstance(card.get('reason'), str) or not card['reason'].strip() or len(card['reason']) > 20000:
        raise ValueError('攻略说明不能为空，最多20000字')
    variants = card.get('variants')
    if not isinstance(variants, list) or not 1 <= len(variants) <= 12:
        raise ValueError('请添加1至12条站位说明')
    seen = set()
    for v in variants:
        seats = v.get('seats', [])
        if seats and (len(seats) != 2 or {x[0] for x in seats} != set(heroes) or
                      any(type(x[1]) is not int or x[1] not in (1,2,3,4) for x in seats) or
                      len({x[1] for x in seats}) != 2):
            raise ValueError('站位必须属于这两名武将，且不能重复')
        key = tuple(sorted((h,s) for h,s in seats))
        if key in seen: raise ValueError('同一站位不能重复')
        seen.add(key)
        if v.get('rating') and not re.fullmatch(r'[0-5]/5', v['rating']):
            raise ValueError('评分必须为0/5至5/5，或留空')


class CustomGuides:
    def __init__(self, folder):
        self.path = folder / 'custom-guides.json'
        self.data = {'schema_version': 1, 'overrides': {}, 'hidden': []}
        if self.path.exists():
            if self.path.stat().st_size > 8*1024*1024: raise ValueError('个人组合文件过大')
            self.data = json.loads(self.path.read_text('utf-8'))
            if (self.data.get('schema_version') != 1 or not isinstance(self.data.get('overrides'), dict)
                    or not isinstance(self.data.get('hidden'), list)
                    or any(not isinstance(x,str) for x in self.data['hidden'])):
                raise ValueError('个人组合文件格式无效，请从备份恢复')
            for ident, card in self.data['overrides'].items():
                if card.get('id') != ident: raise ValueError('个人组合ID不一致')
                validate_card(card)

    def save(self):
        if self.path.exists(): shutil.copy2(self.path, self.path.with_suffix('.previous.json'))
        write_json(self.path, self.data)

    def put(self, card, ident=None):
        card = copy.deepcopy(card)
        validate_card(card)
        ident = ident or 'local-' + uuid.uuid4().hex
        card.setdefault('original_author',card.get('author','本机用户'))
        card.update(id=ident, custom=True, author='本机用户')
        # Preserve only a known original-source URL, never an arbitrary user URL.
        url = card.get('url','')
        card['url'] = url if re.fullmatch(r'https://www\.jiangce\.online/combos/[0-9A-Z]{26}',url) else ''
        self.data['overrides'][ident] = card
        self.data['hidden'] = [x for x in self.data['hidden'] if x != ident]
        self.save()
        return ident

    def hide(self, ident):
        if ident not in self.data['hidden']: self.data['hidden'].append(ident)
        self.save()

    def restore(self, ident):
        self.data['overrides'].pop(ident, None)
        self.data['hidden'] = [x for x in self.data['hidden'] if x != ident]
        self.save()

    def merge(self, cards, include_hidden=False):
        merged = {c['id']: copy.deepcopy(c) for c in cards}
        merged.update(copy.deepcopy(self.data['overrides']))
        for ident, card in merged.items():
            card['hidden'] = ident in self.data['hidden']
            card['seats'] = [(a,sa,b,sb) for v in card['variants'] if v.get('seats')
                             for (a,sa),(b,sb) in [v['seats']]]
        return [c for c in merged.values() if include_hidden or not c['hidden']]
