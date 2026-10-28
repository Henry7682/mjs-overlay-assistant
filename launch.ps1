param([switch]$SkipUpdate)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'release\Release.ps1')
Assert-Platform
$homePath=$PSScriptRoot;$statePath=Join-Path $homePath 'current.json'
if (-not (Test-Path $statePath)) { throw 'Run download.cmd to prepare the versioned installation.' }
$dataPath=Join-Path $homePath 'data';[IO.Directory]::CreateDirectory($dataPath)|Out-Null
$env:MJS_ASSISTANT_HOME=$dataPath
$state=Get-Content -Raw $statePath|ConvertFrom-Json
$exe=Join-Path $homePath ('versions\'+$state.version+'\MjsOverlay.exe')
# Let the application's single-instance channel open Settings without a new update.
$running=Get-Process -Name MjsOverlay -ErrorAction SilentlyContinue|Where-Object { $_.Path -eq $exe }
if ($running) { Start-Process -FilePath $exe -WindowStyle Hidden;exit 0 }
$mutex=New-Object Threading.Mutex($false,('Local\MjsOverlayUpdate-'+([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($homePath))).Replace('/','_')))
if (-not $mutex.WaitOne(0)) { Write-Host 'Another launch is preparing an update.';exit 0 }
$changed=$false;$backup=$null
try {
    if (-not $SkipUpdate) {
        try {
            Write-Host 'Checking update before startup (S: skip).'
            $manifest=Read-Release 'Auto' (Join-Path $homePath 'release\public-key.xml')
            $failed=Join-Path $homePath 'failed-update.json'
            $blocked=if(Test-Path $failed){Get-Content -Raw $failed|ConvertFrom-Json}else{$null}
            if ([version]$manifest.version -gt [version]$state.version -and (-not $blocked -or $blocked.version -ne $manifest.version)) {
                Write-Host ('Downloading '+$manifest.version+'. Press S to use current version.')
                $archive=Get-AssetFile $manifest.assets.portable (Join-Path $homePath 'download-cache') 'Auto' '' ([datetime]::UtcNow.AddSeconds(180))
                $target=Join-Path $homePath ('versions\'+$manifest.version)
                if (-not (Test-Path $target)) { Expand-VerifiedZip $archive $target }
                if (-not (Test-Path (Join-Path $target 'MjsOverlay.exe'))) { throw 'New program missing.' }
                $backup=Join-Path $homePath ('update-backups\'+[guid]::NewGuid().ToString('N'))
                [IO.Directory]::CreateDirectory($backup)|Out-Null
                foreach ($name in @('settings.json','boards')) { $p=Join-Path $dataPath $name;if(Test-Path $p){Copy-Item -LiteralPath $p -Destination $backup -Recurse} }
                $state=@{version=$manifest.version;previous=$state.version}
                Write-AtomicJson $statePath $state;$changed=$true
                $exe=Join-Path $target 'MjsOverlay.exe'
            }
        } catch { Write-Host ('Update unavailable; using installed version. '+$_.Exception.Message) }
    }
    $ready=Join-Path $dataPath ('ready-'+[guid]::NewGuid().ToString('N')+'.txt');$env:MJS_READY_FILE=$ready
    $process=Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
    if ($changed) {
        $watch=[Diagnostics.Stopwatch]::StartNew()
        while (-not (Test-Path $ready) -and -not $process.HasExited -and $watch.Elapsed.TotalSeconds -lt 60) { Start-Sleep -Milliseconds 200 }
        if (-not (Test-Path $ready)) {
            if (-not $process.HasExited) { $process.Kill();$process.WaitForExit(3000)|Out-Null }
            Write-AtomicJson (Join-Path $homePath 'failed-update.json') @{version=$state.version;reason='startup handshake failed'}
            foreach ($name in @('settings.json','boards')) {
                $p=Join-Path $backup $name
                if (Test-Path $p) { Copy-Item -LiteralPath $p -Destination $dataPath -Recurse -Force }
            }
            Write-AtomicJson $statePath @{version=$state.previous;previous=$null}
            Remove-Item Env:MJS_READY_FILE -ErrorAction SilentlyContinue
            Start-Process -FilePath (Join-Path $homePath ('versions\'+$state.previous+'\MjsOverlay.exe')) -WindowStyle Hidden
            Write-Host 'New version did not start. Previous version restored.'
        }
    }
    Remove-Item -LiteralPath $ready -ErrorAction SilentlyContinue
} finally { Remove-Item Env:MJS_READY_FILE -ErrorAction SilentlyContinue;$mutex.ReleaseMutex();$mutex.Dispose() }
