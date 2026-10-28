"""Incremental public-page result collection with conservative end evidence."""
from .guide_state import unique_cards


def result_scroll_target(bounds, footer, selected, results):
    """Use fresh visible result lines after the heading has scrolled away.

    UIA rectangles are x,y,width,height tuples; do not hit the sticky picker,
    selected chips, footer, or another application.
    """
    left,top,right,bottom=bounds
    def visible(rectangles):
        return [(x,y,x+w,y+h) for x,y,w,h in zip(*[iter(rectangles)]*4)
                if w>0 and h>0 and left<=x<x+w<=right and top<=y<y+h<=bottom]
    foot=visible(footer)
    if not foot:return None,()
    ceiling=min(r[1] for r in foot)-6
    chips=[r for r in visible(selected) if r[3]<ceiling]
    if not chips:return None,()
    floor=max(r[3] for r in chips)+6
    lines=[r for r in visible(results) if floor<=r[1] and r[3]<=ceiling]
    if not lines:return None,()
    # Anchor to the last visible guide line, rather than the offscreen heading.
    row=lines[-1]
    point=(int((left+right)/2),int((row[1]+row[3])/2))
    signature=tuple(tuple(round(v) for v in r) for r in lines)
    return point,signature


class GuidePages:
    def __init__(self):
        self.cards=(); self.selected=(); self.complete=False; self.no_result=False
        self.unchanged=0; self.limits=[]

    def add(self, parsed, at_end=False):
        selected=tuple(parsed.get('selected',()))
        if self.selected and set(selected)!=set(self.selected):
            raise ValueError('读取期间小程序候选发生变化，保留已读结果')
        self.selected=selected
        cards=unique_cards(self.cards+tuple(parsed.get('cards',())))
        self.unchanged=self.unchanged+1 if cards==self.cards else 0
        self.cards=cards
        self.no_result=bool(parsed.get('no_result')) and not self.cards
        # Repeated pages never prove the end. Only an explicit terminal state does.
        self.complete=self.no_result or bool(at_end)

    def payload(self):
        return dict(cards=list(self.cards),selected=list(self.selected),complete=self.complete,
                    no_result=self.no_result,limits=list(self.limits))
