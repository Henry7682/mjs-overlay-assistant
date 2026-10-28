"""Restore git-ignored OCR models from a local package or portable bundle."""
import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--from-dir',type=Path,help='Local _internal/assets/models directory')
    args=parser.parse_args()
    target=Path(__file__).resolve().parents[1]/'assets/models'
    manifest=json.loads((target/'manifest.json').read_text('utf8'))['models']
    spec=importlib.util.find_spec('rapidocr')
    sources=([args.from_dir] if args.from_dir else [])+([Path(spec.origin).parent/'models'] if spec else [])
    pending=[]
    for name,record in manifest.items():
        output=target/name
        candidates=[output] if output.exists() else [folder/filename for folder in sources for filename in (name,record['package_name'])]
        match=next((p for p in candidates if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==record['sha256']),None)
        if match is None:
            raise SystemExit(f'{name}: missing or hash mismatch. Use --from-dir with a complete portable bundle; existing files are not overwritten.')
        if match!=output:pending.append((match,output))
    for source,output in pending:shutil.copyfile(source,output)
    print(f'Validated {len(manifest)} OCR models; restored {len(pending)}.')


if __name__=='__main__':main()
