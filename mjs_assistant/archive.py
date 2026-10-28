"""Bounded data-only archives shared by diagnostic and update tooling."""
import hashlib
import stat
import zipfile
from pathlib import Path, PurePosixPath

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def safe_extract(source,destination,max_bytes=2_000_000_000,max_files=20000):
    root=Path(destination).resolve()
    with zipfile.ZipFile(source) as archive:
        entries=archive.infolist()
        if len(entries)>max_files or sum(x.file_size for x in entries)>max_bytes:raise ValueError('归档超过容量限制')
        seen=set()
        for item in entries:
            raw=item.filename.replace('\\','/');parts=PurePosixPath(raw).parts
            if not parts or raw.startswith('/') or any(x in ('..','.') or ':' in x or x.rstrip(' .')!=x for x in parts):raise ValueError('不安全的归档路径')
            if any(x.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} for x in parts):raise ValueError('保留文件名')
            key=raw.rstrip('/').casefold()
            if key in seen:raise ValueError('重复归档路径')
            seen.add(key)
            if stat.S_ISLNK(item.external_attr>>16):raise ValueError('禁止符号链接')
            target=root.joinpath(*parts)
            if not target.resolve().is_relative_to(root):raise ValueError('归档路径越界')
            if target.exists():raise ValueError('解压目标必须为空')
        root.mkdir(parents=True,exist_ok=True)
        for item in entries:
            target=root.joinpath(*PurePosixPath(item.filename.replace('\\','/')).parts)
            if item.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(item) as src,target.open('xb') as out:
                for block in iter(lambda:src.read(1024*1024),b''):out.write(block)
