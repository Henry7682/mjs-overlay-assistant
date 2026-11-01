"""Read-only screenshot replay. Private samples/annotations stay outside Git.

Usage: python tools/replay_regions.py annotations.json --output <private-dir>
Optional --baseline-ref compares immutable Git source, without a checkout or
launching the application. Image paths are relative to the annotation file.
"""
from __future__ import annotations
import argparse
import dataclasses
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import types

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mjs_assistant.ocr import Ocr,Names
from mjs_assistant.recognition import Recognizer,Stabilizer
from mjs_assistant import recognition
from mjs_assistant.region_geometry import pixel_box
from mjs_assistant.entry_detection import ENTRY_TEXT_16_9,ENTRY_COLOUR_16_9


def baseline_class(ref):
    sha=subprocess.check_output(['git','rev-parse','--verify',ref+'^{commit}'],cwd=ROOT,text=True).strip()
    package=types.ModuleType('_region_baseline');package.__path__=[str(ROOT/'mjs_assistant')]
    sys.modules[package.__name__]=package
    for name in ('peak_layout','identity_layout','entry_detection','recognition'):
        source=subprocess.check_output(['git','show',f'{sha}:mjs_assistant/{name}.py'],cwd=ROOT).decode('utf-8')
        mod=types.ModuleType(package.__name__+'.'+name)
        mod.__file__=str(ROOT/'mjs_assistant'/f'{name}.py');mod.__package__=package.__name__
        sys.modules[mod.__name__]=mod;exec(compile(source,mod.__file__,'exec'),mod.__dict__)
    return mod.Recognizer,sha


