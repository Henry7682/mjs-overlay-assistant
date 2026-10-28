# Shared by download.ps1 and the portable launcher. Windows PowerShell 5.1.
Set-StrictMode -Version 2
$ErrorActionPreference='Stop'
$script:ReleaseOwner='Henry7682/mjs-overlay-assistant'
$script:MirrorOwner='henry7682/mjs-overlay-assistant'
$script:UpdateSkipped=$false
function Assert-Platform {
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Only Windows x64 is supported.' }
    if (-not [Environment]::Is64BitProcess) { throw 'Please use 64-bit Windows PowerShell.' }
    [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
}
function Get-DependencyStatus {
    $runtime=[Microsoft.Win32.Registry]::LocalMachine.OpenSubKey('SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64')
    try { $installed=$runtime -and $runtime.GetValue('Installed',0) -eq 1 } finally { if($runtime){$runtime.Dispose()} }
    return [pscustomobject]@{Windows64=[Environment]::Is64BitOperatingSystem;PowerShell=$PSVersionTable.PSVersion.ToString();VCRuntime=$installed;
        SteamRunning=[bool](Get-Process -Name steam -ErrorAction SilentlyContinue);
        WeChatRunning=[bool](Get-Process -Name WeChat,Weixin -ErrorAction SilentlyContinue)}
}
function Assert-Publisher([string]$Path,[string]$Publisher) {
    Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
    $signature=Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch $Publisher) { throw 'Installer publisher signature rejected.' }
}
function Test-Cancel {
    try { if ([Console]::KeyAvailable) { if ([Console]::ReadKey($true).Key -eq 'S') { $script:UpdateSkipped=$true } } } catch {}
    if ($script:UpdateSkipped) { throw 'Skipped by user.' }
}
function Get-Sha256([string]$Path) {
    $stream=[IO.File]::OpenRead($Path);$sha=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose();$sha.Dispose() }
}
function Assert-Hash([string]$Path,$Asset) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'Download missing.' }
    if ((Get-Item -LiteralPath $Path).Length -ne [long]$Asset.bytes -or (Get-Sha256 $Path) -ne $Asset.sha256) { throw 'File size / SHA256 mismatch.' }
}
function Assert-Signature([byte[]]$Bytes,[string]$Signature,[string]$KeyPath) {
    $rsa=New-Object Security.Cryptography.RSACryptoServiceProvider
    $rsa.PersistKeyInCsp=$false
    try {
        $rsa.FromXmlString([IO.File]::ReadAllText($KeyPath))
        if ($rsa.KeySize -ne 3072 -or -not $rsa.VerifyData($Bytes,'SHA256',[Convert]::FromBase64String($Signature.Trim()))) { throw 'Release signature rejected.' }
    } finally { $rsa.Dispose() }
}
function Get-RemoteBytes([string]$Url,[int]$Timeout=5000,[int]$Limit=1048576) {
    if (-not $Url.StartsWith('https://')) { throw 'HTTPS required.' }
    $request=[Net.HttpWebRequest]::Create($Url);$request.Timeout=$Timeout;$request.ReadWriteTimeout=$Timeout
    $request.UserAgent='MjsOverlay/1.0.0';$request.AllowAutoRedirect=$true
    $watch=[Diagnostics.Stopwatch]::StartNew();$response=$request.GetResponse()
    try {
        if ($response.ResponseUri.Scheme -ne 'https') { throw 'Insecure redirect.' }
        $stream=$response.GetResponseStream();$memory=New-Object IO.MemoryStream;$buffer=New-Object byte[] 16384
        try {
            while ($true) {
                $left=$Timeout-[int]$watch.ElapsedMilliseconds
                if ($left -le 0) { throw 'Metadata time budget exceeded.' }
                if ($stream.CanTimeout) { $stream.ReadTimeout=$left }
                $count=$stream.Read($buffer,0,$buffer.Length)
                if ($count -le 0) { break }
                $memory.Write($buffer,0,$count);if ($memory.Length -gt $Limit) { throw 'Metadata too large.' }
            }
            return ,$memory.ToArray()
        }
        finally { $stream.Dispose();$memory.Dispose() }
    } finally { $response.Dispose() }
}
function Read-Release([string]$Source,[string]$KeyPath,[string]$OfflineDirectory='') {
    if ($OfflineDirectory) {
        $path=Join-Path $OfflineDirectory 'release.json';$bytes=[IO.File]::ReadAllBytes($path)
        Assert-Signature $bytes ([IO.File]::ReadAllText((Join-Path $OfflineDirectory 'release.sig'))) $KeyPath
        $manifest=[Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json
    } else {
        $origins=@()
        if ($Source -in @('Auto','GitHub')) { $origins+='https://raw.githubusercontent.com/'+$script:ReleaseOwner+'/main/release.json' }
        if ($Source -in @('Auto','Gitee')) { $origins+='https://gitee.com/'+$script:MirrorOwner+'/raw/main/release.json' }
        $timer=[Diagnostics.Stopwatch]::StartNew();$found=@()
        foreach ($url in $origins) {
            Test-Cancel
            $left=8000-[int]$timer.ElapsedMilliseconds
            if ($left -le 0) { break }
            try {
                $bytes=Get-RemoteBytes $url ([Math]::Min(3500,$left))
                $left=8000-[int]$timer.ElapsedMilliseconds;if ($left -le 0) { break }
                $sig=[Text.Encoding]::UTF8.GetString((Get-RemoteBytes ($url -replace '\.json$','.sig') ([Math]::Min(2500,$left))))
                Assert-Signature $bytes $sig $KeyPath
                $m=[Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json
                if ($m.schema_version -eq 1 -and $m.channel -eq 'stable' -and $m.version -match '^\d+\.\d+\.\d+$') { $found+=,$m }
            } catch { Write-Host ('Source unavailable: '+$url+' ('+$_.Exception.Message+')') }
        }
        if (-not $found) { throw 'No verified release source available.' }
        $manifest=$found|Sort-Object {[version]$_.version} -Descending|Select-Object -First 1
    }
    if ($manifest.schema_version -ne 1 -or $manifest.channel -ne 'stable' -or $manifest.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Unsupported manifest.' }
    if ($manifest.minimum_launcher -gt 1) { throw 'Please download a new complete launcher.' }
    return $manifest
}
function Get-AssetFile($Asset,[string]$Directory,[string]$Source='Auto',[string]$OfflineDirectory='',[datetime]$Deadline=([datetime]::UtcNow.AddSeconds(180))) {
    if ($Asset.name -notmatch '^[A-Za-z0-9_.-]+$' -or $Asset.sha256 -notmatch '^[a-f0-9]{64}$' -or $Asset.bytes -le 0 -or $Asset.bytes -gt 2000000000) { throw 'Invalid asset manifest.' }
    [IO.Directory]::CreateDirectory($Directory)|Out-Null;$target=Join-Path $Directory $Asset.name
    if (Test-Path -LiteralPath $target) { try { Assert-Hash $target $Asset;return $target } catch { Remove-Item -LiteralPath $target } }
    if ($OfflineDirectory) {
        $local=Join-Path $OfflineDirectory $Asset.name
        if (Test-Path -LiteralPath $local) { Copy-Item -LiteralPath $local -Destination $target;Assert-Hash $target $Asset;return $target }
    }
    $urls=@($Asset.urls|Where-Object { $Source -eq 'Auto' -or ($Source -eq 'GitHub' -and $_ -match '^https://(github.com|objects.githubusercontent.com)/') -or ($Source -eq 'Gitee' -and $_ -match '^https://gitee.com/') })
    if (-not $OfflineDirectory) {
        for ($attempt=0;$attempt -lt 2;$attempt++) {
            foreach ($url in $urls) {
                try { Receive-File $url $target $Asset $Deadline;return $target } catch { Write-Host $_.Exception.Message;Test-Cancel }
                if ([datetime]::UtcNow -ge $Deadline) { throw 'Download time budget exceeded.' }
            }
        }
    }
    if ($Asset.PSObject.Properties['parts'] -and $Asset.parts.Count) {
        $partials=@()
        foreach ($part in $Asset.parts) { $partials+=Get-AssetFile $part $Directory $Source $OfflineDirectory $Deadline }
        $output=[IO.File]::Create($target)
        try { foreach ($p in $partials) { $input=[IO.File]::OpenRead($p);try { $input.CopyTo($output) } finally { $input.Dispose() } } } finally { $output.Dispose() }
        Assert-Hash $target $Asset;return $target
    }
    throw ('Unable to obtain verified asset: '+$Asset.name)
}
function Receive-File([string]$Url,[string]$Target,$Asset,[datetime]$Deadline) {
    Test-Cancel
    if ([datetime]::UtcNow -ge $Deadline) { throw 'Download time budget exceeded.' }
    if (-not $Url.StartsWith('https://')) { throw 'HTTPS required.' }
    $partial=$Target+'.partial';$etagFile=$partial+'.json';$offset=0;$etag=$null
    if ((Test-Path $partial) -and (Test-Path $etagFile)) {
        $info=Get-Content -Raw -LiteralPath $etagFile|ConvertFrom-Json
        if ($info.url -eq $Url -and $info.hash -eq $Asset.sha256 -and $info.etag) { $offset=(Get-Item $partial).Length;$etag=$info.etag }
    }
    if ($offset -ge $Asset.bytes) { $offset=0 }
    $remaining=[Math]::Max(1,[int]($Deadline-[datetime]::UtcNow).TotalMilliseconds)
    $request=[Net.HttpWebRequest]::Create($Url);$request.Timeout=[Math]::Min(5000,$remaining);$request.ReadWriteTimeout=[Math]::Min(15000,$remaining);$request.UserAgent='MjsOverlay/1.0.0'
    if ($offset -gt 0) { $request.AddRange($offset);$request.Headers['If-Range']=$etag }
    $response=$request.GetResponse()
    try {
        if ($response.ResponseUri.Scheme -ne 'https' -or $response.ContentType -match 'text/html') { throw 'Rejected non-file response.' }
        if ($offset -gt 0 -and ([int]$response.StatusCode -ne 206 -or $response.Headers['ETag'] -ne $etag -or $response.Headers['Content-Range'] -notmatch ('^bytes '+$offset+'-'))) { $offset=0 }
        if ([int]$response.StatusCode -eq 206 -and $offset -eq 0) { throw 'Unexpected partial response.' }
        @{url=$Url;hash=$Asset.sha256;etag=$response.Headers['ETag']}|ConvertTo-Json|Set-Content -LiteralPath $etagFile -Encoding UTF8
        $mode=[IO.FileMode]::Create;if ($offset -gt 0) { $mode=[IO.FileMode]::Append }
        $output=[IO.File]::Open($partial,$mode);$stream=$response.GetResponseStream();$buffer=New-Object byte[] 65536
        try {
            while ($true) {
                Test-Cancel;$remaining=[int]($Deadline-[datetime]::UtcNow).TotalMilliseconds
                if ($remaining -le 0) { throw 'Download time budget exceeded.' }
                if ($stream.CanTimeout) { $stream.ReadTimeout=[Math]::Min(15000,$remaining) }
                $count=$stream.Read($buffer,0,$buffer.Length);if($count -le 0){break}
                $output.Write($buffer,0,$count);$offset+=$count
                if ($offset -gt $Asset.bytes) { throw 'Download exceeds declared size.' }
                Write-Progress -Activity $Asset.name -Status 'S: skip / cancel' -PercentComplete ([Math]::Min(100,100*$offset/$Asset.bytes))
            }
        } finally { $stream.Dispose();$output.Dispose();Write-Progress -Activity $Asset.name -Completed }
    } finally { $response.Dispose() }
    try { Assert-Hash $partial $Asset } catch { Remove-Item -LiteralPath $partial -ErrorAction SilentlyContinue;throw }
    Move-Item -LiteralPath $partial -Destination $Target;Remove-Item -LiteralPath $etagFile -ErrorAction SilentlyContinue
}
function Expand-VerifiedZip([string]$Archive,[string]$Destination) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $root=[IO.Path]::GetFullPath($Destination).TrimEnd('\')+'\'
    if (Test-Path -LiteralPath $Destination) { throw 'Extraction destination must not exist.' }
    $zip=[IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $total=0L;$seen=@{}
        foreach ($entry in $zip.Entries) {
            $name=$entry.FullName.Replace('/','\');$total+=$entry.Length
            if ($total -gt 2000000000 -or $zip.Entries.Count -gt 20000) { throw 'Archive too large.' }
            if ($name.StartsWith('\') -or $name -match ':' -or (($entry.ExternalAttributes -shr 16) -band 61440) -eq 40960) { throw 'Unsafe archive entry.' }
            foreach ($part in $name.TrimEnd('\').Split('\')) {
                if ($part -in @('.','..','') -or $part.TrimEnd(' ','.') -ne $part -or $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)') { throw 'Unsafe archive name.' }
            }
            $target=[IO.Path]::GetFullPath((Join-Path $Destination $name))
            if (-not $target.StartsWith($root,[StringComparison]::OrdinalIgnoreCase) -or $seen.ContainsKey($target)) { throw 'Archive path escaped / duplicated.' }
            $seen[$target]=$true
        }
        [IO.Directory]::CreateDirectory($Destination)|Out-Null
        foreach ($entry in $zip.Entries) {
            $target=Join-Path $Destination $entry.FullName
            if ($entry.FullName.EndsWith('/')) { [IO.Directory]::CreateDirectory($target)|Out-Null;continue }
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))|Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$target,$false)
        }
    } finally { $zip.Dispose() }
}
function Write-AtomicJson([string]$Path,$Value) {
    $temp=$Path+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
    [IO.File]::WriteAllText($temp,($Value|ConvertTo-Json -Depth 30),(New-Object Text.UTF8Encoding($false)))
    try {
        if (Test-Path -LiteralPath $Path) {
            # PowerShell 5.1 marshals $null to an empty string for this overload.
            $previous=$Path+'.'+[guid]::NewGuid().ToString('N')+'.old'
            [IO.File]::Replace($temp,$Path,$previous)
            Remove-Item -LiteralPath $previous -ErrorAction SilentlyContinue
        } else { [IO.File]::Move($temp,$Path) }
    } finally { Remove-Item -LiteralPath $temp -ErrorAction SilentlyContinue }
}

function Assert-Version([string]$Version) {
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid version path.' }
}
function Assert-Payload([string]$Archive,[string]$Directory) {
    # Existing version folders are not trusted solely because the name matches.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $root=[IO.Path]::GetFullPath($Directory).TrimEnd('\')+'\'
    $zip=[IO.Compression.ZipFile]::OpenRead($Archive);$names=@{}
    try {
        foreach ($entry in $zip.Entries) {
            if ($entry.FullName.EndsWith('/')) { continue }
            $path=[IO.Path]::GetFullPath((Join-Path $Directory $entry.FullName))
            if (-not $path.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe payload path.' }
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Incomplete existing payload.' }
            if ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked payload file.' }
            $stream=$entry.Open();$sha=[Security.Cryptography.SHA256]::Create()
            try { $expected=([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
            finally { $stream.Dispose();$sha.Dispose() }
            if ((Get-Sha256 $path) -ne $expected) { throw 'Existing version differs from verified asset. Choose a new installation directory.' }
            $names[$path]=$true
        }
        foreach ($file in Get-ChildItem -LiteralPath $Directory -Recurse -File) {
            if (-not $names.ContainsKey($file.FullName)) { throw 'Unexpected file in immutable version directory.' }
        }
    } finally { $zip.Dispose() }
}
function Save-UserData([string]$Root) {
    $backup=Join-Path $Root ('update-backups\'+[guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($backup)|Out-Null
    foreach ($name in @('settings.json','boards')) {
        $p=Join-Path (Join-Path $Root 'data') $name
        if (Test-Path -LiteralPath $p) { Copy-Item -LiteralPath $p -Destination $backup -Recurse }
    }
    return $backup
}
function Restore-UserData([string]$Root,[string]$Backup) {
    $rootPath=[IO.Path]::GetFullPath($Root).TrimEnd('\')+'\'
    $backupPath=[IO.Path]::GetFullPath($Backup)
    if (-not $backupPath.StartsWith($rootPath+'update-backups\',[StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $backupPath -PathType Container)) { throw 'Invalid rollback backup.' }
    $savedFailed=Join-Path $backupPath ('failed-data-'+[guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($savedFailed)|Out-Null
    foreach ($name in @('settings.json','boards')) {
        $current=[IO.Path]::GetFullPath((Join-Path (Join-Path $Root 'data') $name))
        if (-not $current.StartsWith($rootPath+'data\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Rollback path escaped.' }
        if (Test-Path -LiteralPath $current) { Move-Item -LiteralPath $current -Destination $savedFailed }
        $old=Join-Path $backupPath $name
        if (Test-Path -LiteralPath $old) { Copy-Item -LiteralPath $old -Destination (Join-Path $Root 'data') -Recurse }
    }
}
