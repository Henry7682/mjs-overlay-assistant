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
    Get-DependencyStatus|Format-List
    Write-Host 'Missing registry entry alone does not imply failure: portable DLLs may suffice. No software was installed.'
    exit 0
}
Write-Host 'MjsOverlay 1.0.0 downloader. Press S to cancel. No global pip or PATH changes.'
$manifest=Read-Release $Source $key $OfflineDirectory
$cache=Join-Path $Destination 'download-cache';$deadline=[datetime]::UtcNow.AddMinutes(15)
if ($Mode -eq 'Portable') {
    $old=$null
    if (Test-Path -LiteralPath (Join-Path $Destination 'current.json')) {
        $old=Get-Content -Raw -LiteralPath (Join-Path $Destination 'current.json')|ConvertFrom-Json
        Assert-Version $old.version
        if ([version]$old.version -gt [version]$manifest.version) { throw 'Refusing downgrade.' }
        $oldExe=Join-Path $Destination ('versions\'+$old.version+'\MjsOverlay.exe')
        if (Get-Process -Name MjsOverlay -ErrorAction SilentlyContinue|Where-Object {$_.Path -eq $oldExe}) { throw 'Close the running assistant before installing.' }
    }
    $asset=$manifest.assets.portable
    $archive=Get-AssetFile $asset $cache $Source $OfflineDirectory $deadline
    $versionDir=Join-Path $Destination ('versions\'+$manifest.version)
    if (-not (Test-Path $versionDir)) { Expand-VerifiedZip $archive $versionDir }
    Assert-Payload $archive $versionDir
    $exe=Join-Path $versionDir 'MjsOverlay.exe'
    if (-not (Test-Path $exe)) { throw 'Portable payload lacks MjsOverlay.exe.' }
    # Smoke uses isolated temporary state, never the existing user's boards.
    $env:MJS_ASSISTANT_HOME=Join-Path $cache ('smoke-data-'+[guid]::NewGuid().ToString('N'))
    $check=Join-Path $cache ('install-smoke-'+[guid]::NewGuid().ToString('N')+'.json')
    $process=Start-Process -FilePath $exe -ArgumentList @('--smoke',('"'+$check+'"')) -PassThru -WindowStyle Hidden
    if (-not $process.WaitForExit(90000)) { $process.Kill();throw 'Portable self-check timed out.' }
    if ($process.ExitCode -ne 0 -or -not (Test-Path $check)) {
        if (-not (Get-DependencyStatus).VCRuntime) {
            $repair=Get-AssetFile $manifest.dependencies.vcredist $cache 'Auto' $OfflineDirectory $deadline
            Assert-Publisher $repair 'Microsoft Corporation'
            Write-Host ('Microsoft VC++ runtime may be missing. Run the verified installer manually: '+$repair)
        }
        throw 'Portable self-check failed; current version retained.'
    }
    # Existing fixed launchers stay intact; protocol upgrades use a new full install.
    foreach ($name in @('launch.cmd','launch.ps1')) {
        $out=Join-Path $Destination $name
        if (-not (Test-Path -LiteralPath $out)) { Copy-Item -LiteralPath (Join-Path $versionDir $name) -Destination $out }
    }
    [IO.Directory]::CreateDirectory((Join-Path $Destination 'release'))|Out-Null
    foreach ($name in @('Release.ps1','public-key.xml')) {
        $out=Join-Path $Destination ('release\'+$name)
        if (-not (Test-Path -LiteralPath $out)) { Copy-Item -LiteralPath (Join-Path $versionDir ('release\'+$name)) -Destination $out }
    }
    $previous=if($old -and $old.version -ne $manifest.version){$old.version}else{$null}
    Write-AtomicJson (Join-Path $Destination 'current.json') @{version=$manifest.version;previous=$previous}
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
        Assert-Publisher $installer 'Python Software Foundation'
        $target=Join-Path $Destination 'python311'
        $proc=Start-Process -FilePath $installer -ArgumentList @('/passive','InstallAllUsers=0','Include_launcher=0','PrependPath=0','Shortcuts=0','AssociateFiles=0','Include_test=0',('TargetDir="'+$target+'"')) -Wait -PassThru -WindowStyle Hidden
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
