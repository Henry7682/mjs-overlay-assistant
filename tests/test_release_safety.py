"""Real Windows PowerShell 5.1 checks, without network or application input."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
import pytest
from mjs_assistant.archive import safe_extract

ROOT=Path(__file__).resolve().parents[1]
PS=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'

def ps(code):
    script="$ErrorActionPreference='Stop'; . '"+str(ROOT/'release/Release.ps1').replace("'","''")+"'; "+code
    return subprocess.run([str(PS),'-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,timeout=45)

def quoted(path):return "'"+str(path).replace("'","''")+"'"

def test_update_log_only_records_source_host_and_rotates(tmp_path):
    path=tmp_path/'events.jsonl.update';path.write_bytes(b'x'*999990)
    result=ps(f"Set-ReleaseLog {quoted(path)}; Write-ReleaseEvent download failed 'https://example.com/private?token=hidden' 1.0.0")
    assert result.returncode==0,result.stderr
    row=json.loads(path.read_text('utf8'))
    assert row['source']=='example.com' and 'hidden' not in path.read_text('utf8')
    assert path.with_name(path.name+'.1').stat().st_size==999990

@pytest.mark.parametrize('name',['../escape.txt','/escape.txt','C:/escape','sub/../../escape','aux.txt','a:stream','trailing.','dir\\..\\escape'])
def test_archive_rejects_paths_before_write(tmp_path,name):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('safe.txt','ok');z.writestr(name,'unsafe')
    with pytest.raises(ValueError):safe_extract(archive,tmp_path/'python')
    result=ps(f'Expand-VerifiedZip {quoted(archive)} {quoted(tmp_path/"powershell")}')
    assert result.returncode!=0
    assert not (tmp_path/'python').exists() and not (tmp_path/'powershell').exists()

def test_payload_tampering_and_extra_files(tmp_path):
    archive=tmp_path/'good.zip';out=tmp_path/'out'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('folder/name.txt','correct')
    command=f'Assert-Payload {quoted(archive)} {quoted(out)}'
    assert ps(f'Expand-VerifiedZip {quoted(archive)} {quoted(out)};'+command).returncode==0
    (out/'extra.dll').write_bytes(b'x')
    assert ps(command).returncode!=0
    (out/'extra.dll').unlink();(out/'folder/name.txt').write_text('wrong')
    assert ps(command).returncode!=0

def test_rollback_removes_new_boards_but_preserves_failed_copy(tmp_path):
    data=tmp_path/'data';(data/'boards').mkdir(parents=True)
    (data/'settings.json').write_text('{"enabled":false}')
    (data/'boards/current.json').write_text('old')
    result=ps(f'$b=Save-UserData {quoted(tmp_path)}; [IO.File]::WriteAllText({quoted(data/"settings.json")},"changed"); [IO.File]::WriteAllText({quoted(data/"boards/new.json")},"new"); Restore-UserData {quoted(tmp_path)} $b')
    assert result.returncode==0,result.stderr
    assert json.loads((data/'settings.json').read_text())=={'enabled':False}
    assert not (data/'boards/new.json').exists()
    assert list((tmp_path/'update-backups').glob('*/failed-data-*/boards/new.json'))

def test_offline_parts_and_corrupt_part(tmp_path):
    offline=tmp_path/'offline';offline.mkdir();cache=tmp_path/'cache'
    def asset(name,data):
        (offline/name).write_bytes(data)
        return dict(name=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),urls=[])
    a=asset('test.zip',b'hello world');(offline/'test.zip').unlink()
    a['parts']=[asset('test.part01',b'hello '),asset('test.part02',b'world')]
    manifest=tmp_path/'asset.json';manifest.write_text(json.dumps(a))
    cmd=f'$a=Get-Content -Raw {quoted(manifest)}|ConvertFrom-Json; Get-AssetFile $a {quoted(cache)} Auto {quoted(offline)}'
    r=ps(cmd);assert r.returncode==0,r.stderr
    assert (cache/'test.zip').read_bytes()==b'hello world'
    (offline/'test.part02').write_bytes(b'wrong')
    r=ps(cmd.replace(quoted(cache),quoted(tmp_path/'cache2')))
    assert r.returncode!=0 and not (tmp_path/'cache2/test.zip').exists()

def test_signed_manifest_and_tamper(tmp_path):
    manifest=tmp_path/'release.json';manifest.write_text(json.dumps(dict(schema_version=1,channel='stable',version='1.0.0',minimum_launcher=1)))
    key=tmp_path/'public.xml';sig=tmp_path/'release.sig'
    cmd=f'''$r=New-Object Security.Cryptography.RSACryptoServiceProvider(3072);$r.PersistKeyInCsp=$false;
    [IO.File]::WriteAllText({quoted(key)},$r.ToXmlString($false));
    [IO.File]::WriteAllText({quoted(sig)},[Convert]::ToBase64String($r.SignData([IO.File]::ReadAllBytes({quoted(manifest)}),'SHA256')));$r.Dispose();
    (Read-Release Auto {quoted(key)} {quoted(tmp_path)}).version'''
    r=ps(cmd);assert r.returncode==0 and '1.0.0' in r.stdout,r.stderr
    manifest.write_text(manifest.read_text().replace('1.0.0','9.0.0'))
    r=ps(f'Read-Release Auto {quoted(key)} {quoted(tmp_path)}')
    assert r.returncode!=0

def test_ps_scripts_parse_in_windows_powershell():
    for path in [ROOT/'setup.ps1',ROOT/'download.ps1',ROOT/'launch.ps1']:
        r=ps(f'$e=$null;$t=$null;[Management.Automation.Language.Parser]::ParseFile({quoted(path)},[ref]$t,[ref]$e)|Out-Null;if($e){{throw ($e|Out-String)}}')
        assert r.returncode==0,r.stderr
