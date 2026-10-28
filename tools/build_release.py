"""Package tested frozen files and an audited source snapshot. No publication.

The output release manifest is unsigned until release/sign.ps1 is run.
Gitee asset URLs may only be added after an anonymous byte/hash check.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mjs_assistant.version import VERSION,REPOSITORY
from tools.export_public_source import export
from tools.collect_dependency_notices import collect

ROOT=Path(__file__).resolve().parents[1]

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def zipped(folder,target):
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(folder.rglob('*')):
            rel=p.relative_to(folder)
            if p.is_file() and rel.parts[0] not in {'runtime','data'} and not {'__pycache__','.git','.venv'}.intersection(rel.parts):z.write(p,rel.as_posix())
    with zipfile.ZipFile(target) as z:
        if z.testzip():raise ValueError('ZIP integrity failed')

def main():
    p=argparse.ArgumentParser();p.add_argument('--frozen',type=Path,required=True);p.add_argument('--wheels',type=Path,required=True)
    p.add_argument('--installers',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Choose a fresh output folder; do not replace published assets.')
    collect(a.wheels, check=True)
    a.output.mkdir(parents=True);work=a.output/'staging';work.mkdir()
    public=work/'source';export(public)
    payload=work/'payload';shutil.copytree(a.frozen,payload)
    if not (payload/'MjsOverlay.exe').is_file():raise ValueError('Frozen executable missing')
    if (payload/'data').exists():raise ValueError('Never package runtime data')
    shutil.copytree(ROOT/'assets/licenses',payload/'_internal/assets/licenses',dirs_exist_ok=True)
    for name in ('launch.cmd','launch.ps1','README.md','LICENSE','THIRD_PARTY_NOTICES.md'):shutil.copy2(ROOT/name,payload/name)
    (payload/'release').mkdir(exist_ok=True)
    for name in ('Release.ps1','public-key.xml'):shutil.copy2(ROOT/'release'/name,payload/'release'/name)
    shutil.copytree(ROOT/'docs',payload/'docs')
    standalone=work/'standalone';standalone.mkdir();shutil.copytree(payload,standalone/'versions'/VERSION)
    for name in ('launch.cmd','launch.ps1','README.md','LICENSE'):shutil.copy2(ROOT/name,standalone/name)
    shutil.copytree(payload/'release',standalone/'release')
    (standalone/'current.json').write_text(json.dumps({'version':VERSION,'previous':None}),'utf8')
    bootstrap=work/'bootstrap';bootstrap.mkdir();(bootstrap/'release').mkdir()
    for name in ('download.ps1','download.cmd'):shutil.copy2(ROOT/name,bootstrap/name)
    for name in ('Release.ps1','public-key.xml'):shutil.copy2(ROOT/'release'/name,bootstrap/'release'/name)
    models=work/'models';models.mkdir()
    manifest=json.loads((ROOT/'assets/models/manifest.json').read_text('utf8'))
    for name,row in manifest['models'].items():
        path=ROOT/'assets/models'/name
        if digest(path)!=row['sha256'] or path.stat().st_size!=row['bytes']:raise ValueError('Model integrity failed')
        shutil.copy2(path,models/name)
    shutil.copy2(ROOT/'assets/models/manifest.json',models/'manifest.json')
    wheels=work/'wheels';wheels.mkdir()
    deps=json.loads((ROOT/'release/dependencies.json').read_text('utf8'))
    for row in deps['components']:
        path=a.wheels/row['filename']
        if digest(path)!=row['sha256']:raise ValueError('Wheel integrity failed')
        shutil.copy2(path,wheels/path.name)
    folders={'portable':payload,'standalone':standalone,'source':public,'models':models,'wheels':wheels,'downloader':bootstrap}
    names={'portable':'payload','standalone':'win64','source':'source','models':'models','wheels':'offline-wheels-win64','downloader':'downloader'}
    assets={}
    for role,folder in folders.items():
        path=a.output/f'MjsOverlay-{VERSION}-{names[role]}.zip';zipped(folder,path)
        row={'name':path.name,'bytes':path.stat().st_size,'sha256':digest(path),'urls':[f'https://github.com/{REPOSITORY}/releases/download/v{VERSION}/{path.name}']}
        if role!='standalone':
            row['parts']=[]
            with path.open('rb') as stream:
                index=0
                while block:=stream.read(90_000_000):
                    index+=1;part=a.output/(path.name+f'.part{index:02d}');part.write_bytes(block)
                    row['parts'].append({'name':part.name,'bytes':len(block),'sha256':digest(part),'urls':[]})
        assets[role]=row
    installer_rows=json.loads((a.installers/'manifest.json').read_text('utf8'))
    dependencies={}
    for row in installer_rows:
        path=a.installers/row['name']
        if digest(path)!=row['sha256']:raise ValueError('Installer integrity failed')
        shutil.copy2(path,a.output/path.name)
        dependencies['python' if row['name'].startswith('python-') else 'vcredist']=row
    release={'schema_version':1,'version':VERSION,'channel':'stable','minimum_launcher':1,
        'product':'名将浮窗助手','release_notes':'公开测试版；实战与已知限制见README和TODO。',
        'mirror_verified':False,'assets':assets,'dependencies':dependencies}
    (a.output/'release.json').write_text(json.dumps(release,ensure_ascii=False,indent=2),'utf8')
    (a.output/'checksums.json').write_text(json.dumps({p.name:{'bytes':p.stat().st_size,'sha256':digest(p)} for p in a.output.iterdir() if p.is_file()},indent=2),'utf8')
    print(json.dumps({'assets':len(assets),'output':str(a.output),'signed':False,'mirror_verified':False}))

if __name__=='__main__':main()
