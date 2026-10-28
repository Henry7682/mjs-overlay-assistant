"""Bundle only deliverables; omit private captures, logs, environments and caches."""
import hashlib
import json
import zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
bundle='MjsOverlay-0.3.10-preview'
portable=root/'dist'/bundle
assert (portable/(bundle+'.exe')).is_file()
version='0.3.10-preview'
outputs=[]
with zipfile.ZipFile(root/f'MjsOverlay-{version}-win64.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for path in sorted(portable.rglob('*')):
        rel=path.relative_to(portable)
        if path.is_file() and rel.parts[0]!='data':z.write(path,Path(bundle)/rel)
with zipfile.ZipFile(root/f'MjsOverlay-{version}-win64.zip','r') as z:
    assert z.testzip() is None
outputs.append(root/f'MjsOverlay-{version}-win64.zip')
with zipfile.ZipFile(root/f'MjsOverlay-{version}-source.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for folder in ('mjs_assistant','assets','tools','tests'):
        for path in sorted((root/folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:z.write(path,Path('MjsOverlay-source')/path.relative_to(root))
    for name in ('main.py','start.cmd','setup.ps1','build.ps1','MjsOverlay.spec','pytest.ini','requirements.lock.txt','README.md','TODO.md','AGENTS.md','RELEASE-0.3.md','RELEASE-0.3.1.md','RELEASE-0.3.2.md','RELEASE-0.3.3.md','RELEASE-0.3.4.md','RELEASE-0.3.5.md','RELEASE-0.3.6.md','RELEASE-0.3.7.md','RELEASE-0.3.8.md','RELEASE-0.3.9.md','RELEASE-0.3.10.md','README-0.1.md','TESTING.md','IMPLEMENTATION-0.2.md','THIRD_PARTY_NOTICES.md','list.md','.gitignore'):
        z.write(root/name,Path('MjsOverlay-source')/name)
with zipfile.ZipFile(root/f'MjsOverlay-{version}-source.zip','r') as z:
    assert z.testzip() is None
outputs.append(root/f'MjsOverlay-{version}-source.zip')
manifest={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in outputs}
(root/f'release-manifest-{version}.json').write_text(json.dumps(manifest,indent=2),'utf8')
print(json.dumps(manifest,indent=2),flush=True)
