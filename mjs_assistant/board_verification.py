"""Bounded, local re-reading of uncertain official table rows.

Never infer a missing value from its neighbours. Geometry only locates a crop;
both enlarged reads must actually contain the same rank, name and rate.
"""
from __future__ import annotations

import copy
import re
from statistics import median

import cv2

from .boards import assemble_rows, parse_words
from .ocr import Word

PARSER_VERSION = 'table-consensus-3'
MAX_RECHECK_ROWS = 40


def signature(row, side):
    return (row[side + '_rank'], row['name'], row.get('win_rate'))


def reread_row(image, ocr, names, side, rank, y, pitch, before_read):
    height, width = image.shape[:2]
    x1, x2 = (0, round(width * .49)) if side == 'win' else (round(width * .49), width)
    y1, y2 = max(0, round(y - pitch * .53)), min(height, round(y + pitch * .53))
    crop = image[y1:y2, x1:x2]
    if not crop.size:
        return None, []
    reads = []
    for scale in (2, 3, 4):
        before_read()
        expanded = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        pad = 12 * scale
        expanded = cv2.copyMakeBorder(expanded, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        words = [Word(w.text, w.confidence,
                      ((w.box[0]-pad)/scale+x1, (w.box[1]-pad)/scale+y1,
                       (w.box[2]-pad)/scale+x1, (w.box[3]-pad)/scale+y1))
                 for w in ocr.read(expanded)]
        parsed = parse_words(words, width, names, 'local-row-verification')
        candidates = [r for r in parsed['raw_' + side + '_rows'] if r[side + '_rank'] == rank]
        if len(candidates) == 1:
            reads.append(candidates[0])
        good = [r for r in reads if r['confidence'] >= .65 and r['name_confidence'] >= .75
                and (side == 'pick' or r.get('rate_confidence', 0) >= .95)]
        # Rank 1 is often ~0.8 even when crisp. Two scales plus complete
        # consecutive ranks can confirm it; confidence remains recorded, not forged.
        if len(good) >= 2 and len({signature(r, side) for r in good}) == 1:
            return max(good, key=lambda r: r['confidence']), reads
        if len({signature(r, side) for r in good}) > 1:
            break  # Conflicting readable values are never majority-voted away.
    return None, reads


def verify_chart(draft, image, ocr, names, before_read=lambda: None):
    """Return a draft with auditable row consensus; unresolved errors stay pending."""
    draft = copy.deepcopy(draft)
    tables = {s: draft.get('raw_' + s + '_rows', []) for s in ('win', 'pick')}
    # Unknown/changed layouts do not receive guessed rows or excessive OCR work.
    if any(len(rows) < 50 for rows in tables.values()):
        return draft
    if any('confidence' not in r for rows in tables.values() for r in rows):
        return draft  # Imported/reviewed legacy rows are not fresh OCR evidence.
    maps = {s: {r[s+'_rank']: r for r in rows} for s, rows in tables.items()}
    if any(len(maps[s]) != len(tables[s]) for s in maps):
        return draft
    n = max(max(rows) for rows in maps.values())
    if n > 999:
        return draft
    gaps = [(b['y']-a['y']) / (b[s+'_rank']-a[s+'_rank'])
            for s, rows in tables.items()
            for a, b in zip(sorted(rows, key=lambda r:r[s+'_rank']),
                            sorted(rows, key=lambda r:r[s+'_rank'])[1:])]
    pitch = median(gaps)
    if not 10 <= pitch <= 150:
        return draft
    common = maps['win'].keys() & maps['pick'].keys()
    offset = median(maps['pick'][r]['y']-maps['win'][r]['y'] for r in common)
    if abs(offset) > pitch * .3:
        return draft
    tasks = []
    for side, rows in maps.items():
        other = maps['pick' if side == 'win' else 'win']
        other_names = {r['name'] for r in other.values()}
        for rank in range(1, n+1):
            row = rows.get(rank)
            if row and (row.get('confidence', 0) < .85 or names.resolve(row['raw_name']) is None
                        or row['name'] not in other_names):
                tasks.append((side, rank, row['y']))
            elif row is None and rank in other:
                tasks.append((side, rank, other[rank]['y'] + (offset if side == 'pick' else -offset)))
    if len(tasks) > MAX_RECHECK_ROWS:
        draft['issues'].append('疑点行过多，保留旧榜单并等待完整核验')
        return draft
    verified, evidence, confirmed_unknown = set(), [], {}
    for side, rank, y in tasks:
        result, reads = reread_row(image, ocr, names, side, rank, y, pitch, before_read)
        accepted = result is not None
        evidence.append({'side': side, 'rank': rank, 'accepted': accepted,
                         'original': maps[side].get(rank), 'reads': reads})
        if not accepted:
            continue
        maps[side][rank] = result
        verified.add((side, rank))
        if (names.resolve(result['raw_name']) is None
                and re.fullmatch(r'[\u3400-\u9fff]{2,6}', result['raw_name'])
                and all(r['name_confidence'] >= .95 for r in reads)):
            confirmed_unknown.setdefault(result['name'], set()).add(side)
    # New names require two strong reads at BOTH independently ranked positions.
    # They are scoped to this board; the global OCR alias dictionary is unchanged.
    new_names = sorted(name for name, sides in confirmed_unknown.items() if sides == {'win', 'pick'})
    for side, rows in maps.items():
        draft['raw_' + side + '_rows'] = [rows[k] for k in sorted(rows)]
    draft = assemble_rows(draft, names, verified, new_names)
    draft['auto_verification'] = {'version': PARSER_VERSION, 'rows': evidence, 'new_names': new_names}
    draft['review_status'] = 'ocr-consensus'
    return draft
