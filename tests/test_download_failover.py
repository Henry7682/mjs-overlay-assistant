"""PowerShell 5.1 download routes, real transfer loop, and bootstrap persistence.

Network transport is injected; signature/size/hash checks remain in production.
No live release assets, user installation or game are changed.
"""
import hashlib
import json
import shutil

import pytest
from test_release_safety import ROOT, ps, quoted


def asset(name, data, urls=()):
    return dict(name=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), urls=list(urls))


def fixture(tmp_path, item):
    path = tmp_path / 'asset.json'
    path.write_text(json.dumps(item))
    return f'$a=Get-Content -Raw {quoted(path)}|ConvertFrom-Json;'


@pytest.mark.parametrize('seconds,received,remaining,slow', [
    (7.99, 1024, 10_000_000, False), (8, 1024, 10_000_000, True),
    (8, 256*1024*8, 10_000_000, False), (9, 1024, 1024*1024, False),
])
def test_slow_threshold(seconds, received, remaining, slow):
    r = ps(f'Test-SlowTransfer {seconds} {received} {remaining}')
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == str(slow)


def test_gitee_parts_before_github_retry_and_hash_checked(tmp_path):
    item = asset('whole.zip', b'hello world', ['https://github.com/test/whole'])
    item['parts'] = [asset('one.part', b'hello ', ['https://gitee.com/test/one']),
                     asset('two.part', b'world', ['https://gitee.com/test/two'])]
    trace = tmp_path/'trace.txt'
    code = fixture(tmp_path, item) + f'''
    function Receive-File($Url,$Target,$Asset,$Deadline,[switch]$SwitchOnSlow) {{
        [IO.File]::AppendAllText({quoted(trace)},$Url+"`n")
        if($Url -match 'github') {{
            if(-not $SwitchOnSlow -or ($Deadline-[datetime]::UtcNow).TotalSeconds -gt 46) {{throw 'No bounded alternate route'}}
            throw 'Simulated slow GitHub'
        }}
        $text=if($Url.EndsWith('one')){{'hello '}}else{{'world'}}
        [IO.File]::WriteAllBytes($Target,[Text.Encoding]::UTF8.GetBytes($text))
    }}
    Get-AssetFile $a {quoted(tmp_path/'cache')}
    '''
    r=ps(code)
    assert r.returncode == 0, r.stderr+r.stdout
    assert trace.read_text().splitlines() == ['https://github.com/test/whole', 'https://gitee.com/test/one', 'https://gitee.com/test/two']
    assert (tmp_path/'cache/whole.zip').read_bytes() == b'hello world'


def test_unavailable_parts_do_not_force_slow_abort(tmp_path):
    item=asset('file.zip', b'ok', ['https://github.com/test/file'])
    item['parts']=[asset('one.part', b'ok')]
    r=ps(fixture(tmp_path,item)+f'''
    function Receive-File($Url,$Target,$Asset,$Deadline,[switch]$SwitchOnSlow) {{
        if($SwitchOnSlow){{throw 'Cannot abandon the only working source'}}
        [IO.File]::WriteAllBytes($Target,[Text.Encoding]::UTF8.GetBytes('ok'))
    }}
    Get-AssetFile $a {quoted(tmp_path/'cache')}
    ''')
    assert r.returncode==0,r.stderr+r.stdout


def test_explicit_gitee_excludes_github_and_cancel_stops(tmp_path):
    item=asset('file.zip',b'ok',['https://github.com/test/file','https://gitee.com/test/file'])
    code=fixture(tmp_path,item)+f'''
    function Receive-File($Url,$Target,$Asset,$Deadline,[switch]$SwitchOnSlow) {{
        if($Url -notmatch '^https://gitee.com/'){{throw 'Wrong source'}}
        [IO.File]::WriteAllBytes($Target,[Text.Encoding]::UTF8.GetBytes('ok'))
    }}
    Get-AssetFile $a {quoted(tmp_path/'cache')} Gitee
    '''
    r=ps(code);assert r.returncode==0,r.stderr
    # Use an uncached directory; cached, verified assets do not perform network input.
    r=ps(code.replace(str(tmp_path/'cache'),str(tmp_path/'cancel')).replace('Get-AssetFile $a ', '$script:UpdateSkipped=$true; Get-AssetFile $a '))
    assert r.returncode!=0 and 'Skipped by user' in r.stderr


