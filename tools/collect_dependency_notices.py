"""Collect notices from the exact locked wheels, retaining their relative paths."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def collect(wheels, check=False):
    manifest = json.loads((ROOT / 'release/dependencies.json').read_text('utf8'))
    rows = []
    for component in manifest['components']:
        wheel = Path(wheels) / component['filename']
        if sha(wheel.read_bytes()) != component['sha256']:
            raise ValueError('Wheel hash mismatch: ' + wheel.name)
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if name.endswith('/') or not re.search(r'(?i)(^|/)(license[^/]*|copying[^/]*|notice[^/]*|copyright[^/]*)$', name):
                    continue
                relative = PurePosixPath(name)
                if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
                    raise ValueError('Unsafe notice path')
                content = archive.read(name)
                destination = ROOT / 'assets/licenses' / component['name'] / 'wheel' / relative
                if check:
                    if not destination.is_file() or destination.read_bytes() != content:
                        raise ValueError('Missing or changed notice: ' + str(destination.relative_to(ROOT)))
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
                rows.append({'component': component['name'], 'version': component['version'],
                             'wheel_sha256': component['sha256'], 'wheel_path': name,
                             'path': destination.relative_to(ROOT).as_posix(), 'sha256': sha(content)})
    # This wheel omits LICENSE; retain the corresponding upstream tag's notice.
    flatbuffers = ROOT / 'assets/licenses/flatbuffers/LICENSE'
    expected = 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'
    if not flatbuffers.is_file() or sha(flatbuffers.read_bytes()) != expected:
        raise ValueError('FlatBuffers upstream license missing or changed')
    rows.append({'component': 'flatbuffers', 'version': '25.12.19',
                 'source': 'https://github.com/google/flatbuffers/blob/v25.12.19/LICENSE',
                 'path': flatbuffers.relative_to(ROOT).as_posix(), 'sha256': expected})
    index = ROOT / 'assets/licenses/dependency-notices.json'
    if not check:
        index.write_text(json.dumps({'schema_version': 1, 'notices': rows}, indent=2), 'utf8')
    elif json.loads(index.read_text('utf8'))['notices'] != rows:
        raise ValueError('Notice index differs from locked wheels')
    print(f'{len(rows)} locked dependency notices verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('wheels', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    collect(args.wheels, args.check)
