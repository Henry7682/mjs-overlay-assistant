[CmdletBinding()]
param([ValidateSet('Portable','Source')][string]$Mode='Portable',
      [ValidateSet('Auto','GitHub','Gitee')][string]$Source='Auto',
      [string]$Destination=(Join-Path (Get-Location) 'MjsOverlay'),[string]$OfflineDirectory='',
      [switch]$CheckOnly)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'release\Release.ps1')
Assert-Platform
$Destination=[IO.Path]::GetFullPath($Destination)
$key=Join-Path $PSScriptRoot 'release\public-key.xml'
if ($CheckOnly) {
    Write-Host "Mode: $Mode | Destination: $Destination | Windows x64: OK"
    if ($Mode -eq 'Source') { Get-Command py,python -ErrorAction SilentlyContinue|Select-Object Name,Source }
    Write-Host 'Portable includes Python, Qt and OCR. Steam/game and WeChat are user-managed.'
    exit 0
}
Write-Host 'MjsOverlay 1.0.0 downloader. Press S to cancel. No global pip or PATH changes.'
$manifest=Read-Release $Source $key $OfflineDirectory
$cache=Join-Path $Destination 'download-cache';$deadline=[datetime]::UtcNow.AddMinutes(15)
if ($Mode -eq 'Portable') {
    $asset=$manifest.assets.portable
    $archive=Get-AssetFile $asset $cache $Source $OfflineDirectory $deadline
    $versionDir=Join-Path $Destination ('versions\'+$manifest.version)
    if (-not (Test-Path $versionDir)) { Expand-VerifiedZip $archive $versionDir }
    $exe=Join-Path $versionDir 'MjsOverlay.exe'
    if (-not (Test-Path $exe)) { throw 'Portable payload lacks MjsOverlay.exe.' }
    # All launch support is included in the signed payload, no extra unsigned fetches.
    foreach ($name in @('launch.cmd','launch.ps1')) { Copy-Item -LiteralPath (Join-Path $versionDir $name) -Destination $Destination -Force }
    if (-not (Test-Path (Join-Path $Destination 'release'))) { New-Item -ItemType Directory (Join-Path $Destination 'release')|Out-Null }
    foreach ($name in @('Release.ps1','public-key.xml')) { Copy-Item -LiteralPath (Join-Path $versionDir ('release\'+$name)) -Destination (Join-Path $Destination 'release') -Force }
    if (Test-Path (Join-Path $Destination 'current.json')) {
        $old=Get-Content -Raw (Join-Path $Destination 'current.json')|ConvertFrom-Json
        if ([version]$old.version -gt [version]$manifest.version) { throw 'Refusing downgrade.' }
    }
    $env:MJS_ASSISTANT_HOME=Join-Path $Destination 'data'
    $check=Join-Path $cache 'install-smoke.json'
    $process=Start-Process -FilePath $exe -ArgumentList @('--smoke',('"'+$check+'"')) -PassThru -WindowStyle Hidden
    if (-not $process.WaitForExit(90000)) { $process.Kill();throw 'Portable self-check timed out.' }
    if ($process.ExitCode -ne 0 -or -not (Test-Path $check)) { throw 'Portable self-check failed; current version retained.' }
    Write-AtomicJson (Join-Path $Destination 'current.json') @{version=$manifest.version;previous=$null}
    Write-Host ('Installed. Run: '+(Join-Path $Destination 'launch.cmd'))
} else {
    $archive=Get-AssetFile $manifest.assets.source $cache $Source $OfflineDirectory $deadline
    $project=Join-Path $Destination ('source-'+$manifest.version)
    if (Test-Path $project) { throw 'Source directory already exists. Choose a new destination to preserve edits.' }
    Expand-VerifiedZip $archive $project
    $model=Get-AssetFile $manifest.assets.models $cache $Source $OfflineDirectory $deadline
    $modelDir=Join-Path $cache ('models-'+$manifest.version+'-'+[guid]::NewGuid().ToString('N'))
    Expand-VerifiedZip $model $modelDir
    $python=$null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidate=& py -3.11 -c "import sys,struct;print(sys.executable if struct.calcsize('P')==8 else '')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate) { $python=$candidate.Trim() }
    }
    if (-not $python) {
        $installer=Get-AssetFile $manifest.dependencies.python $cache 'Auto' $OfflineDirectory $deadline
        $signature=Get-AuthenticodeSignature -LiteralPath $installer
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Python publisher signature rejected.' }
        $target=Join-Path $Destination 'python311'
        $proc=Start-Process -FilePath $installer -ArgumentList @('/passive','InstallAllUsers=0','Include_launcher=0','PrependPath=0','Shortcuts=0','AssociateFiles=0','Include_test=0',('TargetDir="'+$target+'"')) -Wait -PassThru
        if ($proc.ExitCode -notin @(0,3010)) { throw 'Python installation failed.' }
        $python=Join-Path $target 'python.exe'
    }
    $wheelDirectory=''
    if ($OfflineDirectory) {
        $wheels=Get-AssetFile $manifest.assets.wheels $cache $Source $OfflineDirectory $deadline
        $wheelDirectory=Join-Path $cache ('wheels-'+[guid]::NewGuid().ToString('N'))
        Expand-VerifiedZip $wheels $wheelDirectory
    }
    & (Join-Path $project 'setup.ps1') -Python $python -ModelDirectory $modelDir -WheelDirectory $wheelDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Source environment setup failed.' }
    Write-Host ('Source ready: '+$project)
}