def test_all_routes_corrupt_never_accepted(tmp_path):
    item=asset('file.zip',b'ok',['https://github.com/test/file','https://gitee.com/test/file'])
    r=ps(fixture(tmp_path,item)+f'''
    function Receive-File($Url,$Target,$Asset,$Deadline,[switch]$SwitchOnSlow) {{[IO.File]::WriteAllBytes($Target,[Text.Encoding]::UTF8.GetBytes('xx'))}}
    Get-AssetFile $a {quoted(tmp_path/'cache')}
    ''')
    assert r.returncode!=0 and 'Unable to obtain verified asset' in r.stderr


def test_real_read_loop_switches_after_sustained_slow_progress(tmp_path):
    data=b'x'*(2*1024*1024)
    content=tmp_path/'content.bin';content.write_bytes(data)
    item=asset('file.zip',data,['https://github.com/test/file','https://gitee.com/test/file'])
    log=tmp_path/'events.jsonl'
    # The production HTTP request factory is replaced with a deterministic stream.
    # The real stopwatch, read loop, cache, fallback routing and hashing still run.
    code=fixture(tmp_path,item)+f'''
    Add-Type -TypeDefinition 'using System;using System.IO;using System.Threading;
    public class SlowFixtureStream:MemoryStream {{
      bool slow; public SlowFixtureStream(byte[] bytes,bool delay):base(bytes){{slow=delay;}}
      public override int Read(byte[] b,int o,int c){{if(slow){{Thread.Sleep(2100);c=Math.Min(c,1024);}}return base.Read(b,o,c);}}
    }}';
    function New-DownloadRequest($Url) {{
        $stream=[SlowFixtureStream]::new([IO.File]::ReadAllBytes({quoted(content)}),($Url -match 'github'))
        $response=[pscustomobject]@{{ResponseUri=[uri]$Url;ContentType='application/octet-stream';StatusCode=200;Headers=@{{ETag='test'}};Stream=$stream}}
        $response|Add-Member ScriptMethod GetResponseStream {{return $this.Stream}}
        $response|Add-Member ScriptMethod Dispose {{}}
        $req=[pscustomobject]@{{Timeout=0;ReadWriteTimeout=0;UserAgent='';Headers=@{{}};Response=$response}}
        $req|Add-Member ScriptMethod GetResponse {{return $this.Response}}
        return $req
    }}
    Set-ReleaseLog {quoted(log)}
    Get-AssetFile $a {quoted(tmp_path/'cache')}
    '''
    r=ps(code)
    assert r.returncode==0,r.stderr+r.stdout
    rows=[json.loads(line) for line in log.read_text().splitlines()]
    assert any(row['status']=='slow' and row['source']=='github.com' for row in rows)
    assert any(row['status']=='verified' and row['source']=='gitee.com' for row in rows)
    assert (tmp_path/'cache/file.zip').read_bytes()==data
    partials=list((tmp_path/'cache').glob('*.partial'))
    assert len(partials)==1 and partials[0].stat().st_size==4096


@pytest.mark.parametrize('honor_range',[True,False])
def test_legacy_partial_resumes_or_restarts_when_server_ignores_range(tmp_path,honor_range):
    data=b'0123456789abcdef';item=asset('file.zip',data,['https://github.com/file'])
    cache=tmp_path/'cache';cache.mkdir()
    (cache/'file.zip.partial').write_bytes(data[:8])
    (cache/'file.zip.partial.json').write_text(json.dumps({'url':item['urls'][0],'hash':item['sha256'],'etag':'same'}))
    log=tmp_path/'events.jsonl'
    r=ps(fixture(tmp_path,item)+f'''
    function New-DownloadRequest($Url) {{
        $req=[pscustomobject]@{{Timeout=0;ReadWriteTimeout=0;UserAgent='';Headers=@{{}};Offset=0;Url=$Url}}
        $req|Add-Member ScriptMethod AddRange {{param($offset) $this.Offset=$offset}}
        $req|Add-Member ScriptMethod GetResponse {{
            if($this.Offset -ne 8 -or $this.Headers['If-Range'] -ne 'same'){{throw 'Resume not sent'}}
            $offset=if(${'true' if honor_range else 'false'}){{$this.Offset}}else{{0}}
            $bytes=[Text.Encoding]::UTF8.GetBytes('0123456789abcdef')
            $stream=[IO.MemoryStream]::new($bytes,$offset,$bytes.Length-$offset)
            $response=[pscustomobject]@{{ResponseUri=[uri]$this.Url;ContentType='application/zip';StatusCode=$(if($offset){{206}}else{{200}});Headers=@{{ETag='same';'Content-Range'='bytes 8-15/16'}};Stream=$stream}}
            $response|Add-Member ScriptMethod GetResponseStream {{return $this.Stream}}
            $response|Add-Member ScriptMethod Dispose {{}}
            return $response
        }}
        return $req
    }}
    Set-ReleaseLog {quoted(log)}
    Get-AssetFile $a {quoted(cache)}
    ''')
    assert r.returncode==0,r.stderr+r.stdout
    assert (cache/'file.zip').read_bytes()==data
    rows=[json.loads(line) for line in log.read_text().splitlines()]
    assert any(row['status']==('resumed' if honor_range else 'full') for row in rows)
    assert not list(cache.glob('*.partial'))


