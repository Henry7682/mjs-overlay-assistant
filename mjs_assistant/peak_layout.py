"""Locate the two-row peak draft inside the candidate panel, not chat/tooltips."""
import re
import cv2
import numpy as np


def draft_count(layout):
    match = re.fullmatch(r'draft(\d+)', layout or '')
    count = int(match[1]) if match else 0
    return count if 6 <= count <= 12 else 0


def row_starts(count):
    return tuple(.457 - .112 * (count - 1) / 2 + i * .112 for i in range(count))


def draft_regions(layout):
    count = draft_count(layout)
    if not count:
        return []
    return [(x, y, x + .019, end)
            for n, y, end in ((count // 2, .195, .273), ((count + 1) // 2, .444, .523))
            for x in row_starts(n)]


def detect_draft_layout(frame):
    """Read card silhouettes across the full two-row 6–12 candidate area.

    Paper gaps split portraits; validate widths, spacing AND centering. Missing
    middle portraits or tooltip occlusion therefore cannot silently shrink the
    roster. This is layout evidence only, never a source for hero names/mode.
    """
    h, w = frame.shape[:2]
    if h < 100 or w < 100:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    counts = []
    for y in (.23, .48):
        band = hsv[int(h*y):int(h*(y+.10))]
        occupied = (np.mean((band[:, :, 1] > 55) | (band[:, :, 2] < 150), axis=0) > .30).astype(np.uint8)
        occupied[:int(w*.14)] = 0
        occupied[int(w*.86):] = 0
        occupied = cv2.morphologyEx(occupied[None, :], cv2.MORPH_CLOSE,
                                   np.ones((1, max(1, int(w*.012))), np.uint8))[0]
        edges = np.diff(np.r_[0, occupied, 0].astype(int))
        blocks = [(a/w, b/w) for a, b in zip(np.where(edges == 1)[0], np.where(edges == -1)[0])
                  if (b-a)/w > .025]
        n = len(blocks)
        if not 3 <= n <= 6:
            return None
        if any(not (.065 <= b-a <= .103) or abs(a-(x+.002)) > .009
               for (a, b), x in zip(blocks, row_starts(n))):
            return None
        counts.append(n)
    if counts[1] not in (counts[0], counts[0]+1):
        return None
    return 'draft' + str(sum(counts))
