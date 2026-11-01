"""Observed Mingdao 3+6 candidate grid; never infer the game mode from it."""
import cv2
import numpy as np
import time
import re
from .region_geometry import center_x, is_standard_client


def six_lord_grid(frame):
    """Verify the known six-card row before skipping broad name localization.

    This only validates portrait geometry. Names still use the same OCR and
    two-frame confirmation. Missing/extra/shifted portraits keep the old fallback.
    """
    h,w=frame.shape[:2]
    if not is_standard_client(w,h):return False
    band=cv2.cvtColor(frame[int(h*.28):int(h*.40)],cv2.COLOR_BGR2HSV)
    occupied=(np.mean((band[:,:,1]>55)|(band[:,:,2]<150),axis=0)>.30).astype(np.uint8)
    occupied[:int(w*.24)]=0;occupied[int(w*.98):]=0
    occupied=cv2.morphologyEx(occupied[None,:],cv2.MORPH_CLOSE,
                            np.ones((1,max(1,int(w*.008))),np.uint8))[0]
    edges=np.diff(np.r_[0,occupied,0].astype(int))
    blocks=[(a/w,b/w) for a,b in zip(np.where(edges==1)[0],np.where(edges==-1)[0]) if (b-a)/w>.025]
    starts=(.286,.392,.500,.606,.714,.821)
    return len(blocks)==6 and all(.07<=b-a<=.12 and abs(a-center_x(x,w,h))<.016
                                  for (a,b),x in zip(blocks,starts))


class IdentityNameLocator:
    """Discover extra nameplates across the candidate panel, then reuse ROIs.

    Full-panel OCR is for localization only. The recognizer still independently
    reads each name strip and requires two frames before displaying a hero.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.key=None
        self.signature=None
        self.regions=[]
        self.scanned_at=0

    def locate(self, frame, key, ocr, names, now=None):
        now=time.monotonic() if now is None else now
        h,w=frame.shape[:2]
        panel=frame[int(h*.12):int(h*.68),int(w*.015):int(w*.95)]
        hsv=cv2.cvtColor(panel,cv2.COLOR_BGR2HSV)
        ink=((hsv[:,:,1]>55)|(hsv[:,:,2]<150)).astype(np.float32)
        signature=cv2.resize(ink,(64,32),interpolation=cv2.INTER_AREA)>.30
        # Portrait positions change with identity. Small animation/OCR changes
        # do not cause a second full-panel pass on every recognition frame.
        changed=self.signature is None or np.mean(signature!=self.signature)>.025
        if key==self.key and (not changed or now-self.scanned_at<3):
            return list(self.regions)
        regions=[]
        for left,right in ((.015,.52),(.48,.95)):
            x0,y0=int(w*left),int(h*.12)
            tile=frame[y0:int(h*.68),x0:int(w*right)]
            for word in ocr.read(tile):
                a,b,c,d=word.box
                # Horizontal skill prose / identity instructions are excluded.
                # Unknown spellings can locate a strip, but never identify a
                # hero: dictionary/confidence checks run on its independent OCR.
                if not re.fullmatch(r'[\u3400-\u9fff]{2,4}',word.text) or word.confidence<.65 or d-b<1.3*(c-a):
                    continue
                a,b,c,d=(a+x0)/w,(b+y0)/h,(c+x0)/w,(d+y0)/h
                if not (.006<=c-a<=.038 and .025<=d-b<=.17):
                    continue
                # Require a portrait beside the name, not an isolated word.
                patch=frame[max(0,int(b*h)):min(h,int((d+.06)*h)),int((c+.003)*w):min(w,int((c+.06)*w))]
                if not patch.size:continue
                colour=cv2.cvtColor(patch,cv2.COLOR_BGR2HSV)
                if np.mean((colour[:,:,1]>55)|(colour[:,:,2]<150))<.35:continue
                cy=(b+d)/2
                region=(max(.015,a-.004),max(.12,min(b-.008,cy-.057)),
                        min(.95,c+.004),min(.68,max(d+.008,cy+.057)))
                if any(abs((a+c)/2-(r[0]+r[2])/2)<.025 and abs(cy-(r[1]+r[3])/2)<.06 for r in regions):
                    continue
                regions.append(region)
        self.key=key;self.signature=signature;self.scanned_at=now
        self.regions=sorted(regions,key=lambda r:(round((r[1]+r[3])/2,1),r[0]))
        return list(self.regions)


def add_identity_regions(regions, extra):
    """Keep established strips, append uncovered positions without duplicates."""
    result=list(regions)
    for a,b,c,d in extra:
        x,y=(a+c)/2,(b+d)/2
        if not any(r[0]-.012<=x<=r[2]+.012 and r[1]-.025<=y<=r[3]+.025 for r in result):
            result.append((a,b,c,d))
    return result


def mingdao_nine_grid(frame):
    h, w = frame.shape[:2]
    if min(h, w) < 100:
        return False
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Validate both portrait bands, including their paper gaps and centering.
    # A missing middle card or an unrelated tooltip must not resize the roster.
    for y, count in ((.25, 3), (.53, 6)):
        band = hsv[int(h*y):int(h*(y+.08))]
        mask = (np.mean((band[:, :, 1] > 55) | (band[:, :, 2] < 150), axis=0) > .30).astype(np.uint8)
        mask[:int(w*.12)] = 0
        mask[int(w*.88):] = 0
        mask = cv2.morphologyEx(mask[None, :], cv2.MORPH_CLOSE,
                               np.ones((1, max(1, int(w*.012))), np.uint8))[0]
        edges = np.diff(np.r_[0, mask, 0].astype(int))
        blocks = [(a/w, b/w) for a, b in zip(np.where(edges == 1)[0], np.where(edges == -1)[0])
                  if (b-a)/w > .025]
        if len(blocks) != count:
            return False
        starts = [.443 - .112*(count-1)/2 + i*.112 for i in range(count)]
        scale=center_x(1,w,h)-center_x(0,w,h)
        if any(not .075*scale <= b-a <= .110*scale or abs(a-center_x(x,w,h)) > .009*scale
               for (a, b), x in zip(blocks, starts)):
            return False
    return True


def mingdao_nine_regions():
    return [(x, y, x+.028, y+.108)
            for count, y in ((3, .145), (6, .418))
            for x in (.443 - .112*(count-1)/2 + i*.112 for i in range(count))]
