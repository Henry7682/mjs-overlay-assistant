param([switch]$SkipUpdate)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'release\Release.ps1')
Assert-Platform
$homePath=$PSScriptRoot;$statePath=Join-Path $homePath 'current.json'
if (-not (Test-Path -LiteralPath $statePath)) { throw 'Run download.cmd to prepare the installation.' }
$dataPath=Join-Path $homePath 'data';[IO.Directory]::CreateDirectory($dataPath)|Out-Null
$env:MJS_ASSISTANT_HOME=$dataPath
$state=Get-Content -Raw -LiteralPath $statePath|ConvertFrom-Json
Assert-Version $state.version
$exe=Join-Path $homePath ('versions\'+$state.version+'\MjsOverlay.exe')
$versionsRoot=[IO.Path]::GetFullPath((Join-Path $homePath 'versions')).TrimEnd('\')+'\'
$running=Get-Process -Name MjsOverlay -ErrorAction SilentlyContinue|Where-Object { $_.Path -and $_.Path.StartsWith($versionsRoot,[StringComparison]::OrdinalIgnoreCase) }|Select-Object -First 1
if ($running) { Start-Process -FilePath $running.Path -WindowStyle Hidden;exit 0 }
$sha=[Security.Cryptography.SHA256]::Create()
try { $suffix=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($homePath.ToLowerInvariant())))).Replace('-','') } finally { $sha.Dispose() }
$mutex=New-Object Threading.Mutex($false,('Local\MjsOverlayUpdate-'+$suffix))
$owns=$false
try { $owns=$mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owns=$true }
if (-not $owns) { $mutex.Dispose();Write-Host 'Another launch is preparing an update.';exit 0 }
$pendingPath=Join-Path $homePath 'pending-update.json'
$ready=$null
try {
    # Recover an interrupted update before running either version. Never silently
    # continue with a half-restored configuration.
    if (Test-Path -LiteralPath $pendingPath) {
        $pending=Get-Content -Raw -LiteralPath $pendingPath|ConvertFrom-Json
        if ($state.version -ne $pending.version) {
            Restore-UserData $homePath $pending.backup
            Write-AtomicJson (Join-Path $homePath 'failed-update.json') @{version=$pending.version;reason='interrupted startup'}
        }
        Remove-Item -LiteralPath $pendingPath
    }
    $candidate=$null;$manifest=$null
    if (-not $SkipUpdate) {
        try {
            Write-Host 'Checking update before startup (S: skip).'
            $manifest=Read-Release 'Auto' (Join-Path $homePath 'release\public-key.xml')
            $failed=Join-Path $homePath 'failed-update.json'
            $blocked=if(Test-Path -LiteralPath $failed){Get-Content -Raw -LiteralPath $failed|ConvertFrom-Json}else{$null}
            if ([version]$manifest.version -gt [version]$state.version -and (-not $blocked -or $blocked.version -ne $manifest.version)) {
                Write-Host ('Downloading '+$manifest.version+'. Press S to use current version.')
                $archive=Get-AssetFile $manifest.assets.portable (Join-Path $homePath 'download-cache') 'Auto' '' ([datetime]::UtcNow.AddSeconds(180))
                $target=Join-Path $homePath ('versions\'+$manifest.version)
                if (-not (Test-Path -LiteralPath $target)) { Expand-VerifiedZip $archive $target }
                Assert-Payload $archive $target
                $candidate=Join-Path $target 'MjsOverlay.exe'
                if (-not (Test-Path -LiteralPath $candidate)) { throw 'New program missing.' }
            }
        } catch { $candidate=$null;Write-Host ('Update unavailable; using installed version. '+$_.Exception.Message) }
    }
    if ($candidate) {
        $backup=Save-UserData $homePath
        Write-AtomicJson $pendingPath @{version=$manifest.version;backup=$backup}
        $ready=Join-Path $dataPath ('ready-'+[guid]::NewGuid().ToString('N')+'.txt');$env:MJS_READY_FILE=$ready
        $process=$null;$success=$false
        try {
            $process=Start-Process -FilePath $candidate -PassThru -WindowStyle Hidden
            $watch=[Diagnostics.Stopwatch]::StartNew()
            while (-not (Test-Path -LiteralPath $ready) -and -not $process.HasExited -and $watch.Elapsed.TotalSeconds -lt 60) { Start-Sleep -Milliseconds 200 }
            $success=(Test-Path -LiteralPath $ready) -and -not $process.HasExited -and ([IO.File]::ReadAllText($ready) -eq $manifest.version)
        } catch { Write-Host ('New version failed: '+$_.Exception.Message) }
        if ($success) {
            try { Write-AtomicJson $statePath @{version=$manifest.version;previous=$state.version} }
            catch { $success=$false;Write-Host ('Could not commit update: '+$_.Exception.Message) }
        }
        if ($success) {
            Remove-Item -LiteralPath $pendingPath
        } else {
            if ($process -and -not $process.HasExited) { $process.Kill();$process.WaitForExit(3000)|Out-Null }
            Restore-UserData $homePath $backup
            Write-AtomicJson (Join-Path $homePath 'failed-update.json') @{version=$manifest.version;reason='startup handshake failed'}
            Remove-Item -LiteralPath $pendingPath
            Remove-Item Env:MJS_READY_FILE -ErrorAction SilentlyContinue
            Start-Process -FilePath $exe -WindowStyle Hidden
            Write-Host 'New version did not start. Previous version and data restored.'
        }
    } else { Start-Process -FilePath $exe -WindowStyle Hidden }
} finally {
    if ($ready) { Remove-Item -LiteralPath $ready -ErrorAction SilentlyContinue }
    Remove-Item Env:MJS_READY_FILE -ErrorAction SilentlyContinue
    $mutex.ReleaseMutex();$mutex.Dispose()
}
