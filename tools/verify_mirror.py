"""Verify anonymous Gitee assets before adding their URLs to a release manifest.

Mapping JSON: {"exact-asset-or-part-name": "https://gitee.com/..."}.
Uses no browser cookies or account credentials. Does not sign or publish.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request


def verify(manifest_path, mapping_path, cache, output):
    manifest = json.loads(Path(manifest_path).read_text('utf8'))
    mapping = json.loads(Path(mapping_path).read_text('utf8'))
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    report = []
    required = ('portable', 'source', 'models', 'wheels', 'downloader')

    def download(row):
        name = row['name']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or not 0 < row['bytes'] <= 100_000_000:
            raise ValueError('Unsafe or oversized mirror asset: ' + name)
        url = mapping[name]
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != 'gitee.com' or parsed.username or parsed.password:
            raise ValueError('Use the observed public Gitee download URL')
        path = cache / name
        temporary = path.with_name(path.name + '.verifying')
        digest = hashlib.sha256()
        size = 0
        started = time.monotonic()
        request = urllib.request.Request(url, headers={'User-Agent': 'MjsOverlay-ReleaseVerification/1.0.0'})
        try:
            with urllib.request.urlopen(request, timeout=20) as response, temporary.open('wb') as out:
                if response.status != 200 or urllib.parse.urlsplit(response.url).scheme != 'https':
                    raise ValueError('Unexpected download response')
                if 'text/html' in response.headers.get('Content-Type', '').lower():
                    raise ValueError('Login or HTML page returned instead of asset')
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > row['bytes'] or time.monotonic() - started > 300:
                        raise ValueError('Download exceeds declared size or time limit')
                    digest.update(chunk)
                    out.write(chunk)
            if size != row['bytes'] or digest.hexdigest() != row['sha256']:
                raise ValueError('Mirror bytes differ from signed release candidate: ' + name)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        report.append({'name': name, 'bytes': size, 'sha256': digest.hexdigest(), 'url': url})
        row['urls'] = list(dict.fromkeys([*row.get('urls', []), url]))
        print('Verified anonymously: ' + name, flush=True)
        return path

    for role in required:
        asset = manifest['assets'][role]
        if asset['name'] in mapping:
            download(asset)
        else:
            if not asset.get('parts'):
                raise ValueError('No verified full asset or parts for ' + role)
            digest = hashlib.sha256()
            size = 0
            for part in asset['parts']:
                with download(part).open('rb') as stream:
                    while chunk := stream.read(1024 * 1024):
                        size += len(chunk)
                        digest.update(chunk)
            if size != asset['bytes'] or digest.hexdigest() != asset['sha256']:
                raise ValueError('Merged mirror parts differ: ' + role)
    manifest['mirror_verified'] = True
    # A fresh file prevents accidental replacement of an already published list.
    with Path(output).open('x', encoding='utf8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    (cache / 'anonymous-verification.json').write_text(json.dumps(report, indent=2), 'utf8')
    print('All required mirror roles verified. Sign the new manifest before publishing.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--mapping', required=True, type=Path)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    verify(args.manifest, args.mapping, args.cache, args.output)
