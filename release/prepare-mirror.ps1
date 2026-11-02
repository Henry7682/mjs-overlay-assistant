param(
    [Parameter(Mandatory=$true)][string]$Manifest,
    [Parameter(Mandatory=$true)][string]$AssetsDirectory,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$HistoryDirectory='',
    [string]$KeyPath=(Join-Path $PSScriptRoot 'public-key.xml')
)
# Prepare a NEW upload directory. Never sign, upload or overwrite published files.
. (Join-Path $PSScriptRoot 'Release.ps1')
$Manifest=[IO.Path]::GetFullPath($Manifest)
$signature=[IO.Path]::ChangeExtension($Manifest,'.sig')
$bytes=[IO.File]::ReadAllBytes($Manifest)
Assert-Signature $bytes ([IO.File]::ReadAllText($signature)) $KeyPath
$m=[Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json
Assert-Version $m.version
if($m.schema_version -ne 1 -or $m.channel -ne 'stable' -or $m.minimum_launcher -gt 1){throw 'Unsupported manifest'}
if(Test-Path -LiteralPath $OutputDirectory){throw 'Output directory must be new'}
$files=@{}
foreach($role in @('portable','source','models','wheels','downloader')){
    $asset=$m.assets.$role
    if($asset.bytes -le 90000000){$rows=@($asset)}else{$rows=@($asset.parts)}
    if(-not $rows.Count){throw ('Missing split assets: '+$role)}
    foreach($row in $rows){
        if($row.name -notmatch '^[A-Za-z0-9_.-]+$' -or $row.bytes -gt 90000000){throw 'Invalid mirror filename/size'}
        $path=Join-Path $AssetsDirectory $row.name
        Assert-Hash $path $row
        $files[$row.name]=$path
    }
}
# Validate history conflicts BEFORE writing. History is byte-preserving and
# immutable; a later manifest with extra URLs must not replace earlier history.
if($HistoryDirectory){
    foreach($suffix in @('json','sig')){
        $source=if($suffix -eq 'json'){$Manifest}else{$signature}
        $target=Join-Path $HistoryDirectory ($m.version+'.'+$suffix)
        if((Test-Path -LiteralPath $target) -and (Get-Sha256 $target) -ne (Get-Sha256 $source)){throw 'Signed history already exists with different bytes'}
    }
}
[IO.Directory]::CreateDirectory($OutputDirectory)|Out-Null
foreach($name in $files.Keys){Copy-Item -LiteralPath $files[$name] -Destination (Join-Path $OutputDirectory $name)}
Copy-Item -LiteralPath $Manifest -Destination (Join-Path $OutputDirectory 'release.json')
Copy-Item -LiteralPath $signature -Destination (Join-Path $OutputDirectory 'release.sig')
if($HistoryDirectory){
    [IO.Directory]::CreateDirectory($HistoryDirectory)|Out-Null
    foreach($suffix in @('json','sig')){
        $source=if($suffix -eq 'json'){$Manifest}else{$signature}
        $target=Join-Path $HistoryDirectory ($m.version+'.'+$suffix)
        if(-not(Test-Path -LiteralPath $target)){Copy-Item -LiteralPath $source -Destination $target}
    }
}
Write-Host ('Prepared '+($files.Count+2)+' files for Gitee '+$m.version+'. Anonymous verification is still required.')
