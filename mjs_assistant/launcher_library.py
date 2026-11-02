"""Migrate an old fixed launcher after its new application has committed.

No network, version switch, key replacement or user-data write. The shipped
library remains protocol-1 compatible. This also covers launchers from 1.0.0--5
which cannot themselves refresh their download implementation.
"""
import json
import os
from pathlib import Path
import re
import uuid


def _atomic_bytes(path: Path, data: bytes):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def refresh_committed_library(executable: Path, version: str) -> str:
    """Return pending while launcher handshake is uncommitted, otherwise done.

    Caller restricts this to frozen applications and catches all failures so
    updating the downloader never stops statistics/guide features.
    """
    executable = Path(executable).absolute()
    payload = executable.parent
    if (not re.fullmatch(r'\d+\.\d+\.\d+', version)
            or payload.name != version or payload.parent.name != 'versions'
            or executable.name.lower() != 'mjsoverlay.exe'):
        return 'not_installed'
    root = payload.parent.parent
    # Do not follow redirected installation paths when replacing root scripts.
    if any(p.resolve() != p for p in (root, payload.parent, payload, root/'release', payload/'release')):
        return 'redirected_path'
    state = json.loads((root/'current.json').read_text('utf-8-sig'))
    if state.get('version') != version or (root/'pending-update.json').exists():
        return 'pending'
    if (root/'release/public-key.xml').read_bytes() != (payload/'release/public-key.xml').read_bytes():
        return 'different_key'
    source = payload/'release/Release.ps1'
    destination = root/'release/Release.ps1'
    if source.resolve() != source or destination.resolve() != destination:
        return 'redirected_path'
    data = source.read_bytes()
    marker = re.search(rb'^# MJS_DOWNLOAD_LIBRARY: (\d+)\r?$', data, re.M)
    if not marker or int(marker[1]) < 3:
        return 'legacy_payload'
    pairs = [(destination, data)]
    launcher = payload/'launch.ps1'
    target_launcher = root/'launch.ps1'
    if launcher.exists() and target_launcher.exists():
        if launcher.resolve() != launcher or target_launcher.resolve() != target_launcher:
            return 'redirected_path'
        entry = launcher.read_bytes()
        if re.search(rb'^# MJS_LAUNCH_PROTOCOL: 1\r?$', entry, re.M):
            pairs.append((target_launcher, entry))
    changed = False
    # Backward compatible library first, then the new candidate-selection entry.
    # An interruption between them leaves a working old entrypoint/new library.
    for target, body in pairs:
        old = target.read_bytes()
        if old == body:
            continue
        backup = target.with_name(target.name+'.previous')
        if backup.resolve() != backup:
            return 'redirected_path'
        _atomic_bytes(backup, old)
        _atomic_bytes(target, body)
        changed = True
    return 'refreshed' if changed else 'unchanged'
