$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run setup.ps1 first.' }
$taskBundleName = if ($env:MJS_BUILD_NAME) { $env:MJS_BUILD_NAME } else { 'MjsOverlay-0.3.10-preview' }
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
& $taskPython -X utf8 -m PyInstaller --noconfirm MjsOverlay.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Copy-Item -LiteralPath README.md,TODO.md,AGENTS.md,RELEASE-0.3.md,RELEASE-0.3.1.md,RELEASE-0.3.2.md,RELEASE-0.3.3.md,RELEASE-0.3.4.md,RELEASE-0.3.5.md,RELEASE-0.3.6.md,RELEASE-0.3.7.md,RELEASE-0.3.8.md,RELEASE-0.3.9.md,RELEASE-0.3.10.md,TESTING.md,THIRD_PARTY_NOTICES.md,IMPLEMENTATION-0.2.md,requirements.lock.txt -Destination $taskBundlePath
if ($taskBackup) { Copy-Item -LiteralPath (Join-Path $taskBackup 'data') -Destination $taskBundlePath -Recurse }
Write-Host "Portable app: $taskBundlePath\$taskBundleName.exe"
