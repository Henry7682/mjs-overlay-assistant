param([switch]$Release)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run setup.ps1 first.' }
$taskBundleName = if ($env:MJS_BUILD_NAME) { $env:MJS_BUILD_NAME } else { 'MjsOverlay' }
if ($taskBundleName -notmatch '^[A-Za-z0-9_.-]+$') { throw 'Invalid bundle directory name.' }
$taskDistRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'dist'))
$taskBundlePath = [IO.Path]::GetFullPath((Join-Path $taskDistRoot $taskBundleName))
if (-not $taskBundlePath.StartsWith($taskDistRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Build target escaped dist.' }
$taskPortableExe = Join-Path $taskBundlePath ($taskBundleName + '.exe')
if (Get-Process | Where-Object { $_.Path -eq $taskPortableExe }) { throw 'Close this preview build before rebuilding it.' }
$taskSavedData = Join-Path $taskBundlePath 'data'
if (Test-Path -LiteralPath $taskSavedData) {
  $taskBackup = Join-Path $PSScriptRoot ('build-data-backups\' + $taskBundleName + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
  New-Item -ItemType Directory -Path $taskBackup -Force | Out-Null
  Copy-Item -LiteralPath $taskSavedData -Destination $taskBackup -Recurse
}
& $taskPython -X utf8 -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
$previousBuildKind=$env:MJS_RELEASE_BUILD
try {
    $env:MJS_RELEASE_BUILD=if($Release){'1'}else{'0'}
    & $taskPython -X utf8 -m PyInstaller --noconfirm MjsOverlay.spec
    $buildExit=$LASTEXITCODE
} finally { $env:MJS_RELEASE_BUILD=$previousBuildKind }
if ($buildExit -ne 0) { throw 'Build failed.' }
Copy-Item -LiteralPath README.md,THIRD_PARTY_NOTICES.md,LICENSE,requirements-runtime.lock.txt -Destination $taskBundlePath
if ($taskBackup) { Copy-Item -LiteralPath (Join-Path $taskBackup 'data') -Destination $taskBundlePath -Recurse }
Write-Host "Portable app: $taskBundlePath\$taskBundleName.exe"
