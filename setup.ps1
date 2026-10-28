[CmdletBinding()]
param([string]$Python='', [string]$ModelDirectory='', [string]$WheelDirectory='', [switch]$Development)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $Python) {
    $Python=& py -3.11 -c 'import sys;print(sys.executable)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 x64 is required.' }
}
& $Python -c "import sys,struct;assert sys.version_info[:2]==(3,11) and struct.calcsize('P')==8"
if ($LASTEXITCODE -ne 0) { throw 'Only Python 3.11 x64 is supported.' }
$venv=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv)) {
    & $Python -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated environment.' }
}
& $venv -c "import sys,struct;assert sys.version_info[:2]==(3,11) and struct.calcsize('P')==8"
if ($LASTEXITCODE -ne 0) { throw 'Existing .venv is incompatible; choose a new source directory.' }
$lock=if($Development){'requirements-dev.lock.txt'}else{'requirements-runtime.lock.txt'}
$base=@('-m','pip','--isolated','install','--disable-pip-version-check','--only-binary=:all:','--require-hashes','-r',$lock)
if ($WheelDirectory) {
    & $venv @base --no-index --find-links $WheelDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Offline dependency verification or installation failed.' }
} else {
    $success=$false
    foreach ($index in @('https://pypi.org/simple','https://pypi.tuna.tsinghua.edu.cn/simple','https://mirrors.aliyun.com/pypi/simple/')) {
        & $venv @base --index-url $index --timeout 15 --retries 1
        if ($LASTEXITCODE -eq 0) { $success=$true;break }
    }
    if (-not $success) { throw 'No index provided the verified dependencies.' }
}
& $venv -m pip --isolated check
if ($LASTEXITCODE -ne 0) { throw 'Dependency compatibility check failed.' }
$modelArgs=@('tools/restore_models.py')
if ($ModelDirectory) { $modelArgs+=@('--from-dir',$ModelDirectory) }
& $venv @modelArgs
if ($LASTEXITCODE -ne 0) { throw 'OCR model verification failed.' }
& $venv -c 'from PySide6 import QtCore,QtGui,QtWidgets; import cv2,rapidocr,onnxruntime,windows_capture,pywinauto; print("Imports OK")'
if ($LASTEXITCODE -ne 0) { throw 'Runtime import self-check failed.' }
Write-Host 'Environment and models ready. Run .venv\Scripts\python.exe -X utf8 main.py'
