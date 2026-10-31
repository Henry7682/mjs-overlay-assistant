from __future__ import annotations

from dataclasses import dataclass, replace
import re
import time

import cv2
import numpy as np

from .ocr import Names, Word
from .modes import MINGDAO, RANKED_CHUHAN, PEAK_CHUHAN, PEAK_SHUANGLONG
from .peak_layout import detect_draft_layout, draft_count, draft_regions
NAME_MIN_CONFIDENCE = .80
NAME_RECHECK_CONFIDENCE = .85

from .identity_layout import mingdao_nine_grid, mingdao_nine_regions, IdentityNameLocator, add_identity_regions


@dataclass
class Detection:
    name: str | None
    raw: str
    box: tuple[float, float, float, float]
    confidence: float
    slot: str = ''
    confirmed: bool = False
    method: str = 'ocr'


def profile_key(scene, width, height):
    return f'{scene}:{width / height:.2f}'


def selection_seconds(words):
    """Accept labelled seconds only; card numbers and progress bars are not clocks."""
    values=[]
    for word in words:
        match=re.fullmatch(r'(?:选将)?剩余(?:时间)?[：:\s]*(\d{1,3})\s*秒',word.text.strip())
        if match and word.confidence>=.9 and 0<=int(match[1])<=180:values.append(int(match[1]))
    return values[0] if len(set(values))==1 else None


def empty_selection_panel(words):
    """Only the observed face-down card's clear 将 is evidence of no choice."""
    return len(words)==1 and words[0].text.strip()=='将' and words[0].confidence>=.95


def puppet_dialog_visible(title, buttons):
    # The normal top-left selection title is outside these modal-only regions.
    return (any(w.text.strip()=='武将选择' and w.confidence>=.9 for w in title)
            and any(w.text.strip()=='取消' and w.confidence>=.9 for w in buttons))


def fourteen_card_grid(frame):
    """Four outer portraits exist in ban14 and are blank paper in draft9.

    Used only inside a confirmed peak selection scene, never as mode evidence.
    """
    h,w=frame.shape[:2]
    occupied=0
    for x in (.15,.82):
        for y in (.27,.53):
            tile=frame[int(h*y):int(h*(y+.07)),int(w*x):int(w*(x+.035))]
            if tile.size:
                hsv=cv2.cvtColor(tile,cv2.COLOR_BGR2HSV)
                if np.std(hsv[:,:,2])>15 and np.mean((hsv[:,:,1]>65)|(hsv[:,:,2]<120))>.35:occupied+=1
    return occupied>=3


def nine_card_grid(frame):
    h,w=frame.shape[:2];occupied=0
    for x,y in [(.32,.25),(.43,.25),(.55,.25),(.66,.25),(.27,.51),(.72,.51)]:
        tile=frame[int(h*y):int(h*(y+.05)),int(w*x):int(w*(x+.025))]
        if tile.size:
            hsv=cv2.cvtColor(tile,cv2.COLOR_BGR2HSV)
            if np.mean((hsv[:,:,1]>65)|(hsv[:,:,2]<120))>.35:occupied+=1
    return occupied>=5


def peak_phase(footer, grid14, order, grid9=False, draft_layout=None):
    if '禁止' in footer:return 'ban','ban14'
    if grid14:return 'transition','ban14'
    layout=draft_layout or ('draft9' if grid9 else None)
    # The bottom action prompt changes from 禁止 to 本局要使用/其他玩家选择.
    # Turn-order icons alone also exist in transitions and are not sufficient.
    if draft_count(layout) and ('本局要使用' in footer or '其他玩家选择' in footer):
        return 'selection',layout
    return 'unknown','unknown'


