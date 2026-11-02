import hashlib
import json

import pytest
from test_release_safety import ROOT,ps,quoted
from tools.verify_mirror import discover_mapping


def test_discover_exact_gitee_version_without_manual_urls():
    row={'tag_name':'v1.0.5','assets':[{'name':'MjsOverlay-1.0.5-payload.zip.part01',
        'browser_download_url':'https://gitee.com/henry7682/mjs-overlay-assistant/releases/download/v1.0.5/part01'}]}
    assert len(discover_mapping('1.0.5',row))==1
    with pytest.raises(ValueError,match='version'):discover_mapping('1.0.6',row)
    row['assets']*=2
    with pytest.raises(ValueError,match='Duplicate'):discover_mapping('1.0.5',row)


@pytest.mark.parametrize('url',['http://gitee.com/x','https://other.example/x','https://gitee.com/other/repo/x'])
def test_discovered_mirror_rejects_other_locations(url):
    with pytest.raises(ValueError,match='location'):
        discover_mapping('1.0.5',{'tag_name':'v1.0.5','assets':[{'name':'MjsOverlay-test','browser_download_url':url}]})


def test_prepare_signed_upload_keeps_bytes_and_refuses_existing_directory(tmp_path):
    assets={}
    for role in ('portable','source','models','wheels','downloader'):
        body=role.encode();name=f'MjsOverlay-1.0.6-{role}.zip';(tmp_path/name).write_bytes(body)
        assets[role]=dict(name=name,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),urls=[])
    manifest=tmp_path/'release.json';signature=tmp_path/'release.sig';key=tmp_path/'key.xml'
    manifest.write_text(json.dumps(dict(schema_version=1,channel='stable',version='1.0.6',minimum_launcher=1,assets=assets)))
    output=tmp_path/'upload';history=tmp_path/'history'
    prepare=f'& {quoted(ROOT/"release/prepare-mirror.ps1")} -Manifest {quoted(manifest)} -AssetsDirectory {quoted(tmp_path)} -OutputDirectory {quoted(output)} -HistoryDirectory {quoted(history)} -KeyPath {quoted(key)}'
    result=ps(f'''
      $rsa=New-Object Security.Cryptography.RSACryptoServiceProvider(3072);$rsa.PersistKeyInCsp=$false
      [IO.File]::WriteAllText({quoted(key)},$rsa.ToXmlString($false))
      [IO.File]::WriteAllText({quoted(signature)},[Convert]::ToBase64String($rsa.SignData([IO.File]::ReadAllBytes({quoted(manifest)}),'SHA256')));$rsa.Dispose()
      {prepare}
    ''')
    assert result.returncode==0,result.stderr+result.stdout
    assert len(list(output.iterdir()))==7
    assert (output/'release.json').read_bytes()==manifest.read_bytes()==(history/'1.0.6.json').read_bytes()
    assert (history/'1.0.6.sig').read_bytes()==signature.read_bytes()
    again=ps(prepare)
    assert again.returncode!=0 and 'must be new' in again.stderr
    (history/'1.0.6.json').write_bytes(b'prior immutable metadata')
    conflict=ps(prepare.replace(quoted(output),quoted(tmp_path/'second-upload')))
    assert conflict.returncode!=0 and 'different bytes' in conflict.stderr
    assert not (tmp_path/'second-upload').exists()
