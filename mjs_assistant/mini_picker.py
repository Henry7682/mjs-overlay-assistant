"""Conservative parsing of the public picker, separate from selected chips/guides."""
import re


def roster_text(text):
    # The public page places the picker after its fixed footer/canvas, even when
    # the selected chips and recommendation cards repeat the same hero names.
    footer=text.find('相册')
    start=text.find('绘图区域',footer) if footer>=0 else -1
    if start<0:return ''
    return text[start+len('绘图区域'):].split('绘图区域',1)[0]


def roster_names(text):
    return tuple(dict.fromkeys(re.findall(
        r'([\u3400-\u9fff]{2,6})\s+(?:\d+(?:\.\d+)?%|-)(?=\s|$)',roster_text(text))))


def catalogue_ready(text):
    # Do not infer unsupported heroes from an empty, loading or filtered page.
    tail=text[text.find('相册'):] if '相册' in text else ''
    return tail.count('绘图区域')>=2 and len(roster_names(text))>=50


def portrait_point(box,bounds,footer_y):
    if len(box)!=4:return None
    x,y,w,h=box
    if w<=0 or h<=0:return None
    point=(int(x+w/2),int(y-h*2))
    # Keep the portrait and its name above the fixed footer, not merely inside
    # the native window. Reject clipping rather than clicking the footer.
    if not(bounds[0]<x and x+w<bounds[2] and bounds[1]+h*3<point[1]
           and y+h<min(bounds[3],footer_y)):return None
    return point