def decide_scene(words, detections, width, height):
    text = ' '.join(x.text for x in words)
    # Blocking popups and unrelated pages must not inherit the previous scene.
    if any(s in text for s in ('武将图鉴', '我的收藏', '战斗结算', '返回大厅', '选择模式')):
        return 'unknown'
    if any(s in text for s in ('武将选择', '请选择本局要使用的武将', '选择武将', '选择你的武将', '确认选将', '换将', '选将中')):
        return 'selection'
    if any(s in text for s in ('出牌阶段', '结束出牌', '托管', '取消托管', '身份场', '明刀暗箭')) and len(detections) >= 2:
        return 'battle'
    # Strong layout evidence: names distributed across at least three screen edges.
    edges = set()
    for d in detections:
        x = (d.box[0] + d.box[2]) / width / 2
        y = (d.box[1] + d.box[3]) / height / 2
        if x < .2: edges.add('left')
        if x > .8: edges.add('right')
        if y < .26: edges.add('top')
        if y > .75: edges.add('bottom')
    return 'battle' if len(detections) >= 4 and len(edges) >= 3 else 'unknown'


class Recognizer:
    def __init__(self, ocr, names: Names):
        self.ocr, self.names = ocr, names
        self._reads={};self._names_cache=None
        self.identity_locator=IdentityNameLocator()

    def read_region(self,key,image):
        previous=self._reads.get(key)
        if previous and np.array_equal(image,previous[1]):return previous[2]
        words=self.ocr.read(image);self._reads[key]=(time.monotonic(),image.copy(),words)
        return words

    def analyze(self, frame, scene_override='auto', profiles=None, mode_id=MINGDAO):
        self.layout='default';self.phase='unknown';self.seats=(None,None);self.self_locked=False;self.remaining=None
        self.entry_mode=None;self.in_entry=False;self.empty_panels=False;self.battle_badges={};self.locked_names=();self.round_end=False
        h, w = frame.shape[:2]
        # Scene title is separate from chat, tooltips and the card OCR canvas.
        header = self.read_region('header',frame[:int(h*.10), :int(w*.22)])
        text = ''.join(x.text for x in header)
        self.round_end=any(w.confidence>=.9 and w.text.strip() in ('战斗结算','对局结算','选择模式','排位赛') for w in header)
        from .entry_detection import detect_entry
        self.in_entry,self.entry_mode=detect_entry(frame,header,self.read_region)
        if self.in_entry:
            self.phase='entry';self.identity_locator.reset()
            return 'entry',[],header
        scene = scene_override
        if scene == 'auto':
            if '武将选择' in text or '选择武将' in text:
                scene = 'selection'
            elif re.search(r'第\d+轮', text):
                scene = 'battle'
            else:
                self.identity_locator.reset()
                return 'unknown', [], header
        self.layout='default';self.phase=scene
        if mode_id not in (MINGDAO,RANKED_CHUHAN,PEAK_CHUHAN,PEAK_SHUANGLONG):return 'unknown',[],header
        modal_title=self.read_region('puppet_title',frame[int(h*.20):int(h*.265),int(w*.42):int(w*.58)])
        modal_buttons=(self.read_region('puppet_cancel',frame[int(h*.68):int(h*.76),int(w*.55):int(w*.68)])
                       if any(t.text.strip()=='武将选择' and t.confidence>=.9 for t in modal_title) else [])
        puppet=puppet_dialog_visible(modal_title,modal_buttons)
        if puppet:self.layout='puppet3';self.phase='puppet'
        if not puppet and mode_id==MINGDAO and scene=='selection' and mingdao_nine_grid(frame):
            self.layout='identity3_6'
        if not puppet and mode_id in (MINGDAO,PEAK_SHUANGLONG) and scene=='selection':
            role=self.read_region('shuanglong_role',frame[int(h*.83):int(h*.91),int(w*.44):int(w*.64)])
            if any('潜龙' in word.text and word.confidence>=.9 for word in role):
                self.layout='identity_two_rows_qianlong'
            else:
                lord=self.read_region('identity_lord',frame[int(h*.58):int(h*.65),int(w*.035):int(w*.18)])
                if mode_id==PEAK_SHUANGLONG or any('主公已选' in word.text and word.confidence>=.9 for word in lord):
                    self.layout='identity6_lord'
        if not puppet and mode_id==PEAK_CHUHAN and scene=='selection':
            footer=self.read_region('footer',frame[int(h*.65):int(h*.95),int(w*.30):int(w*.80)])
            footer_text=''.join(t.text for t in footer)
            self.remaining=selection_seconds(footer)
            order=self.read_region('peak_order',frame[int(h*.07):int(h*.15),int(w*.36):int(w*.64)])
            self.phase,self.layout=peak_phase(footer_text,fourteen_card_grid(frame),''.join(t.text for t in order),draft_layout=detect_draft_layout(frame))
            if self.layout=='unknown':return 'selection',[],header
        if not puppet and scene=='battle' and mode_id in (RANKED_CHUHAN,PEAK_CHUHAN):
            self.battle_badges=self.read_battle_badges(frame)
        if not puppet and mode_id in (RANKED_CHUHAN,PEAK_CHUHAN) and scene=='selection':
            # Read only the seat/control band, never infer sides from portrait count.
            a,b,c,d=(.29,.50,.71,.61) if mode_id==RANKED_CHUHAN else (.29,.66,.71,.74)
            controls=self.read_region('controls',frame[int(h*b):int(h*d),int(w*a):int(w*c)])
            self.remaining=self.remaining if self.remaining is not None else selection_seconds(controls)
            seats=[None,None];numbers={'一':1,'二':2,'三':3,'四':4,'1':1,'2':2,'3':3,'4':4}
            for word in controls:
                match=re.fullmatch(r'([一二三四1-4])号位',word.text.strip())
                if match and word.confidence>=.9:
                    side=0 if (word.box[0]+word.box[2])/2 < w*(c-a)/2 else 1
                    seats[side]=numbers[match[1]]
            self.seats=(seats[1],seats[0])  # Self is on the right in verified Steam layouts.
            lock_words=self.read_region('lock',frame[int(h*.82):,int(w*.84):])
            self.self_locked=any('已确认' in word.text or '已锁定' in word.text for word in lock_words)
            panels=[self.read_region('selected_'+side,frame[int(h*.80):int(h*.94),int(w*a):int(w*b)])
                    for side,a,b in [('ally',.08,.15),('own',.86,.93)]]
            self.empty_panels=all(empty_selection_panel(words) for words in panels)
        profile = (profiles or {}).get(profile_key(scene,w,h)+':'+self.layout,
                                     {} if puppet or self.layout.startswith('identity') else (profiles or {}).get(profile_key(scene,w,h), {}))
        regions = profile.get('regions', [])
        calibrated = bool(regions)
        if not regions:
            # Standard Steam eight-player layout, normalized to the client area.
            # Only nameplates are searched; arbitrary in-game prose cannot match.
            if puppet:
                regions=[(x,.384,x+.025,.478) for x in (.313,.450,.588)]
            elif scene=='selection' and mode_id==MINGDAO and self.layout=='identity3_6':
                regions=mingdao_nine_regions()
            elif scene=='selection' and mode_id==RANKED_CHUHAN:
                regions=[(x,.246,x+.019,.321) for x in (.092,.194,.296,.398,.522,.624,.726,.828)]
            elif scene=='selection' and mode_id==PEAK_CHUHAN:
                if self.layout=='ban14':
                    regions=[(x,y,x+.019,y+.082) for y in (.221,.477) for x in (.121,.233,.345,.457,.569,.681,.793)]
                else:
                    regions=draft_regions(self.layout)
            elif scene=='selection' and mode_id in (MINGDAO,PEAK_SHUANGLONG) and self.layout in ('identity_two_rows_qianlong','identity6_lord'):
                if self.layout=='identity_two_rows_qianlong':
                    # Live samples show both 5+1 and 1+5 arrangements. Search
                    # the observed nameplate columns on both rows; blank slots
                    # produce no hero instead of guessing the row from the role.
                    regions=[(x,y,x+.024,end) for y,end in ((.166,.260),(.431,.528))
                             for x in (.225,.338,.451,.564,.677)]
                else:
                    regions=[(.028,.275,.059,.361)]
                    regions += [(x,.255,x+.022,.365) for x in (.286,.392,.500,.606,.714,.821)]
            elif scene=='battle' and mode_id in (RANKED_CHUHAN,PEAK_CHUHAN):
                regions=[(x,.088,x+.034,.178) for x in (.294,.580)]
                regions += [(.009,.239,.040,.329),(.870,.239,.901,.329),(.870,.714,.901,.820)]
            elif scene == 'selection':
                regions = [(x,y,x+.028,y+.108) for y in (.145,.418) for x in (.331,.443,.556)]
            else:
                regions = [(x,.088,x+.034,.178) for x in (.151,.294,.437,.580,.723)]
                regions += [(.009,.225,.040,.339),(.870,.239,.901,.329),(.870,.694,.901,.820)]
        if not calibrated and not puppet and scene=='selection' and mode_id in (MINGDAO,PEAK_SHUANGLONG):
            extra=self.identity_locator.locate(frame,(mode_id,self.layout,w,h),self.ocr,self.names)
            regions=add_identity_regions(regions,extra)
        else:
            self.identity_locator.reset()
        if not calibrated and not puppet and scene=='battle':
            regions=[(max(0,a-.002),max(0,b-.008),min(1,c+.002),min(1,d+.010)) for a,b,c,d in regions]
        # Pack full-resolution narrow nameplates into one detector invocation.
        # This preserves vertical glyphs while avoiding a full-screen CNN pass.
        tiles=[];locations=[];maxw=0;maxh=0
        for i,region in enumerate(regions):
            a,b,c,d=[int(v*(w if j%2==0 else h)) for j,v in enumerate(region)]
            a,b,c,d=max(0,a),max(0,b),min(w,c),min(h,d)
            if c<=a or d<=b:continue
            crop=frame[b:d,a:c]
            factor=150/max(d-b,1)
            tile=cv2.resize(crop,None,fx=factor,fy=factor)
            tiles.append(tile);locations.append((i,a,b,c,d,factor))
            maxw=max(maxw,tile.shape[1]);maxh=max(maxh,tile.shape[0])
        if not tiles:return scene,[],header
        cols=min(4,len(tiles));cw=maxw+32;ch=maxh+32
        canvas=np.zeros((((len(tiles)+cols-1)//cols)*ch,cols*cw,3),np.uint8)
        for j,tile in enumerate(tiles):
            x=j%cols*cw+16;y=j//cols*ch+16
            canvas[y:y+tile.shape[0],x:x+tile.shape[1]]=tile
        cache=self._names_cache;cache_key=(mode_id,scene,self.layout,tuple(locations),tuple(sorted(self.names.names)))
        if cache and cache[0]==cache_key and np.array_equal(cache[2],canvas):
            if draft_count(self.layout) and sum(bool(d.name) for d in cache[4])<draft_count(self.layout):
                self.locked_names=self.read_locked_names(frame)
            return cache[3],list(cache[4]),header
        words=self.ocr.read(canvas);detected=[]
        for j,(slot,a,b,c,d,factor) in enumerate(locations):
            ox=j%cols*cw+16;oy=j//cols*ch+16
            texts=[t for t in words if ox <= (t.box[0]+t.box[2])/2 < ox+tiles[j].shape[1]
                   and oy <= (t.box[1]+t.box[3])/2 < oy+tiles[j].shape[0]]
            texts.sort(key=lambda t:t.box[1])
            # A name may be detected as individual vertical characters.
            raw=''.join(t.text for t in texts)
            name=self.names.resolve(raw)
            conf=min((t.confidence for t in texts),default=0)
            method='ocr'
            if not name:
                exact=[t for t in texts if self.names.resolve(t.text)]
                if len(exact)==1:
                    raw=exact[0].text;name=self.names.resolve(raw);conf=exact[0].confidence
            if not texts:continue
            if (not name or conf<NAME_MIN_CONFIDENCE) and not calibrated and not puppet and scene=='selection' and mode_id==RANKED_CHUHAN:
                from .nameplate_match import verify_ranked_name
                match=verify_ranked_name(frame,(a,b,c,d),raw,self.names)
                if match:
                    name,conf=match;method='glyph_verified'
            if (not name or conf<NAME_MIN_CONFIDENCE) and not calibrated and scene=='selection' and mode_id in (MINGDAO,PEAK_SHUANGLONG) and not puppet:
                # Preserve the reliable narrow read; expand missing strokes only
                # on failed identity-mode nameplates, never the whole screen.
                crop=frame[max(0,b-round(h*.012)):min(h,d+round(h*.010)),
                           max(0,a-round(w*.003)):min(w,c+round(w*.004))]
                checked=self.read_region('identity_full_'+str(slot),cv2.copyMakeBorder(cv2.resize(crop,None,fx=3,fy=3),24,24,24,24,cv2.BORDER_CONSTANT))
                exact=[t for t in checked if self.names.resolve(t.text) and t.confidence>=NAME_RECHECK_CONFIDENCE]
                if len(exact)==1 and len(checked)==1:
                    raw=exact[0].text;name=self.names.resolve(raw);conf=exact[0].confidence
            if (not name or conf<NAME_MIN_CONFIDENCE) and not calibrated and draft_count(self.layout):
                # Expand only failed name strips: widening every valid two-glyph
                # read regressed 侯嬴. Full first strokes repair 鲁仲连/秦舞阳.
                crop=frame[max(0,b-round(h*.012)):min(h,d+round(h*.006)),a:c]
                checked=self.read_region('draft_full_'+str(slot),cv2.copyMakeBorder(cv2.resize(crop,None,fx=3,fy=3),24,24,24,24,cv2.BORDER_CONSTANT))
                checked.sort(key=lambda t:t.box[1])
                spelling=''.join(t.text for t in checked);resolved=self.names.resolve(spelling)
                score=min((t.confidence for t in checked),default=0)
                if resolved and score>=NAME_RECHECK_CONFIDENCE:raw,name,conf=spelling,resolved,score
            if (not name or conf<NAME_MIN_CONFIDENCE) and not calibrated and not puppet and scene=='battle' :
                # Whole-name read at native detail: the packed canvas can lose
                # 金日磾's last glyph. Accept only an exact dictionary result.
                crop=frame[max(0,b-round(h*.006)):min(h,d+round(h*.006)),a:c]
                checked=self.read_region('battle_full_'+str(slot),cv2.copyMakeBorder(cv2.resize(crop,None,fx=3,fy=3),24,24,24,24,cv2.BORDER_CONSTANT))
                checked.sort(key=lambda t:t.box[1])
                spelling=''.join(t.text for t in checked);resolved=self.names.resolve(spelling)
                score=min((t.confidence for t in checked),default=0)
                if resolved and score>=NAME_RECHECK_CONFIDENCE:raw,name,conf=spelling,resolved,score
            if (not name or conf<NAME_MIN_CONFIDENCE) and not calibrated and (self.layout=='ban14' or draft_count(self.layout)):
                # Retry observed glyphs with their full lower strokes and contrast;
                # no near-name alias (e.g. 樊哈/晋仲连/侯赢) is added to the dictionary.
                crop=frame[max(0,b-round(h*.006)):min(h,d+round(h*.014)),max(0,a-round(w*.003)):min(w,c+round(w*.004))]
                gray=cv2.cvtColor(cv2.resize(crop,None,fx=3,fy=3),cv2.COLOR_BGR2GRAY)
                for variant in (cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR),cv2.cvtColor(cv2.threshold(gray,170,255,cv2.THRESH_BINARY)[1],cv2.COLOR_GRAY2BGR)):
                    checked=self.ocr.read(cv2.copyMakeBorder(variant,24,24,24,24,cv2.BORDER_CONSTANT))
                    checked.sort(key=lambda t:t.box[1])
                    spelling=''.join(t.text for t in checked);resolved=self.names.resolve(spelling)
                    score=min((t.confidence for t in checked),default=0)
                    if resolved and score>=NAME_RECHECK_CONFIDENCE:
                        raw,name,conf=spelling,resolved,score;break
                if not name:
                    base=cv2.resize(frame[b:d,a:c],None,fx=4,fy=4)
                    ink=cv2.cvtColor(cv2.threshold(cv2.cvtColor(base,cv2.COLOR_BGR2GRAY),190,255,cv2.THRESH_BINARY)[1],cv2.COLOR_GRAY2BGR)
                    first=self.ocr.read(cv2.copyMakeBorder(cv2.resize(frame[b:d,a:c],None,fx=3,fy=3),24,24,24,24,cv2.BORDER_CONSTANT))
                    second=self.ocr.read(cv2.copyMakeBorder(ink,24,24,24,24,cv2.BORDER_CONSTANT))
                    # Independent original + threshold reads must agree exactly;
                    # one must meet the normal confirmation threshold.
                    if len(first)==len(second)==1 and first[0].text==second[0].text and first[0].confidence>=.7 and second[0].confidence>=NAME_MIN_CONFIDENCE:
                        resolved=self.names.resolve(second[0].text)
                        if resolved:raw,name,conf=second[0].text,resolved,second[0].confidence
            if (not name or conf<NAME_MIN_CONFIDENCE) and not calibrated and not puppet and scene=='selection' and mode_id==RANKED_CHUHAN:
                # Four-glyph names start higher. Retry the actual missing strokes
                # rather than aliasing 十阳公主 to 平阳公主 or changing every ROI.
                top=max(0,b-round(h*.012))
                expanded=cv2.resize(frame[top:d,a:c],None,fx=3,fy=3)
                checked=self.ocr.read(cv2.copyMakeBorder(expanded,24,24,24,24,cv2.BORDER_CONSTANT))
                checked.sort(key=lambda t:t.box[1])
                spelling=''.join(t.text for t in checked)
                resolved=self.names.resolve(spelling)
                score=min((t.confidence for t in checked),default=0)
                if resolved and score>=NAME_RECHECK_CONFIDENCE:raw,name,conf=spelling,resolved,score
            if name and .60<=conf<NAME_MIN_CONFIDENCE:
                gray=cv2.cvtColor(frame[b:d,a:c],cv2.COLOR_BGR2GRAY)
                gray=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
                checked=self.ocr.read(cv2.copyMakeBorder(cv2.resize(gray,None,fx=3,fy=3),24,24,24,24,cv2.BORDER_CONSTANT))
                # Only promote the exact original spelling on an independent
                # contrast/scale read. Unknown or conflicting names stay pending.
                if len(checked)==1 and checked[0].text==raw and checked[0].confidence>=NAME_MIN_CONFIDENCE:
                    conf=checked[0].confidence
            # Low scores and unknown glyphs remain visible as review candidates,
            # never silently fuzzy-matched to a dictionary name.
            if (not name or conf < NAME_MIN_CONFIDENCE) and texts:
                retry=self.ocr.read(cv2.copyMakeBorder(cv2.resize(tiles[j],None,fx=2,fy=2),24,24,24,24,cv2.BORDER_CONSTANT))
                retry.sort(key=lambda t:t.box[1])
                retry_raw=''.join(t.text for t in retry)
                retry_name=self.names.resolve(retry_raw)
                retry_conf=min((t.confidence for t in retry),default=0)
                if retry_name and retry_conf >= NAME_RECHECK_CONFIDENCE:
                    raw,name,conf=retry_raw,retry_name,retry_conf
            if ((name and conf<NAME_MIN_CONFIDENCE and len(name)==2) or ((self.layout=='ban14' or draft_count(self.layout)) and not name and len(raw)==2)) and len(texts)==1:
                # Cross-check an exact two-character name by laying the observed
                # vertical glyphs horizontally. Never replace an unknown spelling.
                t=texts[0];tx1,ty1,tx2,ty2=t.box
                x1,y1=max(0,int(tx1-ox)),max(0,int(ty1-oy))
                x2,y2=min(tiles[j].shape[1],int(tx2-ox)+1),min(tiles[j].shape[0],int(ty2-oy)+1)
                glyphs=tiles[j][y1:y2,x1:x2];middle=glyphs.shape[0]//2
                if middle>3 and glyphs.shape[1]>3:
                    strip=np.hstack([cv2.resize(g,(64,64)) for g in (glyphs[:middle],glyphs[middle:])])
                    checked=self.ocr.read(cv2.copyMakeBorder(strip,16,16,16,16,cv2.BORDER_CONSTANT))
                    if len(checked)==1 and checked[0].confidence>=NAME_RECHECK_CONFIDENCE and self.names.resolve(checked[0].text):
                        if checked[0].text==raw or ((self.layout=='ban14' or draft_count(self.layout)) and not name):
                            raw=checked[0].text;name=self.names.resolve(raw);conf=checked[0].confidence
            if name and conf<NAME_MIN_CONFIDENCE:
                # A known exact spelling (including explicit traditional-form
                # aliases) needs independent, high-confidence confirmation.
                # Preserve the nameplate's lower strokes and suppress its art
                # background; never use this pass to guess an unknown name.
                pad=max(1,round(w*.0035));bottom=max(1,int(h*.01))
                crop=frame[b:min(h,d+bottom),max(0,a-pad):min(w,c+pad+1)]
                gray=cv2.cvtColor(cv2.resize(crop,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC),cv2.COLOR_BGR2GRAY)
                ink=cv2.cvtColor(cv2.threshold(gray,180,255,cv2.THRESH_BINARY)[1],cv2.COLOR_GRAY2BGR)
                checked=self.ocr.read(cv2.copyMakeBorder(ink,24,24,24,24,cv2.BORDER_CONSTANT))
                if len(checked)==1 and self.names.resolve(checked[0].text)==name and checked[0].confidence>=NAME_RECHECK_CONFIDENCE:
                    raw=checked[0].text;conf=checked[0].confidence
            if not name or conf < NAME_MIN_CONFIDENCE:
                from .rare_names import candidate, confirm
                if candidate(raw,self.names):
                    # Only this short reviewed list gets a lower, double-read
                    # threshold. No fixed screen coordinate or portrait match.
                    crop=cv2.resize(frame[b:d,a:c],None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC)
                    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
                    checked=self.read_region('rare_gray_'+str(slot),cv2.copyMakeBorder(
                        cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR),24,24,24,24,cv2.BORDER_CONSTANT))
                    match=confirm(raw,conf,checked,self.names)
                    if match:
                        name,conf=match;method='rare_consensus'
            if conf < NAME_MIN_CONFIDENCE and method!='rare_consensus':name=None
            detected.append(Detection(name,raw,(a,b,c,d),conf,f'puppet{slot}' if puppet else f'roi{slot}',method=method))
        if not puppet and not calibrated and scene_override=='auto' and scene=='battle' and not any(d.name for d in detected):
            return 'unknown',[],header
        self._names_cache=(cache_key,time.monotonic(),canvas.copy(),scene,list(detected))
        if draft_count(self.layout) and sum(bool(d.name) for d in detected)<draft_count(self.layout):
            self.locked_names=self.read_locked_names(frame)
        return scene,detected,header

    def read_locked_names(self,frame):
        h,w=frame.shape[:2];found=[];signature=[]
        for side,x in (('own',.850),('ally',.073)):
            lock=self.read_region('lock_panel_'+side,frame[int(h*.85):int(h*.92),int(w*x):int(w*(x+.10))])
            if not any('已确认' in t.text and t.confidence>=.9 for t in lock):continue
            crop=frame[int(h*.79):int(h*.86),int(w*x):int(w*(x+.02))]
            words=self.read_region('lock_name_'+side,cv2.copyMakeBorder(cv2.resize(crop,None,fx=3,fy=3),24,24,24,24,cv2.BORDER_CONSTANT))
            raw=''.join(t.text for t in sorted(words,key=lambda t:t.box[1]))
            name=self.names.resolve(raw)
            if name and words and min(t.confidence for t in words)>=NAME_MIN_CONFIDENCE:
                signature.append((side,name))
                if (side,name) in getattr(self,'_locked_previous',()):found.append(name)
        self._locked_previous=tuple(signature)
        return tuple(found)

    def read_battle_badges(self,frame):
        h,w=frame.shape[:2];result={}
        # Verified Steam main-portrait badge and seat regions; no skill text.
        positions=[(.389,.051,.348,.334),(.675,.051,.634,.334),
                   (.103,.202,.061,.484),(.964,.202,.923,.484),(.964,.678,.923,.963)]
        for index,(x,y,sx,sy) in enumerate(positions):
            crops=[frame[int(h*(y+a)):int(h*(y+b)),int(w*x):int(w*(x+.017))] for a,b in ((0,.019),(.019,.039))]
            strip=np.hstack([cv2.resize(crop,(90,90)) for crop in crops])
            words=self.read_region('camp'+str(index),cv2.copyMakeBorder(strip,24,24,24,24,cv2.BORDER_CONSTANT))
            text=''.join(t.text for t in sorted(words,key=lambda t:t.box[0]) if t.confidence>=.90)
            camp=text if text in ('楚军','汉军') else None
            seat=None
            if camp:
                tile=frame[int(h*sy):min(h,int(h*(sy+.032))),int(w*sx):int(w*(sx+.020))]
                words=self.read_region('seat'+str(index),cv2.resize(tile,None,fx=3,fy=3))
                values={'一':1,'二':2,'三':3,'四':4,'1':1,'2':2,'3':3,'4':4}
                known={values[t.text] for t in words if t.text in values and t.confidence>=.9}
                if len(known)==1:seat=known.pop()
            result['roi'+str(index)]={'camp':camp,'seat':seat}
        return result


class Stabilizer:
    def __init__(self):
        self.previous = {}
        self.scene = None
        self.last_time = 0
        self.overrides = {}

    def clear(self):
        self.previous.clear()
        self.overrides.clear()
        self.scene = None

    def update(self, scene, detections, now=None, max_gap=3):
        now = time.monotonic() if now is None else now
        if scene != self.scene or now-self.last_time > max_gap:
            self.clear()
        self.scene, self.last_time = scene, now
        current, result = {}, []
        for d in detections:
            # Alternate exact/traditional OCR spellings of the same dictionary
            # name must not reset a confirmed hero on every frame. Unknown text
            # still has its own key; replacement names require two fresh hits.
            key=(d.slot,d.name or d.raw)
            hits=self.previous.get(key,0)+1
            current[key]=hits
            name=self.overrides.get((d.slot,d.raw),d.name)
            result.append(replace(d,name=name,confirmed=bool(name) and hits>=2))
        # Overrides are valid only while the exact observed slot/text remains present.
        active={(d.slot,d.raw) for d in detections}
        self.overrides={k:v for k,v in self.overrides.items() if k in active}
        self.previous=current
        return result


def place_labels(items, width, height, label_width=290, label_height=44, offset=(0,0), anchors=None):
    occupied=[]
    result=[]
    for item in items:
        x1,y1,x2,y2=item.box
        anchor=(anchors or {}).get(item.slot)
        x=max(4,min(width-label_width-4,anchor[0] if anchor else x1+offset[0]))
        candidates=[y2+6+offset[1], y1-label_height-6+offset[1]]
        if anchor:candidates.insert(0,anchor[1])
        candidates.extend(range(45,max(46,int(height-label_height)),label_height+4))
        for y in candidates:
            y=max(34,min(height-label_height-4,y))
            rect=(x,y,x+label_width,y+label_height)
            if all(rect[2]<=r[0] or rect[0]>=r[2] or rect[3]<=r[1] or rect[1]>=r[3] for r in occupied):
                occupied.append(rect);result.append((item,rect));break
    return result
