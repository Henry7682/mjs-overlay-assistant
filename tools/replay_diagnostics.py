"""Read-only archive validation/OCR replay. Never controls applications."""
import argparse,json,tempfile,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mjs_assistant.archive import safe_extract,sha256

def inspect(path,ocr=False,scenes=False,logic=False):
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)/'bundle';safe_extract(path,root,max_bytes=30_000_000,max_files=5000)
        manifest=json.loads((root/'manifest.json').read_text('utf8'))
        if manifest.get('schema_version')!=1:raise ValueError('未知诊断格式')
        records=manifest['files'];allowed={'manifest.json'}
        for row in records:
            target=(root/row['name']).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():raise ValueError('文件缺失或路径无效')
            if target.stat().st_size!=row['bytes'] or sha256(target)!=row['sha256']:raise ValueError('诊断文件校验失败')
            allowed.add(row['name'])
        if {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}!=allowed:raise ValueError('存在未登记文件')
        result={'bundle_id':manifest['bundle_id'],'part':manifest['part'],'parts':manifest['parts'],'files':len(records),'validated':True}
        events=[]
        for p in (root/'logs').glob('events.jsonl*'):
            for line in p.read_text('utf8').splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
        result['events']=sorted(events,key=lambda r:r.get('monotonic',0))
        if logic:result['logic']=replay_logic(result['events'])
        if ocr or scenes:
            import cv2,numpy as np
            from PIL import Image
            from mjs_assistant.ocr import Ocr,Names
            from mjs_assistant.recognition import Recognizer
            engine=Ocr();result['ocr']=[]
            recognizer=Recognizer(engine,Names());metadata={}
            for incident in (root/'incidents').glob('*.json'):
                value=json.loads(incident.read_text('utf8'))
                for frame in value.get('frames',[]):metadata[value['id']+'/'+frame['file']]=frame.get('metadata',{})
            for p in (root/'images').rglob('*.png'):
                with Image.open(p) as header:
                    if header.width*header.height>15_000_000:continue
                img=cv2.imdecode(np.fromfile(p,np.uint8),1)
                if img is None or img.size>45_000_000:continue
                row={'file':p.relative_to(root).as_posix()}
                if ocr:row['words']=[{'text':w.text,'box':w.box,'confidence':w.confidence} for w in engine.read(img)]
                if scenes and p.name.endswith('-game.png'):
                    meta=metadata.get(p.parent.name+'/'+p.name,{})
                    scene,items,_=recognizer.analyze(img,'auto',{},meta.get('mode'))
                    row.update(scene=scene,mode_evidence=meta.get('mode'),names=[{'name':x.name,'slot':x.slot,'box':x.box} for x in items],
                        limitations='抽样画面，不重放实际帧间时序；跨分卷缺少元数据时模式可能未知')
                result['ocr'].append(row)
        return result

def replay_logic(events):
    from dataclasses import asdict
    from mjs_assistant.recommendations import ModeContext,SelectionSnapshot,filter_cards
    requests={};results=[]
    for event in events:
        try:
            key=(event.get('session_id'),event.get('request_id'))
            if event.get('event')=='query_start':
                raw=dict(event['config']['selection']);raw['context']=ModeContext(**raw['context'])
                for name in ('own_pool','ally_pool','enemies'):raw[name]=tuple(raw.get(name,[]))
                requests[key]=SelectionSnapshot(**raw)
            elif event.get('event') in ('query_result','query_batch'):
                snap=requests.get(key)
                results.append({'request_id':key[1],'missing_request':snap is None,
                    'filtered_cards':[asdict(x) for x in filter_cards(event.get('cards',[]),snap)] if snap else [],
                    'complete':event.get('complete',False)})
        except (KeyError,TypeError,ValueError) as error:results.append({'invalid_event':str(error)})
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archives',nargs='+',type=Path);p.add_argument('--ocr',action='store_true');p.add_argument('--scenes',action='store_true');p.add_argument('--logic',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
    results=[inspect(x,a.ocr,a.scenes) for x in a.archives]
    output={'archives':results}
    if a.logic:output['logic']=replay_logic(sorted([e for r in results for e in r['events']],key=lambda e:e.get('time','')))
    text=json.dumps(output,ensure_ascii=False,indent=2)
    if a.output:a.output.write_text(text,'utf8')
    else:print(text)
