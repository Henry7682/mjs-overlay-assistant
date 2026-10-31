# Explicit user-run test. Uses its own data and a synthetic window, not the game.
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$state=Get-Content -Raw -LiteralPath (Join-Path $root 'current.json')|ConvertFrom-Json
if($state.version -notmatch '^\d+\.\d+\.\d+$'){throw 'Invalid installed version'}
$exe=Join-Path $root ('versions\'+$state.version+'\MjsOverlay.exe')
$report=Join-Path $root ('compatibility-checks\'+(Get-Date -Format yyyyMMdd-HHmmss)+'-'+[guid]::NewGuid().ToString('N').Substring(0,6))
[IO.Directory]::CreateDirectory($report)|Out-Null
$env:MJS_ASSISTANT_HOME=Join-Path $report 'isolated-data'
$env:PYTHONIOENCODING='utf-8'
Write-Host 'Checking bundled models, Qt, OCR, UIA and settings without network or game input...'
$smoke=Join-Path $report 'offline.json'
$p=Start-Process -FilePath $exe -ArgumentList ('--smoke "'+$smoke+'"') -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $report 'offline.stdout.txt') -RedirectStandardError (Join-Path $report 'offline.stderr.txt')
$handle=$p.Handle  # Keep the process handle so PS5.1 retains its exit code.
if(-not $p.WaitForExit(90000)){$p.Kill();Write-Host ('Offline check timed out; report: '+$report);exit 1}
if($p.ExitCode -ne 0){Write-Host ('Offline check failed; report: '+$report);exit 1}
Write-Host 'A test window will briefly appear. Only that window is captured; no images are saved.'
$capture=Join-Path $report 'capture.json'
$p=Start-Process -FilePath $exe -ArgumentList ('--capture-check "'+$capture+'"') -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $report 'capture.stdout.txt') -RedirectStandardError (Join-Path $report 'capture.stderr.txt')
$handle=$p.Handle
if(-not $p.WaitForExit(30000)){$p.Kill();Write-Host ('Capture check timed out; report: '+$report);exit 1}
Write-Host ('Checks complete. Report: '+$report)
exit $p.ExitCode
