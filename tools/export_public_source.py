"""Create a new, allowlisted public snapshot; never copy workspace Git history.

Review the resulting files before pushing. This scanner is an aid, not a
guarantee that arbitrary future source edits are free of private information.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TOOLS = (
    'smoke.py', 'restore_models.py', 'replay_diagnostics.py',
    'portable_worker_smoke.py', 'probe_focus_roundtrip.py', 'replay_provider.py',
    'package_release.py', 'export_public_source.py',
    'lock_dependencies.py', 'build_release.py', 'collect_dependency_notices.py', 'verify_mirror.py',
)
ROOT_FILES = (
    'main.py', 'setup.ps1', 'start.cmd', 'build.ps1', 'MjsOverlay.spec',
    'pytest.ini', 'requirements.lock.txt', 'download.cmd', 'download.ps1',
    'launch.cmd', 'launch.ps1', '.gitignore', 'LICENSE', 'list.md',
    'README.md', 'TODO.md', 'TESTING.md', 'AGENTS.md',
    'PERFORMANCE-2026-10-28.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md',
    'requirements-runtime.in', 'requirements-dev.in', 'requirements-runtime.lock.txt', 'requirements-dev.lock.txt',
    'IMPLEMENTATION-0.2.md', 'README-0.1.md',
)


def export(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Destination must be new; no existing checkout is replaced.')
    selected = [ROOT / name for name in ROOT_FILES]
    selected += list(ROOT.glob('RELEASE-*.md'))
    selected += [ROOT / 'tools' / name for name in TOOLS]
    for folder, patterns in {
        'mjs_assistant': ('*.py',), 'tests': ('*.py',),
        'tests/fixtures': ('*.png', '*.md'),
        'assets/boards': ('*.json',), 'assets/sources': ('*.jpg',),
        'assets/licenses': ('*',), 'assets/models': ('manifest.json',),
        'docs': ('*.md',), '.github': ('*.yml',), 'release': ('*.ps1', 'dependencies.json', 'public-key.xml'),
    }.items():
        for pattern in patterns:
            selected += [p for p in (ROOT / folder).rglob(pattern) if p.is_file()]
    selected += [ROOT / 'assets' / name for name in ('names.json', 'board.json', 'dependencies.json', 'ocr-selftest.png', 'official-2026-10-22.jpg')]
    forbidden = {'.git', '.research', '.venv', 'runtime', 'data', '__pycache__'}
    outputs = {}
    for path in sorted(set(selected)):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing or linked file: {path.name}')
        rel = path.relative_to(ROOT)
        if forbidden.intersection(rel.parts):
            raise ValueError(f'Forbidden path: {rel}')
        body = path.read_bytes()
        if path.suffix == '.md' and 'licenses' not in rel.parts:
            text = body.decode('utf8')
            # Public historical conclusions retain relative evidence indexes;
            # machine-specific drive roots and installation paths are private.
            text = re.sub(r'(?i)D:[\\/]mjs[\\/]', '', text)
            text = re.sub(r'(?i)(?<![a-z0-9])[A-Z]:[\\/](?!/)[^\s`\"<>，。；、）)]*', '[本机路径已省略]', text)
            body = text.encode('utf8')
        if path.suffix.lower() not in {'.jpg', '.png'}:
            text = body.decode('utf-8-sig')
            if re.search(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN (?:RSA )?PRIVATE KEY-----', text):
                raise ValueError(f'Possible credential: {rel}')
            if re.search(r'(?i)[A-Z]:[\\/]Users[\\/](?!Public)', text):
                raise ValueError(f'Personal profile path: {rel}')
        outputs[rel] = body
    destination.mkdir(parents=True)
    for rel, body in outputs.items():
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    return {'files': len(outputs), 'bytes': sum(map(len, outputs.values())),
            'sha256': {p.as_posix(): hashlib.sha256(body).hexdigest() for p, body in outputs.items()}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    parser.add_argument('--audit', type=Path)
    args = parser.parse_args()
    result = export(args.destination)
    if args.audit:
        args.audit.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({k: result[k] for k in ('files', 'bytes')}))
