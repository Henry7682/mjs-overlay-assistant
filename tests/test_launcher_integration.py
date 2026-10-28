"""Launch tiny local fixture executables; never launch the game or mini program."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
import pytest
from test_release_safety import PS,ROOT,ps,quoted

@pytest.fixture(scope='module')
def test_exes(tmp_path_factory):
    root=tmp_path_factory.mktemp('launcher-executables');result={}
    for name,body in {
        'old':'File.WriteAllText(Environment.GetEnvironmentVariable("MJS_TEST_TRACE"),"old");',
        'new':'File.WriteAllText(Environment.GetEnvironmentVariable("MJS_READY_FILE"),"1.0.1");System.Threading.Thread.Sleep(1500);',
        'fail':'File.WriteAllText(Path.Combine(Environment.GetEnvironmentVariable("MJS_ASSISTANT_HOME"),"settings.json"),"changed");',
    }.items():
        path=root/(name+'.exe')
        code='using System;using System.IO;public class Program {public static void Main(){'+body+'}}'
        r=ps(f'Add-Type -TypeDefinition {quoted(code)} -OutputAssembly {quoted(path)} -OutputType ConsoleApplication')
        assert r.returncode==0,r.stderr
        result[name]=path
    return result

@pytest.mark.parametrize('candidate',['new','fail'])
def test_launcher_commits_after_handshake_or_restores(tmp_path,test_exes,candidate):
    root=tmp_path/'install';(root/'release').mkdir(parents=True);(root/'versions/1.0.0').mkdir(parents=True)
    (root/'data').mkdir();(root/'data/settings.json').write_text('{"preserved":true}')
    shutil.copy2(test_exes['old'],root/'versions/1.0.0/MjsOverlay.exe')
    shutil.copy2(ROOT/'launch.ps1',root/'launch.ps1')
    (root/'current.json').write_text(json.dumps({'version':'1.0.0','previous':None}))
    cache=root/'download-cache';cache.mkdir();archive=cache/'payload.zip'
    with zipfile.ZipFile(archive,'w') as z:z.write(test_exes[candidate],'MjsOverlay.exe')
    manifest={'version':'1.0.1','assets':{'portable':{'name':archive.name,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'urls':[]}}}
    fixture=root/'fixture.json';fixture.write_text(json.dumps(manifest))
    # Signature/network tested separately: this fixture isolates installation,
    # startup handshake and data rollback using the unchanged real launcher.
    library=(ROOT/'release/Release.ps1').read_text('utf8')
    library+='\nfunction Read-Release { Get-Content -Raw '+quoted(fixture)+' | ConvertFrom-Json }\n'
    (root/'release/Release.ps1').write_text(library,'utf8')
    env=dict(os.environ,MJS_TEST_TRACE=str(root/'trace.txt'))
    r=subprocess.run([str(PS),'-NoProfile','-NonInteractive','-File',str(root/'launch.ps1')],env=env,capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stderr+r.stdout
    state=json.loads((root/'current.json').read_text())
    assert state['version']==('1.0.1' if candidate=='new' else '1.0.0')
    assert json.loads((root/'data/settings.json').read_text())=={'preserved':True}
    assert not (root/'pending-update.json').exists()
    if candidate=='fail':
        assert json.loads((root/'failed-update.json').read_text())['version']=='1.0.1'
        assert list((root/'update-backups').glob('*/failed-data-*/settings.json'))
