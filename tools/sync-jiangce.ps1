param([switch]$Publish,[string]$SnapshotDate=(Get-Date -Format yyyyMMdd))
$ErrorActionPreference='Stop'
if($SnapshotDate -notmatch '^\d{8}$'){throw 'SnapshotDate must be yyyyMMdd'}
$repo=Split-Path $PSScriptRoot -Parent
Push-Location $repo
try {
    $python=Join-Path $repo '.venv\Scripts\python.exe'
    $archive=Join-Path $repo ".research\jiangce\$SnapshotDate"
    $channel=Join-Path $repo '.research\jiangce\channel'
    function Invoke-Step([string[]]$Arguments){
        & $python -X utf8 @Arguments
        if($LASTEXITCODE -ne 0){throw "Step failed: $($Arguments[0])"}
    }
    Invoke-Step -Arguments @('tools/sync_jiangce.py',$archive)
    Invoke-Step -Arguments @('tools/build_jiangce.py',$archive,"$archive\guides.sqlite")
    Invoke-Step -Arguments @('tools/prepare_jiangce.py',"$archive\guides.sqlite",$channel)
    if($Publish){
        $failures=@()
        foreach($hostName in @('GitHub','Gitee')){
            try {Invoke-Step -Arguments @('tools/publish_jiangce.py',$channel,$hostName)}
            catch {$failures+=$hostName}
        }
        if($failures){throw "Data channel needs retry: $($failures -join ', ')"}
    }
} finally {Pop-Location}

