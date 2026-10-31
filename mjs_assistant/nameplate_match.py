"""Limited glyph verification for reviewed ranked-selection rare characters.

This is not a text alias or a general hero classifier. A two-character OCR
reading, matching first character, whole-name image and both glyphs must agree.
Reference pixels contain only names; never match portraits, nicknames or prose.
"""
from functools import lru_cache

import cv2
import numpy as np

from .ocr import clean_name
from .storage import ASSETS

REFERENCES = {"左棻": "zuofen", "樊哙": "fankuai", "卫玠": "weijie"}


def feature(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (16, 40), interpolation=cv2.INTER_AREA).astype(np.float32)
    # Remove broad ribbon/background brightness; compare the actual strokes.
    return small - cv2.GaussianBlur(small, (0, 0), 1.4)


@lru_cache(maxsize=1)
def references():
    result = {}
    for name, stem in REFERENCES.items():
        result[name] = []
        for width in (2559, 1920, 1280):
            try:
                image = cv2.imdecode(np.fromfile(ASSETS / "nameplates" / f"{stem}-{width}.png", np.uint8), 1)
                if image is not None and image.size:
                    result[name].append(feature(image))
            except (OSError, cv2.error):
                pass  # A missing optional reference never stops normal OCR.
    return result


def similarity(first, second):
    if min(float(np.std(first)), float(np.std(second))) < 3:
        return 0.0  # Blank/flat regions are not name evidence.
    return float(cv2.matchTemplate(first, second, cv2.TM_CCOEFF_NORMED)[0, 0])


def verify_ranked_name(frame, box, raw, names):
    spelling = clean_name(raw)
    if len(spelling) != 2 or spelling[0] not in {n[0] for n in REFERENCES}:
        return None
    h, w = frame.shape[:2]
    a, _, c, _ = box
    pad = round(w * .002)
    top, bottom = round(h * 344 / 1334), round(h * 414 / 1334)
    left, right = a + pad, c - pad
    if not (0 <= left < right <= w and 0 <= top < bottom <= h):
        return None
    if min(bottom-top, right-left) < 8:
        return None
    # Screenshot resampling and slot rounding shift thin strokes by 1--3 px.
    # Search only that tiny translation; do not widen the name to nearby prose.
    dx, dy = max(1, round(w*.001)), max(1, round(h*.002))
    scores = {name: 0.0 for name in REFERENCES}
    templates = references()
    for y in range(-dy, dy+1):
        for x in range(-dx, dx+1):
            if not (0 <= left+x < right+x <= w and 0 <= top+y < bottom+y <= h):
                continue
            observed = feature(frame[top+y:bottom+y, left+x:right+x])
            for name, variants in templates.items():
                # Both glyphs must independently agree, not just the surname.
                for template in variants:
                    if min(similarity(observed[:20], template[:20]),
                           similarity(observed[20:], template[20:])) >= .88:
                        scores[name] = max(scores[name], similarity(observed, template))
    scores = sorted(((score, name) for name, score in scores.items()), reverse=True)
    score, name = scores[0]
    if (score >= .94 and score - scores[1][0] >= .12
            and name[0] == spelling[0] and name in names.names):
        return name, score
    return None
