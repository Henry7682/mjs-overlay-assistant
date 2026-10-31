[CmdletBinding()]
param([switch]$CheckOnly)
$ErrorActionPreference='Stop'
try {
    Set-Location -LiteralPath $PSScriptRoot
    $python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        throw 'Source environment missing. Run: powershell -File setup.ps1 -Development'
    }
    if (-not $CheckOnly) {
        $running=@(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
            $_.Name -like 'MjsOverlay*.exe'
        })
        if ($running.Count) {
            throw 'An assistant is already running. Exit it from the tray before testing source; no existing instance was changed.'
        }
    }
    $arguments=@('-X','utf8','tools/start_source.py')
    if ($CheckOnly) { $arguments+='--check' }
    & $python @arguments
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
