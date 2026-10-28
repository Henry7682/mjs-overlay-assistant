$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
py -3.11 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 x64 is required.' }
& .\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .\.venv\Scripts\python.exe tools/restore_models.py
if ($LASTEXITCODE -ne 0) { throw 'Restore OCR models from a complete portable bundle as described in README.md.' }
