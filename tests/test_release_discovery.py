"""Independent GitHub/Gitee candidates; no live network in regression tests."""
import hashlib
import json

import pytest
from test_release_safety import ps, quoted


def manifest(version, source='GitHub'):
    data=version.encode()
    host='github.com' if source=='GitHub' else 'gitee.com'
    name=f'MjsOverlay-{version}-payload.zip'
    return dict(schema_version=1,channel='stable',version=version,minimum_launcher=1,
                discovery_source=source,assets={'portable':dict(name=name,bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),urls=[f'https://{host}/henry7682/mjs-overlay-assistant/releases/download/v{version}/{name}'])})


def write_json(path,value):
    path.write_text(json.dumps(value));return quoted(path)


@pytest.mark.parametrize('mode',['blocked','slow','broken_hash'])
def test_newer_github_failure_uses_older_gitee_above_installed(tmp_path,mode):
    rows=write_json(tmp_path/'rows.json',[manifest('1.0.6'),manifest('1.0.5','Gitee')])
    trace=tmp_path/'trace.txt'
    r=ps(f'''
    function Read-Release {{$items=Get-Content -Raw {rows}|ConvertFrom-Json;$items}}
    function Get-GiteeReleaseList {{@()}}
    function Receive-File($Url,$Target,$Asset,$Deadline,[switch]$SwitchOnSlow) {{
      [IO.File]::AppendAllText({quoted(trace)},$Asset.name+"`n")
      if($Url -match 'github') {{
        if(-not $SwitchOnSlow){{throw 'Missing slow-source fallback'}}
        if('{mode}' -eq 'broken_hash'){{[IO.File]::WriteAllBytes($Target,[Text.Encoding]::UTF8.GetBytes('wrong'));return}}
        throw '{mode}'
      }}
      [IO.File]::WriteAllBytes($Target,[Text.Encoding]::UTF8.GetBytes('1.0.5'))
    }}
    $p=Get-UpdatePackage Auto unused {quoted(tmp_path/'cache')} 1.0.4
    if($p.manifest.version -ne '1.0.5' -or $p.source -ne 'Gitee'){{throw 'Wrong fallback'}}
    ''')
    assert r.returncode==0,r.stderr+r.stdout
    assert trace.read_text().splitlines()==['MjsOverlay-1.0.6-payload.zip','MjsOverlay-1.0.5-payload.zip']


@pytest.mark.parametrize('current',['1.0.5','1.0.6','1.0.7'])
def test_fallback_never_downgrades_or_reinstalls(tmp_path,current):
    rows=write_json(tmp_path/'rows.json',[manifest('1.0.5','Gitee')])
    r=ps(f'''
    function Read-Release {{$items=Get-Content -Raw {rows}|ConvertFrom-Json;$items}}
    function Get-GiteeReleaseList {{@()}}
    function Receive-File {{throw 'Must not download'}}
    if(Get-UpdatePackage Auto unused {quoted(tmp_path/'cache')} {current}){{throw 'Unexpected update'}}
    ''')
    assert r.returncode==0,r.stderr+r.stdout


def test_skip_does_not_fall_through_to_other_version(tmp_path):
    rows=write_json(tmp_path/'rows.json',[manifest('1.0.6'),manifest('1.0.5','Gitee')])
    trace=tmp_path/'trace.txt'
    r=ps(f'''
    function Read-Release {{$items=Get-Content -Raw {rows}|ConvertFrom-Json;$items}}
    function Get-GiteeReleaseList {{@()}}
    function Receive-File {{[IO.File]::AppendAllText({quoted(trace)},'once');$script:UpdateSkipped=$true;Test-Cancel}}
    Get-UpdatePackage Auto unused {quoted(tmp_path/'cache')} 1.0.4
    ''')
    assert r.returncode!=0 and 'Skipped by user' in r.stderr
    assert trace.read_text()=='once'


def test_release_list_sorted_numerically_not_api_order(tmp_path):
    path=write_json(tmp_path/'api.json',[dict(tag_name='v1.0.5',prerelease=False),dict(tag_name='v1.0.12',prerelease=False),dict(tag_name='v1.0.99',prerelease=True),dict(tag_name='v1.0.14',draft=True)])
    r=ps(f'''function Get-RemoteBytes {{return ,[IO.File]::ReadAllBytes({path})}}
    (Get-GiteeReleaseList ([datetime]::UtcNow.AddSeconds(8))).tag_name|ConvertTo-Json -Compress''')
    assert r.returncode==0,r.stderr
    assert json.loads(r.stdout)==['v1.0.12','v1.0.5']


