"""Recognize the active tab, not every mode name visible on an entry page."""
import cv2
import numpy as np
from .modes import MINGDAO, RANKED_CHUHAN, PEAK_CHUHAN, PEAK_SHUANGLONG


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
    for index,(a,b,c,d) in enumerate(regions):
        crop=frame[int(h*b):int(h*d),int(w*a):int(w*c)]
        if not crop.size:return True,None
        texts.append(''.join(t.text for t in read_region(f'entry_tab_{peak}_{index}',crop) if t.confidence>=.85))
        hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
        hue=hsv[:,:,0]
        color=((hue>=70)&(hue<=105)) if peak else ((hue<22)|(hue>170))
        scores.append(float(np.mean(color&(hsv[:,:,1]>75)&(hsv[:,:,2]>80))))
    winner=int(scores[1]>scores[0])
    # The selected flame/cyan tab must be distinct; a fade/tooltip is unknown.
    if scores[winner]<.45 or scores[winner]-scores[1-winner]<.20:return True,None
    if not all(name in text for name,text in zip(names,texts)):return True,None
    return True,modes[winner]