@pytest.mark.parametrize('other_version,other_data,expect', [('1.0.5',b'ok',True),('1.0.4',b'ok',False),('1.0.5',b'no',False)])
def test_metadata_union_requires_same_version_and_content(tmp_path,other_version,other_data,expect):
    def manifest(ver,data,url):
        return dict(schema_version=1,channel='stable',version=ver,minimum_launcher=1,assets={'portable':asset('file.zip',data,[url])})
    github=tmp_path/'github.json';gitee=tmp_path/'gitee.json'
    github.write_text(json.dumps(manifest('1.0.5',b'ok','https://github.com/file')))
    gitee.write_text(json.dumps(manifest(other_version,other_data,'https://gitee.com/file')))
    r=ps(f'''
    function Get-RemoteBytes($Url,$Timeout) {{
        if($Url.EndsWith('.sig')){{return ,[Text.Encoding]::UTF8.GetBytes('test')}}
        $file=if($Url -match 'gitee'){{{quoted(gitee)}}}else{{{quoted(github)}}}
        return ,[IO.File]::ReadAllBytes($file)
    }}
    function Assert-Signature {{}}
    (Read-Release Auto unused).assets.portable.urls|ConvertTo-Json -Compress
    ''')
    assert r.returncode==0,r.stderr
    assert ('https://gitee.com/file' in r.stdout)==expect


def test_metadata_with_invalid_signature_cannot_contribute_urls(tmp_path):
    item=dict(schema_version=1,channel='stable',version='1.0.5',minimum_launcher=1,assets={'portable':asset('file.zip',b'ok',['https://github.com/file'])})
    path=tmp_path/'manifest.json';path.write_text(json.dumps(item))
    r=ps(f'''
    function Get-RemoteBytes($Url,$Timeout) {{
        if($Url.EndsWith('.sig')){{return ,[Text.Encoding]::UTF8.GetBytes($Url)}}
        return ,[IO.File]::ReadAllBytes({quoted(path)})
    }}
    function Assert-Signature($Bytes,$Signature,$KeyPath) {{if($Signature -match 'gitee'){{throw 'Signature rejected'}}}}
    $m=Read-Release Auto unused;if($m.assets.portable.urls.Count -ne 1){{throw 'Unexpected URL'}}
    ''')
    assert r.returncode==0,r.stderr
    assert 'Signature rejected' in r.stdout


def test_committed_library_delegation_and_atomic_refresh(tmp_path):
    root=tmp_path/'install';(root/'release').mkdir(parents=True)
    payload=root/'versions/1.0.6';(payload/'release').mkdir(parents=True)
    shutil.copy2(ROOT/'release/Release.ps1',root/'release/Release.ps1')
    (root/'current.json').write_text('{"version":"1.0.6"}')
    future='# MJS_DOWNLOAD_LIBRARY: 10\nfunction Test-FutureLibrary { "future" }\n'
    (payload/'release/Release.ps1').write_text(future)
    r=ps(f'. {quoted(root/"release/Release.ps1")}; Test-FutureLibrary; Install-DownloadLibrary {quoted(payload)} {quoted(root)}')
    assert r.returncode==0 and 'future' in r.stdout,r.stderr
    assert (root/'release/Release.ps1').read_text()==future
    assert (root/'release/Release.ps1.previous').exists()


@pytest.mark.parametrize('contents',['# old helper\nthrow "OLD"','# MJS_DOWNLOAD_LIBRARY: 2\nsyntax {'])
def test_old_or_invalid_payload_library_keeps_outer_helper(tmp_path,contents):
    root=tmp_path/'install';(root/'release').mkdir(parents=True)
    payload=root/'versions/1.0.5';(payload/'release').mkdir(parents=True)
    shutil.copy2(ROOT/'release/Release.ps1',root/'release/Release.ps1')
    (root/'current.json').write_text('{"version":"1.0.5"}')
    (payload/'release/Release.ps1').write_text(contents)
    r=ps(f'. {quoted(root/"release/Release.ps1")}; Test-SlowTransfer 8 1024 10000000')
    assert r.returncode==0 and 'True' in r.stdout,r.stderr
