"""Bounded, cached source identity and immutable build provenance."""
from dataclasses import asdict, dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
import subprocess
import sys

from .version import VERSION

ROOT = Path(__file__).resolve().parents[1]
METADATA = 'build-identity.json'


@dataclass(frozen=True)
class BuildIdentity:
    version: str = VERSION
    channel: str = 'development'
    commit: str | None = None
    dirty: bool | None = None
    # Export provenance is historical evidence, never current source verification.
    exported_from: dict | None = None

    @property
    def display(self):
        suffix = '' if self.channel == 'release' else '-dev'
        revision = 'g' + self.commit[:8] if self.commit else '提交未知'
        state = ' · 修改状态未知' if self.dirty is None else (' · 未提交修改' if self.dirty else '')
        origin = ''
        if self.exported_from:
            source_commit = self.exported_from.get('commit')
            source_revision = 'g' + source_commit[:8] if source_commit else '提交未知'
            origin = f' · 导出来源 {self.exported_from["channel"]}/{source_revision}'
        return f'{self.version}{suffix} · {revision}{state}{origin}'

    def to_dict(self):
        return {**asdict(self), 'display_version': self.display}


def git(root, *args):
    return subprocess.run(
        ['git', '-C', str(root), *args], check=True, capture_output=True,
        text=True, encoding='utf-8', timeout=0.7,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    ).stdout.strip()


def source_identity(root=ROOT):
    try:
        # Never identify an exported tree as its enclosing private repository.
        if Path(git(root, 'rev-parse', '--show-toplevel')).resolve() != Path(root).resolve():
            return BuildIdentity()
        commit = git(root, 'rev-parse', 'HEAD')
        dirty = bool(git(root, 'status', '--porcelain', '--untracked-files=no'))
        return BuildIdentity(commit=commit, dirty=dirty)
    except (OSError, subprocess.SubprocessError):
        return BuildIdentity()


def read_identity(path):
    try:
        row = json.loads(Path(path).read_text('utf-8'))
        if (row['version'] != VERSION or row['channel'] not in {'development', 'release'}
                or row.get('dirty') not in (None, True, False)
                or (row.get('commit') is not None and not re.fullmatch(r'[0-9a-f]{40}', row['commit']))):
            return None
        if row['channel'] == 'release' and (not row.get('commit') or row.get('dirty') is not False):
            return None
        origin = row.get('exported_from')
        if origin is not None:
            if (not isinstance(origin, dict) or origin.get('version') != VERSION
                    or origin.get('channel') not in {'development', 'release'}
                    or (origin.get('dirty') is not None and type(origin['dirty']) is not bool)
                    or (origin.get('commit') is not None and
                        not re.fullmatch(r'[0-9a-f]{40}', origin['commit']))):
                return None
            origin = {k: origin.get(k) for k in ('version', 'channel', 'commit', 'dirty')}
        return BuildIdentity(**{k: row.get(k) for k in ('version', 'channel', 'commit', 'dirty')},
                             exported_from=origin)
    except (OSError, ValueError, KeyError, TypeError):
        return None


@lru_cache(maxsize=1)
def get_build_identity():
    if getattr(sys, 'frozen', False):
        return read_identity(Path(sys._MEIPASS) / METADATA) or BuildIdentity()
    if (ROOT / '.git').exists():
        current = source_identity()
        if current.commit:
            return current
    return exported_source_identity(ROOT)


def exported_source_identity(root):
    metadata = read_identity(Path(root) / METADATA)
    if metadata is None:
        return BuildIdentity()
    origin = metadata.exported_from or {
        k: getattr(metadata, k) for k in ('version', 'channel', 'commit', 'dirty')
    }
    return BuildIdentity(exported_from=origin)


def build_identity(root=ROOT, release=False):
    identity = source_identity(root)
    if release:
        if not identity.commit or identity.dirty is not False:
            raise ValueError('Release requires a known, clean Git commit.')
        if git(root, 'status', '--porcelain'):
            raise ValueError('Release requires all source changes to be committed.')
        if git(root, 'rev-parse', f'v{VERSION}^{{commit}}') != identity.commit:
            raise ValueError('Release tag, version and build commit must match.')
        identity = BuildIdentity(channel='release', commit=identity.commit, dirty=False)
    elif not identity.commit:
        identity = exported_source_identity(root)
    return identity


def write_identity(path, identity):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identity.to_dict(), ensure_ascii=False, indent=2), 'utf-8')


def validate_release_payload(payload, expected):
    actual = read_identity(Path(payload) / '_internal' / METADATA)
    if expected.channel != 'release' or actual != expected:
        raise ValueError('Frozen payload is not a release build of the current tagged commit.')
    return actual
