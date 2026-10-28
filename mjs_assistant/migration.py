"""Explicit import of data only; never copy arbitrary executable/log files."""
import json,shutil,tempfile,uuid
from pathlib import Path
from .boards import validate_board
from .storage import write_json

def import_data(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if source==destination:raise ValueError('请选择另一个旧版data目录')
    settings=json.loads((source/'settings.json').read_text('utf8'))
    if not isinstance(settings,dict):raise ValueError('配置格式无效')
    files={'settings.json':settings}
    for path in (source/'boards').glob('*/*.json'):
        if path.name not in ('current.json','previous.json'):continue
        board=json.loads(path.read_text('utf8'))
        from .modes import board_mode
        if validate_board(board) or board_mode(board)!=path.parent.name:raise ValueError('旧榜单校验失败或模式目录不符，未修改当前配置')
        files[path.relative_to(source).as_posix()]=board
    # Version 0.1 used root-level files. Preserve these official periods too;
    # the explicit per-mode files take precedence when both layouts exist.
    from .modes import MINGDAO,board_mode
    for old,new in (('board.json','current.json'),('board.previous.json','previous.json')):
        path=source/old
        if not path.is_file():continue
        board=json.loads(path.read_text('utf8'))
        if validate_board(board) or board_mode(board)!=MINGDAO:raise ValueError('旧版明刀暗箭榜单校验失败，未修改当前配置')
        files.setdefault(f'boards/{MINGDAO}/{new}',board)
    backup=destination/'migration-backups'/uuid.uuid4().hex;backup.mkdir(parents=True)
    installed=[]
    try:
        for name,data in files.items():
            target=destination/name;old=backup/name
            if target.exists():old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,old)
            installed.append(name);write_json(target,data)
    except Exception:
        for name in installed:
            old=backup/name;target=destination/name
            if old.exists():shutil.copy2(old,target)
            else:target.unlink(missing_ok=True)
        raise
    return backup
