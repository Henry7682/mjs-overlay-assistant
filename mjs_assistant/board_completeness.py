"""Conservative end-of-table evidence for the official dark two-panel layout.

Unsupported artwork stays pending. Blank image margins alone never prove an end.
"""
from statistics import median
import numpy as np


def inspect_end(image, tables):
    evidence = {'version': 1, 'complete': False, 'layout': 'dark-two-panel', 'sides': {}}
    if image is None or image.ndim != 3:
        return evidence
    height, width = image.shape[:2]
    for side, (left, right) in {'win': (.065, .46), 'pick': (.54, .94)}.items():
        rows = sorted(tables.get(side, []), key=lambda r: r[side+'_rank'])
        if len(rows) < 50:
            return evidence
        pitch = median(b['y']-a['y'] for a,b in zip(rows[-12:], rows[-11:]))
        if not 10 <= pitch <= 150:
            return evidence
        last = rows[-1]
        y = int(last['y'])
        if y < pitch or y + 3*pitch >= height:
            return evidence  # cropped image cannot prove the original table ended
        column = image[max(0,y-int(pitch)):min(height,y+int(pitch*3)),int(width*left):int(width*right)]
        colors = np.median(column, axis=1)
        base = np.median(colors[:int(pitch*1.4)], axis=0)
        if float(base.max()) > 85:
            return evidence
        distance = np.linalg.norm(colors.astype(float)-base, axis=1)
        boundary = None
        for offset in range(int(pitch*.65), int(pitch*1.8)):
            index = int(pitch)+offset
            span = distance[index:index+max(4,int(pitch*.6))]
            if len(span) and np.min(span) > 4.5:
                boundary = y+offset
                break
        evidence['sides'][side] = {'last_rank': last[side+'_rank'], 'last_y': last['y'],
                                   'pitch': pitch, 'boundary_y': boundary}
        if boundary is None:
            return evidence
    a,b = evidence['sides']['win'], evidence['sides']['pick']
    evidence['complete'] = (a['last_rank']==b['last_rank'] and
                            abs(a['boundary_y']-b['boundary_y']) < max(a['pitch'],b['pitch'])*.4)
    return evidence
