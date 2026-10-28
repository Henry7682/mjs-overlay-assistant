"""Read-only archive validation/OCR replay. Never controls applications."""
import argparse,json,tempfile,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mjs_assistant.archive import safe_extract,sha256

def inspect(path,ocr=False):
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
        if ocr:
            import cv2,numpy as np
            from mjs_assistant.ocr import Ocr
            engine=Ocr();result['ocr']=[]
            for p in (root/'images').rglob('*.png'):
                img=cv2.imdecode(np.fromfile(p,np.uint8),1)
                if img is None or img.size>45_000_000:continue
                result['ocr'].append({'file':p.relative_to(root).as_posix(),'words':[{'text':w.text,'box':w.box,'confidence':w.confidence} for w in engine.read(img)]})
        return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archives',nargs='+',type=Path);p.add_argument('--ocr',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
    text=json.dumps([inspect(x,a.ocr) for x in a.archives],ensure_ascii=False,indent=2)
    if a.output:a.output.write_text(text,'utf8')
    else:print(text)
