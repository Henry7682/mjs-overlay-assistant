"""Cheap coordinate transforms; never resize a game frame or search for names.

Legacy centered candidate panels were measured in a 2559 x 1334 client.
Battle portraits use a different, client-proportional layout. Calibration is
already in client coordinates and must not pass through this conversion.
"""
from functools import lru_cache

REFERENCE_SIZE = (2559, 1334)
NAME_MARGIN = (6, 8)  # physical pixels at 1920 x 1080


def is_standard_client(width, height):
    return width > 0 and height > 0 and abs(height - width * 9 / 16) <= 2


def center_x(x, width, height):
    if not is_standard_client(width, height):
        return x  # retain legacy templates for offline regression/reference
    return .5 + (x - .5) * REFERENCE_SIZE[0] / REFERENCE_SIZE[1] * height / width


@lru_cache(maxsize=512)
def map_region(rect, width, height, mapping='client', margin=(0, 0)):
    """Return normalized client bounds. Only centered groups change anchors."""
    a, b, c, d = rect
    if mapping == 'center_height':
        a, c = center_x(a, width, height), center_x(c, width, height)
    elif mapping != 'client':
        raise ValueError('unknown region mapping')
    px, py = margin
    if is_standard_client(width, height):
        a -= px / 1920; c += px / 1920
        b -= py / 1080; d += py / 1080
    return max(0., a), max(0., b), min(1., c), min(1., d)


def map_regions(regions, width, height, mapping='client', margin=(0, 0)):
    return [map_region(tuple(r), width, height, mapping, margin) for r in regions]


def pixel_box(rect, width, height):
    a, b, c, d = rect
    return (max(0, int(a * width)), max(0, int(b * height)),
            min(width, int(c * width)), min(height, int(d * height)))
