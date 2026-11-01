"""Recognize the active tab, not every mode name visible on an entry page."""
import cv2
import numpy as np
from .modes import MINGDAO, RANKED_CHUHAN, PEAK_CHUHAN, PEAK_SHUANGLONG
from .region_geometry import is_standard_client

ENTRY_TEXT_16_9={False:((.63,.23,.81,.285),(.85,.23,.96,.285)),
                 True:((.34,.145,.46,.215),(.56,.145,.67,.215))}
ENTRY_COLOUR_16_9={False:((.65,.235,.80,.277),(.84,.235,.98,.277)),
                   True:((.31,.15,.50,.216),(.515,.15,.70,.216))}


def detect_entry(frame, header, read_region):
    # The adjacent help icon can be joined to the title at smaller resolutions.
    labels={w.text.strip().rstrip('?？').strip() for w in header if w.confidence>=.9}
    peak='巅峰竞技场' in labels
    if not peak and '竞技场' not in labels:return False,None
    regions=([(.305,.145,.505,.215),(.508,.145,.708,.215)] if peak else
             [(.655,.22,.826,.285),(.832,.22,.995,.285)])
    names=('楚汉争霸','双龙争鼎') if peak else ('楚汉争霸','明刀暗箭')
    modes=(PEAK_CHUHAN,PEAK_SHUANGLONG) if peak else (RANKED_CHUHAN,MINGDAO)
    h,w=frame.shape[:2];scores=[];texts=[]
    colour_regions=regions
    if is_standard_client(w,h):
        # Text bounds and active-tab colour are independent: padding a label
        # must not dilute its selection colour with the neighbouring paper.
        regions=ENTRY_TEXT_16_9[peak]
        colour_regions=ENTRY_COLOUR_16_9[peak]
    for index,(a,b,c,d) in enumerate(regions):
        crop=frame[int(h*b):int(h*d),int(w*a):int(w*c)]
        if not crop.size:return True,None
        texts.append(''.join(t.text for t in read_region(f'entry_tab_{peak}_{index}',crop) if t.confidence>=.85).replace('爭','争'))
        ca,cb,cc,cd=colour_regions[index]
        hsv=cv2.cvtColor(frame[int(h*cb):int(h*cd),int(w*ca):int(w*cc)],cv2.COLOR_BGR2HSV)
        hue=hsv[:,:,0]
        color=((hue>=70)&(hue<=105)) if peak else ((hue<22)|(hue>170))
        scores.append(float(np.mean(color&(hsv[:,:,1]>75)&(hsv[:,:,2]>80))))
    winner=int(scores[1]>scores[0])
    # The selected flame/cyan tab must be distinct; a fade/tooltip is unknown.
    if scores[winner]<.45 or scores[winner]-scores[1-winner]<.20:return True,None
    if not all(name in text for name,text in zip(names,texts)):return True,None
    return True,modes[winner]
