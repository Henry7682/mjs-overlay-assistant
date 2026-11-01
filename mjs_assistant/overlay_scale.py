"""Window-relative UI sizing, independent of Windows display scaling.

Keep the former appearance at the development reference: 2560x1440, 150%.
All sizes below are design-space Qt pixels, not screenshot pixels.
"""
REFERENCE_WIDTH = 2560 / 1.5
REFERENCE_HEIGHT = 1440 / 1.5


def logical_scale(width, height):
    return max(.001, min(width / REFERENCE_WIDTH, height / REFERENCE_HEIGHT))


def panel_metrics(rect, dpi, compact=False):
    """Return Qt scale and physical window size; convert DPI exactly once."""
    _, _, w, h = rect
    physical_scale = logical_scale(w, h)
    scale = physical_scale / dpi
    bw, bh = (76, 42) if compact else (430, 430)
    return scale, (max(1, min(w, round(bw * physical_scale))),
                   max(1, min(h, round(bh * physical_scale))))