class Meter:
    def __init__(self,ocr):self.ocr=ocr;self.calls=0
    def read(self,image):self.calls+=1;return self.ocr.read(image)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('annotations',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline-ref');parser.add_argument('--rounds',type=int,default=5)
    parser.add_argument('--perturb',action='store_true')
    args=parser.parse_args()
    if not 1<=args.rounds<=20:parser.error('rounds must be 1..20')
    specs=json.loads(args.annotations.read_text(encoding='utf-8'))['samples']
    args.output.mkdir(parents=True,exist_ok=True)
    engine=Ocr();meter=Meter(engine);classes={'current':Recognizer};sha=None
    if args.baseline_ref:classes['baseline'],sha=baseline_class(args.baseline_ref)
    classes['coordinates_only']=Recognizer
    samples=[];records=[];checks=[]
    for spec in specs:
        path=args.annotations.parent/spec['image'];frame=cv2.imdecode(np.fromfile(path,np.uint8),1)
        if frame is None:raise ValueError(f'unreadable image: {path.name}')
        samples.append((spec,frame))
    # Warm model separately; cold-start import/loading is not OCR loop latency.
    meter.read(samples[0][1][:100,:400])
    margin=recognition.NAME_MARGIN
    for turn in range(args.rounds):
        variants=list(classes)
        if turn%2:variants.reverse()
        for spec,frame in samples:
            for variant in variants:
                recognition.NAME_MARGIN=(0,0) if variant=='coordinates_only' else margin
                r=classes[variant](meter,Names());stabilizer=Stabilizer()
                for phase in ('first','cached','changed'):
                    image=frame
                    if phase=='changed':
                        image=frame.copy()
                        boxes=getattr(r,'name_regions',())
                        if boxes:
                            a,b,_,_=pixel_box(boxes[0],frame.shape[1],frame.shape[0]);image[b,a]^=1
                        elif getattr(r,'_names_cache',None) and r._names_cache[0][3]:
                            _,a,b,*_=r._names_cache[0][3][0];image[b,a]^=1
                        else:image[0,0]^=1
                    count=meter.calls;start=time.perf_counter()
                    scene,items,_=r.analyze(image,mode_id=spec['mode'])
                    elapsed=time.perf_counter()-start
                    confirmed=stabilizer.update(scene,items,now=10+('first','cached','changed').index(phase))
                    records.append(dict(sample=spec['id'],variant=variant,round=turn,phase=phase,
                        seconds=elapsed,ocr_calls=meter.calls-count,heroes=sorted(d.name for d in items if d.name)))
                    if turn==0 and variant=='current' and phase=='cached':
                        actual={d.name for d in items if d.name};expected=set(spec['heroes'])
                        bounds=getattr(r,'name_regions',())
                        contained=all(any(a<=x1 and b<=y1 and c>=x2 and d>=y2
                            for a,b,c,d in [pixel_box(region,frame.shape[1],frame.shape[0]) for region in bounds])
                            for x1,y1,x2,y2 in spec.get('name_bounds',[]))
                        badges_correct=all(r.battle_badges.get(slot,{}).get('camp')==badge['camp']
                            and r.battle_badges.get(slot,{}).get('seat') in (None,badge['seat'])
                            for slot,badge in spec.get('badges',{}).items())
                        confirmed_names=sorted(d.name for d in confirmed if d.name and d.confirmed)
                        checks.append(dict(sample=spec['id'],correct=actual==expected,
                            scene=scene,scene_correct=scene==spec['scene'],entry=r.entry_mode,
                            entry_correct=r.entry_mode==spec.get('entry'),phase=r.phase,layout=r.layout,
                            bounds_contained=contained,badges_correct=badges_correct,
                            confirmation_correct=set(confirmed_names)==expected,confirmed=confirmed_names,
                            items=[dataclasses.asdict(d) for d in items],badges=r.battle_badges,seats=r.seats))
                        preview=frame.copy()
                        for index,region in enumerate(bounds):
                            a,b,c,d=pixel_box(region,frame.shape[1],frame.shape[0]);cv2.rectangle(preview,(a,b),(c,d),(0,200,255),2)
                            cv2.putText(preview,str(index),(a,max(15,b-4)),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,200,255),2)
                        if scene=='entry':
                            peak=spec['mode'].startswith('peak_')
                            for regions,colour in ((ENTRY_TEXT_16_9[peak],(0,200,255)),(ENTRY_COLOUR_16_9[peak],(255,200,0))):
                                for region in regions:
                                    a,b,c,d=pixel_box(region,frame.shape[1],frame.shape[0]);cv2.rectangle(preview,(a,b),(c,d),colour,2)
                        cv2.imencode('.png',preview)[1].tofile(args.output/(spec['id']+'-regions.png'))
                    if turn==0 and variant=='baseline' and phase=='cached':
                        preview=frame.copy()
                        cache=getattr(r,'_names_cache',None)
                        if cache:
                            for index,a,b,c,d,factor in cache[0][3]:
                                cv2.rectangle(preview,(a,b),(c,d),(0,0,255),2)
                        cv2.imencode('.png',preview)[1].tofile(args.output/(spec['id']+'-before.png'))
            print(f'round {turn+1}: {spec["id"]}',flush=True)
    recognition.NAME_MARGIN=margin
    perturb=[]
    if args.perturb:
        for spec,frame in samples:
            if not spec.get('name_bounds'):continue
            for dx,dy in ((-4,-6),(-4,6),(4,-6),(4,6)):
                shifted=frame.copy()
                for a,b,c,d in spec['name_bounds']:
                    # Shift only this labelled name patch, not the entire UI.
                    # Neighbouring background fills the vacated strips.
                    patch=frame[b-6:d+6,a-4:c+4].copy()
                    if patch.size:
                        shifted[b-6:d+6,a-4:c+4]=cv2.warpAffine(patch,np.float32([[1,0,dx],[0,1,dy]]),
                            (patch.shape[1],patch.shape[0]),borderMode=cv2.BORDER_REPLICATE)
                r=Recognizer(meter,Names());scene,items,_=r.analyze(shifted,mode_id=spec['mode'])
                actual={d.name for d in items if d.name}
                perturb.append(dict(sample=spec['id'],dx=dx,dy=dy,correct=actual==set(spec['heroes']),
                                    heroes=sorted(actual)))
    summaries=[]
    for spec,_ in samples:
        for variant in classes:
            for phase in ('first','cached','changed'):
                rows=[r for r in records if r['sample']==spec['id'] and r['variant']==variant and r['phase']==phase]
                times=[r['seconds'] for r in rows]
                summaries.append(dict(sample=spec['id'],variant=variant,phase=phase,
                    median=statistics.median(times),p95=float(np.percentile(times,95)),
                    max=max(times),median_ocr_calls=statistics.median(r['ocr_calls'] for r in rows)))
    result=dict(baseline=sha,rounds=args.rounds,checks=checks,perturb=perturb,summary=summaries,records=records,
                limitations=['changed is a one-pixel cache invalidation, not live animation',
                             'perturbations are synthetic, not real resolution validation'])
    (args.output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    failures=[c['sample'] for c in checks if not all(c[k] for k in ('correct','scene_correct','entry_correct','bounds_contained','badges_correct','confirmation_correct'))]
    print('failed checks:',failures,'failed perturbations:',sum(not p['correct'] for p in perturb))
    return 1 if failures or any(not p['correct'] for p in perturb) else 0


if __name__=='__main__':raise SystemExit(main())