@pytest.mark.parametrize('kind',['attachment','history','bad_signature','wrong_version','incomplete'])
def test_release_discovery_survives_both_main_channels_unavailable(tmp_path,kind):
    # Real RSA signature validation, only the HTTP transport is injected.
    m=manifest('1.0.6' if kind=='wrong_version' else '1.0.5')
    asset=m['assets']['portable'];name=asset['name']
    release_base='https://gitee.com/henry7682/mjs-overlay-assistant/releases/download/v1.0.5/'
    assets=[dict(name=name,browser_download_url=release_base+name)]
    if kind=='attachment':assets += [dict(name=n,browser_download_url=release_base+n) for n in ('release.json','release.sig')]
    if kind=='incomplete':assets=[]
    rows=write_json(tmp_path/'rows.json',[dict(tag_name='v1.0.5',assets=assets)])
    metadata=write_json(tmp_path/'manifest.json',m)
    key=quoted(tmp_path/'key.xml');signature=quoted(tmp_path/'signature')
    r=ps(f'''
    $rsa=New-Object Security.Cryptography.RSACryptoServiceProvider(3072);$rsa.PersistKeyInCsp=$false
    [IO.File]::WriteAllText({key},$rsa.ToXmlString($false))
    [IO.File]::WriteAllText({signature},[Convert]::ToBase64String($rsa.SignData([IO.File]::ReadAllBytes({metadata}),'SHA256')));$rsa.Dispose()
    function Read-Release {{throw 'Both raw main channels unavailable'}}
    function Get-GiteeReleaseList {{$items=Get-Content -Raw {rows}|ConvertFrom-Json;$items}}
    function Get-RemoteBytes($Url,$Timeout) {{
      if($Url.EndsWith('.sig')){{return ,[Text.Encoding]::UTF8.GetBytes($(if('{kind}' -eq 'bad_signature'){{'bad'}}else{{[IO.File]::ReadAllText({signature})}}))}}
      return ,[IO.File]::ReadAllBytes({metadata})
    }}
    function Receive-File($Url,$Target,$Asset,$Deadline,[switch]$SwitchOnSlow) {{
      if($Url -notmatch '^https://gitee.com/'){{throw 'GitHub must not be contacted'}}
      [IO.File]::WriteAllBytes($Target,[Text.Encoding]::UTF8.GetBytes('1.0.5'))
    }}
    $p=Get-UpdatePackage Auto {key} {quoted(tmp_path/'cache')} 1.0.4
    if($p){{$p.manifest.version}}else{{'NONE'}}
    ''')
    assert r.returncode==0,r.stderr+r.stdout
    assert r.stdout.strip().splitlines()[-1]==('1.0.5' if kind in ('attachment','history') else 'NONE')


def test_discovery_accepts_parts_only_when_all_present(tmp_path):
    m=manifest('1.0.5');item=m['assets']['portable']
    item['parts']=[dict(name=f'part{i}',bytes=2,sha256='a'*64,urls=[]) for i in (1,2)]
    mp=write_json(tmp_path/'m.json',m)
    r=ps(f'''
    $m=Get-Content -Raw {mp}|ConvertFrom-Json
    $rows=@([pscustomobject]@{{name='part1';browser_download_url='https://gitee.com/henry7682/mjs-overlay-assistant/part1'}})
    Add-DiscoveredLocations $m.assets.portable $rows
    if(Test-AssetRoute $m.assets.portable Gitee){{throw 'Missing second part accepted'}}
    $rows+=,[pscustomobject]@{{name='part2';browser_download_url='https://gitee.com/henry7682/mjs-overlay-assistant/part2'}}
    Add-DiscoveredLocations $m.assets.portable $rows
    if(-not (Test-AssetRoute $m.assets.portable Gitee)){{throw 'Complete parts not accepted'}}
    ''')
    assert r.returncode==0,r.stderr+r.stdout


def test_invalid_candidate_does_not_block_other_signed_source(tmp_path):
    bad=manifest('1.0.6');bad['assets']={}
    rows=write_json(tmp_path/'rows.json',[bad,manifest('1.0.5','Gitee')])
    r=ps(f'''
    function Read-Release {{$items=Get-Content -Raw {rows}|ConvertFrom-Json;$items}}
    function Get-GiteeReleaseList {{@()}}
    $found=@(Find-ReleaseCandidates Auto unused 1.0.4)
    if($found.Count -ne 1 -or $found[0].manifest.version -ne '1.0.5'){{throw 'Valid fallback lost'}}
    ''')
    assert r.returncode==0,r.stderr+r.stdout
