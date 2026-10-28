import hashlib
import io
import json

import pytest

from tools.verify_mirror import verify


def fixture_files(tmp_path):
    assets, mapping, responses = {}, {}, {}
    for role in ('portable', 'source', 'models', 'wheels', 'downloader'):
        body = (role + '-candidate').encode()
        row = {'name': role + '.zip', 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(), 'urls': []}
        files = [(row, body)]
        if role in ('portable', 'wheels'):
            row['parts'] = []
            files = []
            for i, chunk in enumerate((body[:4], body[4:]), 1):
                part = {'name': row['name'] + f'.part{i:02}', 'bytes': len(chunk), 'sha256': hashlib.sha256(chunk).hexdigest(), 'urls': []}
                row['parts'].append(part)
                files.append((part, chunk))
        for file, chunk in files:
            url = 'https://gitee.com/test/release/' + file['name']
            mapping[file['name']] = url
            responses[url] = chunk
        assets[role] = row
    manifest = tmp_path / 'release.json'
    manifest.write_text(json.dumps({'mirror_verified': False, 'assets': assets}))
    links = tmp_path / 'mapping.json'
    links.write_text(json.dumps(mapping))
    return manifest, links, responses


@pytest.mark.parametrize('fault', [None, 'corrupt', 'html', 'missing'])
def test_only_complete_anonymous_mirror_can_be_enabled(tmp_path, monkeypatch, fault):
    manifest, links, responses = fixture_files(tmp_path)
    first = next(iter(responses))
    if fault == 'corrupt':
        responses[first] = b'bad!'
    if fault == 'missing':
        mapping = json.loads(links.read_text())
        del mapping['downloader.zip']
        links.write_text(json.dumps(mapping))

    def open_response(request, timeout):
        result = io.BytesIO(responses[request.full_url])
        result.status = 200
        result.url = request.full_url
        result.headers = {'Content-Type': 'text/html' if fault == 'html' else 'application/octet-stream'}
        assert not request.has_header('Cookie') and not request.has_header('Authorization')
        return result

    monkeypatch.setattr('tools.verify_mirror.urllib.request.urlopen', open_response)
    output = tmp_path / 'verified.json'
    if fault:
        with pytest.raises((ValueError, KeyError)):
            verify(manifest, links, tmp_path / 'cache', output)
        assert not output.exists()
    else:
        verify(manifest, links, tmp_path / 'cache', output)
        result = json.loads(output.read_text('utf8'))
        assert result['mirror_verified'] is True
        assert len(result['assets']['portable']['parts']) == 2
        assert all(part['urls'] for part in result['assets']['portable']['parts'])
    assert json.loads(manifest.read_text())['mirror_verified'] is False
