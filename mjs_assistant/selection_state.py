"""Conservative visual validity guard, independent of OCR name stability."""
from __future__ import annotations
import cv2
import numpy as np


class SelectionGuard:
    def __init__(self):self.clear()

    def clear(self):
        self.reference=None;self.signature=None;self.revision=0;self.reason='initial'

    @staticmethod
    def patches(frame,items,mode=None):
        h,w=frame.shape[:2];patches=[]
        for item in sorted(items,key=lambda d:d.slot):
            x,y,_,_=item.box
            # Central portrait/badge area relative to the observed nameplate.
            a,b=int(x+w*.018),int(y+h*.015)
            c,d=min(w,int(x+w*.075)),min(h,int(y+h*.125))
            if c<=a or d<=b:continue
            crop=frame[max(0,b):d,max(0,a):c]
            patches.append(cv2.resize(cv2.GaussianBlur(crop,(9,9),0),(16,24)).astype(np.float32))
        if mode in ('ranked_chuhan_2v2','peak_chuhan_2v2'):
            # The selected ally/self portrait can change without changing any
            # name in the candidate row. Exclude adjacent nicknames and avatars.
            for a,b in ((.08,.15),(.86,.93)):
                crop=frame[int(h*.80):int(h*.94),int(w*a):int(w*b)]
                if crop.size:patches.append(cv2.resize(cv2.GaussianBlur(crop,(9,9),0),(16,24)).astype(np.float32))
        return patches

    @staticmethod
    def ranked_image_patches(frame):
        """Watch nameplates/lock marks, not animated portrait art or OCR output."""
        h,w=frame.shape[:2]
        regions=[(x,.246,x+.019,.321) for x in (.092,.194,.296,.398,.522,.624,.726,.828)]
        # Selected-card name strips. A preview/lock can change without removing
        # a candidate; deliberately exclude the central animated portraits.
        regions +=[(.065,.79,.085,.86),(.84,.79,.86,.86)]
        patches=[]
        for a,b,c,d in regions:
            crop=frame[int(h*b):int(h*d),int(w*a):int(w*c)]
            gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
            ink=cv2.threshold(gray,170,255,cv2.THRESH_BINARY)[1]
            patches.append(cv2.resize(ink,(16,24)).astype(np.float32))
        # Green confirmation ribbon, excluding the top-right glowing card gem.
        for a,c in ((.06,.16),(.835,.94)):
            crop=frame[int(h*.845):int(h*.92),int(w*a):int(w*c)]
            hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
            green=cv2.inRange(hsv,(35,100,90),(90,255,255))
            patches.append(cv2.resize(green,(16,24)).astype(np.float32))
        return patches

    def update(self,frame,items,mode,scene,phase,image_only=False):
        image_only=image_only and mode=='ranked_chuhan_2v2'
        signature=(mode,scene,phase,None if image_only else tuple(sorted((d.slot,d.name,d.confirmed) for d in items)))
        patches=(self.ranked_image_patches(frame) if image_only else self.patches(frame,items,mode)) if scene=='selection' else []
        changed=signature!=self.signature or self.reference is None or len(patches)!=len(self.reference)
        reason='signature' if signature!=self.signature else 'patch_count'
        if not changed:
            # Compare to the last accepted state, not the preceding frame; slow
            # transitions must not evade invalidation by changing a little each time.
            deltas=[(i,round(float(np.abs(a-b).mean()),2)) for i,(a,b) in enumerate(zip(patches,self.reference))]
            hits=[(i,value) for i,value in deltas if value>10]
            changed=bool(hits);reason='visual '+str(hits)
        if changed:
            self.signature=signature;self.reference=patches;self.revision+=1;self.reason=reason
        return str(self.revision),changed
