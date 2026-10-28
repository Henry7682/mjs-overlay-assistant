from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ASSETS = ROOT / "assets"


def user_dir() -> Path:
    override = os.getenv("MJS_ASSISTANT_HOME")
    base = Path(override) if override else ((Path(sys.executable).parent / "data") if getattr(sys, "frozen", False) else ROOT / "runtime")
    try:
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=base):
            pass
    except OSError:
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MjsOverlay"
        base.mkdir(parents=True, exist_ok=True)
    return base


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class BoardStore:
    def __init__(self, folder: Path | None = None, mode_id=None):
        from .modes import MINGDAO,MODES
        self.folder = folder or user_dir()
        self.mode_id=mode_id or MINGDAO
        if self.mode_id not in MODES: raise ValueError('未知模式')
        self._migrate_v1()
        self._load()

    def _migrate_v1(self):
        from .modes import MINGDAO,board_mode
        from .boards import validate_board
        old=self.folder/'board.json'
        target=self.folder/'boards'/MINGDAO/'current.json'
        if target.exists() or not old.exists(): return
        board=read_json(old)
        if board_mode(board or {})!=MINGDAO or validate_board(board): return
        backup=self.folder/'backup-v1'
        backup.mkdir(parents=True,exist_ok=True)
        for name in ('board.json','board.previous.json','settings.json'):
            source=self.folder/name
            if source.exists() and not (backup/name).exists(): shutil.copy2(source,backup/name)
        write_json(target,board)
        previous=read_json(self.folder/'board.previous.json')
        if previous and board_mode(previous)==MINGDAO and not validate_board(previous):write_json(target.parent/'previous.json',previous)

    def _load(self):
        from .modes import MINGDAO,board_mode,MODES
        from .boards import validate_board
        self.path=self.folder/'boards'/self.mode_id/'current.json'
        self.previous=self.path.parent/'previous.json'
        self.pending_path=self.path.parent/'pending.json'
        self.board = read_json(self.path)
        if not self.board or validate_board(self.board) or board_mode(self.board)!=self.mode_id:
            self.board=read_json(ASSETS/'boards'/f'{self.mode_id}.json')
            if self.mode_id==MINGDAO and not self.board:self.board=read_json(ASSETS/'board.json')
        if self.board and (validate_board(self.board) or board_mode(self.board)!=self.mode_id): self.board=None
        if not self.board:
            self.board={'schema_version':2,'mode_id':self.mode_id,'mode':MODES[self.mode_id],
                        'heroes':[],'period_start':'','period_end':'','available':False}

    def select(self,mode_id):
        from .modes import MODES
        if mode_id not in MODES: raise ValueError('未知模式')
        self.mode_id=mode_id;self._load()

    def all_current(self):
        from .modes import MODES
        return {mode:BoardStore(self.folder,mode).board for mode in MODES}

    def install(self, board):
        from .boards import validate_board
        from .modes import board_mode
        problems = validate_board(board)
        if problems:
            raise ValueError("；".join(problems[:8]))
        if board_mode(board)!=self.mode_id:
            other=BoardStore(self.folder,board_mode(board));other.install(board);return
        if self.board.get('heroes'):write_json(self.previous, self.board)
        write_json(self.path, board)
        self.board = board

    def rollback(self):
        from .modes import board_mode
        old = read_json(self.previous)
        if not old:
            raise ValueError("没有可回退的榜单")
        if board_mode(old)!=self.mode_id:raise ValueError('上一版模式不一致，拒绝跨模式回退')
        self.install(old)

    def lookup(self, mode_or_name, name=None):
        if name is not None:
            if mode_or_name!=self.mode_id:return BoardStore(self.folder,mode_or_name).lookup(name)
        else:name=mode_or_name
        return next((x for x in self.board["heroes"] if x["name"] == name), None)


def migrate_settings(folder):
    """Copy old calibration only into the legacy mode; preserve original backup."""
    from .modes import MINGDAO
    path=folder/'settings.json';config=read_json(path,{})
    if not isinstance(config,dict):config={}
    if config.get('schema_version',1)>=2:return config
    if path.exists():
        backup=folder/'backup-v1';backup.mkdir(parents=True,exist_ok=True)
        if not (backup/'settings.json').exists():shutil.copy2(path,backup/'settings.json')
    config['mode_profiles']={MINGDAO:config.get('profiles',{})}
    config['schema_version']=2
    # Upgrading does not assume the current game is the legacy mode.
    config['selected_mode']=None
    write_json(path,config)
    return config
