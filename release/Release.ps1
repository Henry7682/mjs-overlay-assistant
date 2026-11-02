# Shared by download.ps1 and the portable launcher. Windows PowerShell 5.1.
# MJS_DOWNLOAD_LIBRARY: 3
Set-StrictMode -Version 2
$ErrorActionPreference='Stop'
$script:ReleaseOwner='Henry7682/mjs-overlay-assistant'
$script:MirrorOwner='henry7682/mjs-overlay-assistant'
$script:UpdateSkipped=$false
$script:ReleaseLog=$null
function Set-ReleaseLog([string]$Path) {
    try { [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))|Out-Null;$script:ReleaseLog=$Path } catch { $script:ReleaseLog=$null }
}
function Write-ReleaseEvent([string]$Stage,[string]$Status,[string]$Source='',[string]$Version='') {
    if (-not $script:ReleaseLog) { return }
    try {
        $origin='';if ($Source) { $origin=([uri]$Source).Host }
        $row=@{schema_version=1;event='release';time=[datetime]::UtcNow.ToString('o');stage=$Stage;status=$Status;source=$origin;version=$Version}|ConvertTo-Json -Compress
        $encoding=New-Object Text.UTF8Encoding($false);$bytes=$encoding.GetByteCount($row)+2
        if ((Test-Path -LiteralPath $script:ReleaseLog) -and (Get-Item -LiteralPath $script:ReleaseLog).Length+$bytes -gt 1000000) {
            for ($i=4;$i -ge 1;$i--) {
                $old=if($i -eq 1){$script:ReleaseLog}else{$script:ReleaseLog+'.'+($i-1)}
                $next=$script:ReleaseLog+'.'+$i
                if(Test-Path -LiteralPath $next){Remove-Item -LiteralPath $next}
                if(Test-Path -LiteralPath $old){Move-Item -LiteralPath $old -Destination $next}
            }
        }
        [IO.File]::AppendAllText($script:ReleaseLog,$row+"`r`n",$encoding)
    } catch {} # Logging cannot stop installation or the usable previous version.
}
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
function Read-Release([string]$Source,[string]$KeyPath,[string]$OfflineDirectory='',[switch]$All) {
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
            # Reserve a metadata slot for the other origin, including its signature.
            $slotEnd=[Math]::Min(8000,$timer.ElapsedMilliseconds+[int](8000/$origins.Count))
            try {
                $bytes=Get-RemoteBytes $url ([Math]::Min(2500,$left))
                $left=[int]($slotEnd-$timer.ElapsedMilliseconds);if ($left -le 0) { throw 'Metadata source time budget exceeded.' }
                $sig=[Text.Encoding]::UTF8.GetString((Get-RemoteBytes ($url -replace '\.json$','.sig') ([Math]::Min(2500,$left))))
                Assert-Signature $bytes $sig $KeyPath
                $m=[Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json
                if ($m.schema_version -eq 1 -and $m.channel -eq 'stable' -and $m.version -match '^\d+\.\d+\.\d+$') {
                    $m|Add-Member -NotePropertyName discovery_source -NotePropertyValue $(if($url -match '^https://gitee.com/'){'Gitee'}else{'GitHub'}) -Force
                    $found+=,$m
                }
                Write-ReleaseEvent 'metadata' 'verified' $url $m.version
            } catch { Write-ReleaseEvent 'metadata' 'unavailable' $url;Write-Host ('Source unavailable: '+$url+' ('+$_.Exception.Message+')') }
        }
        if (-not $found) { throw 'No verified release source available.' }
        if ($All) { return @($found|Where-Object {$_.minimum_launcher -le 1}) }
        $latest=$found|Sort-Object {[version]$_.version} -Descending|Select-Object -First 1
        $manifest=@($found|Where-Object {$_.version -eq $latest.version})[0]
        # Same-version signed mirror metadata may arrive before GitHub is synced.
        # Only union locations of byte-identical assets; never mix versions/content.
        foreach ($other in $found) {
            if ($other.version -ne $manifest.version -or $other.minimum_launcher -ne $manifest.minimum_launcher) { continue }
            if (-not $manifest.PSObject.Properties['assets'] -or -not $other.PSObject.Properties['assets']) { continue }
            foreach ($role in $manifest.assets.PSObject.Properties.Name) {
                if ($other.assets.PSObject.Properties[$role]) { Merge-AssetLocations $manifest.assets.$role $other.assets.$role }
            }
        }
    }
    if ($manifest.schema_version -ne 1 -or $manifest.channel -ne 'stable' -or $manifest.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Unsupported manifest.' }
    if ($manifest.minimum_launcher -gt 1) { throw 'Please download a new complete launcher.' }
    return $manifest
}
function Merge-AssetLocations($Asset,$Other) {
    if ($Asset.name -ne $Other.name -or $Asset.bytes -ne $Other.bytes -or $Asset.sha256 -ne $Other.sha256) { return }
    $Asset.urls=@(@($Asset.urls)+@($Other.urls)|Select-Object -Unique)
    if ($Other.PSObject.Properties['parts'] -and $Other.parts.Count) {
        if (-not $Asset.PSObject.Properties['parts'] -or -not $Asset.parts.Count) {
            $Asset|Add-Member -NotePropertyName parts -NotePropertyValue $Other.parts -Force
        } elseif ($Asset.parts.Count -eq $Other.parts.Count) {
            for ($i=0;$i -lt $Asset.parts.Count;$i++) { Merge-AssetLocations $Asset.parts[$i] $Other.parts[$i] }
        }
    }
}
function Get-SourceUrls($Asset,[string]$Source) {
    @($Asset.urls|Where-Object { $Source -eq 'Auto' -or ($Source -eq 'GitHub' -and $_ -match '^https://(github\.com|objects\.githubusercontent\.com)/') -or ($Source -eq 'Gitee' -and $_ -match '^https://gitee\.com/') }|Select-Object -Unique)
}
function Test-SlowTransfer([double]$Seconds,[long]$Received,[long]$Remaining) {
    # Grace period and a minimum remaining size prevent switching a tiny/nearly
    # finished file. Rate is based on this request, not previous resumed bytes.
    return $Seconds -ge 8 -and $Remaining -gt 1MB -and ($Received/[Math]::Max(1,$Seconds)) -lt 256KB
}
function New-DownloadRequest([string]$Url) { return [Net.HttpWebRequest]::Create($Url) }
function Get-AssetFile($Asset,[string]$Directory,[string]$Source='Auto',[string]$OfflineDirectory='',[datetime]$Deadline=([datetime]::UtcNow.AddSeconds(180)),[switch]$FallbackAvailable) {
    if ($Asset.name -notmatch '^[A-Za-z0-9_.-]+$' -or $Asset.sha256 -notmatch '^[a-f0-9]{64}$' -or $Asset.bytes -le 0 -or $Asset.bytes -gt 2000000000) { throw 'Invalid asset manifest.' }
    [IO.Directory]::CreateDirectory($Directory)|Out-Null;$target=Join-Path $Directory $Asset.name
    if (Test-Path -LiteralPath $target) { try { Assert-Hash $target $Asset;return $target } catch { Remove-Item -LiteralPath $target } }
    if ($OfflineDirectory) {
        $local=Join-Path $OfflineDirectory $Asset.name
        if (Test-Path -LiteralPath $local) { Copy-Item -LiteralPath $local -Destination $target;Assert-Hash $target $Asset;return $target }
    }
    $routes=@()
    if (-not $OfflineDirectory) { foreach ($url in @(Get-SourceUrls $Asset $Source)) { $routes+=,[pscustomobject]@{url=$url;parts=$false} } }
    if ($Asset.PSObject.Properties['parts'] -and $Asset.parts.Count) {
        $available=$true
        foreach ($part in $Asset.parts) {
            if (-not $OfflineDirectory -and -not @(Get-SourceUrls $part $Source).Count) { $available=$false }
        }
        if ($available) { $routes+=,[pscustomobject]@{url='';parts=$true} }
    }
    # Try every distinct route (including Gitee parts) BEFORE retrying GitHub.
    for ($attempt=0;$attempt -lt 2;$attempt++) {
        for ($routeIndex=0;$routeIndex -lt $routes.Count;$routeIndex++) {
            Test-Cancel
            if ([datetime]::UtcNow -ge $Deadline) { throw 'Download time budget exceeded.' }
            $route=$routes[$routeIndex];$alternative=($routeIndex -lt $routes.Count-1) -or $FallbackAvailable
            $routeDeadline=$Deadline
            if ($alternative) {
                $seconds=[Math]::Min(45,($Deadline-[datetime]::UtcNow).TotalSeconds/2)
                $routeDeadline=[datetime]::UtcNow.AddSeconds($seconds)
            }
            try {
                if ($route.parts) {
                    $partials=@()
                    foreach ($part in $Asset.parts) { $partials+=Get-AssetFile $part $Directory $Source $OfflineDirectory $routeDeadline -FallbackAvailable:$alternative }
                    $output=[IO.File]::Create($target)
                    try { foreach ($p in $partials) { $input=[IO.File]::OpenRead($p);try { $input.CopyTo($output) } finally { $input.Dispose() } } } finally { $output.Dispose() }
                } else {
                    Write-ReleaseEvent 'download' 'attempt' $route.url
                    Receive-File $route.url $target $Asset $routeDeadline -SwitchOnSlow:$alternative
                }
                Assert-Hash $target $Asset
                Write-ReleaseEvent 'download' 'verified' $route.url
                return $target
            } catch {
                # A failed part assembly/hash must not block the next full route.
                Remove-Item -LiteralPath $target -ErrorAction SilentlyContinue
                Write-ReleaseEvent 'download' 'failed' $route.url;Write-Host $_.Exception.Message;Test-Cancel
                if ($alternative) { Write-ReleaseEvent 'download' 'switch_source' $route.url;Write-Host 'Trying alternate verified download source.' }
            }
            if ($OfflineDirectory) { break }
        }
        if ($OfflineDirectory -or $FallbackAvailable) { break }
    }
    throw ('Unable to obtain verified asset: '+$Asset.name)
}
function Test-AssetRoute($Asset,[string]$Source) {
    if (@(Get-SourceUrls $Asset $Source).Count) { return $true }
    if (-not $Asset.PSObject.Properties['parts'] -or -not $Asset.parts.Count) { return $false }
    foreach ($part in $Asset.parts) { if (-not @(Get-SourceUrls $part $Source).Count) { return $false } }
    return $true
}
function Test-GiteeLocation([string]$Url) {
    try {
        $uri=[uri]$Url
        return $uri.Scheme -eq 'https' -and $uri.Host -eq 'gitee.com' -and -not $uri.UserInfo -and $uri.IsDefaultPort -and
            ($uri.AbsolutePath.StartsWith('/'+$script:MirrorOwner+'/',[StringComparison]::OrdinalIgnoreCase) -or $uri.AbsolutePath.StartsWith('/attachments/download/'))
    } catch { return $false }
}
function Get-ReleaseAttachments($Row) {
    if (-not $Row.PSObject.Properties['assets']) { return @() }
    # Gitee API uses an array; GitHub uses an assets array too. Ignore archives,
    # duplicate names and arbitrary off-project links, never synthesize asset IDs.
    return @($Row.assets|Where-Object {$_.PSObject.Properties['name'] -and $_.PSObject.Properties['browser_download_url'] -and (Test-GiteeLocation $_.browser_download_url)})
}
function Add-DiscoveredLocations($Asset,$Attachments) {
    $attachmentMatches=@($Attachments|Where-Object {$_.name -ceq $Asset.name})
    if ($attachmentMatches.Count -eq 1) { $Asset.urls=@(@($Asset.urls)+@($attachmentMatches[0].browser_download_url)|Select-Object -Unique) }
    if ($Asset.PSObject.Properties['parts']) { foreach ($part in $Asset.parts) { Add-DiscoveredLocations $part $Attachments } }
}
function Get-GiteeReleaseList([datetime]$Deadline) {
    $remaining=[int]($Deadline-[datetime]::UtcNow).TotalMilliseconds
    if ($remaining -le 0) { return @() }
    $url='https://gitee.com/api/v5/repos/'+$script:MirrorOwner+'/releases?page=1&per_page=100'
    $bytes=Get-RemoteBytes $url ([Math]::Min(2500,$remaining))
    $rows=[Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json
    return @($rows|Where-Object {
        $_.PSObject.Properties['tag_name'] -and $_.tag_name -cmatch '^v\d+\.\d+\.\d+$' -and
        (-not $_.PSObject.Properties['draft'] -or -not $_.draft) -and
        (-not $_.PSObject.Properties['prerelease'] -or -not $_.prerelease)
    }|Sort-Object {[version]$_.tag_name.Substring(1)} -Descending)
}
function Get-GiteeManifest($Row,$Known,[string]$KeyPath,[datetime]$Deadline) {
    $version=$Row.tag_name.Substring(1)
    $existing=@($Known|Where-Object {$_.version -eq $version})
    if ($existing.Count) { return ($existing[0]|ConvertTo-Json -Depth 30|ConvertFrom-Json) }
    $attachments=@(Get-ReleaseAttachments $Row)
    $json=@($attachments|Where-Object {$_.name -ceq 'release.json'})
    $sig=@($attachments|Where-Object {$_.name -ceq 'release.sig'})
    $locations=@()
    if ($json.Count -eq 1 -and $sig.Count -eq 1) { $locations+=,@($json[0].browser_download_url,$sig[0].browser_download_url) }
    # Immutable signed history survives main advancing before the mirror assets.
    $base='https://gitee.com/'+$script:MirrorOwner+'/raw/main/release/history/'+$version
    $locations+=,@(($base+'.json'),($base+'.sig'))
    foreach ($location in $locations) {
        Test-Cancel
        try {
            $remaining=[int]($Deadline-[datetime]::UtcNow).TotalMilliseconds
            if ($remaining -le 0) { break }
            $bytes=Get-RemoteBytes $location[0] ([Math]::Min(2000,$remaining))
            $remaining=[int]($Deadline-[datetime]::UtcNow).TotalMilliseconds
            if ($remaining -le 0) { break }
            $signature=[Text.Encoding]::UTF8.GetString((Get-RemoteBytes $location[1] ([Math]::Min(2000,$remaining))))
            Assert-Signature $bytes $signature $KeyPath
            $manifest=[Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json
            if ($manifest.schema_version -ne 1 -or $manifest.channel -ne 'stable' -or $manifest.version -ne $version -or $manifest.minimum_launcher -gt 1) { throw 'Release metadata version/protocol mismatch.' }
            return $manifest
        } catch { Write-ReleaseEvent 'release_discovery' 'metadata_unavailable' $location[0] $version;Test-Cancel }
    }
    return $null
}
function Find-ReleaseCandidates([string]$Source,[string]$KeyPath,[string]$CurrentVersion='0.0.0',[string]$OfflineDirectory='',[string]$Role='portable') {
    Assert-Version $CurrentVersion
    $known=@();$candidates=@()
    try { $known=@(Read-Release $Source $KeyPath $OfflineDirectory -All) }
    catch { Write-ReleaseEvent 'metadata' 'main_unavailable';Write-Host $_.Exception.Message;Test-Cancel }
    foreach ($manifest in $known) {
      try {
        if ([version]$manifest.version -le [version]$CurrentVersion) { continue }
        $origin=$Source
        if ($Source -eq 'Auto' -and $manifest.PSObject.Properties['discovery_source']) { $origin=$manifest.discovery_source }
        if ($OfflineDirectory -or (Test-AssetRoute $manifest.assets.$Role $origin)) {
            $candidates+=,[pscustomobject]@{manifest=$manifest;source=$origin}
        }
      } catch { Write-ReleaseEvent 'metadata' 'candidate_invalid';Test-Cancel }
    }
    if (-not $OfflineDirectory -and $Source -in @('Auto','Gitee')) {
        # Separate from GitHub availability: a failed/advanced GitHub channel
        # never prevents discovering the newest signed Gitee release we can use.
        $deadline=[datetime]::UtcNow.AddSeconds(8)
        try {
            $rows=@(Get-GiteeReleaseList $deadline)
            foreach ($row in $rows) {
              try {
                Test-Cancel
                if ([datetime]::UtcNow -ge $deadline) { break }
                if ([version]$row.tag_name.Substring(1) -le [version]$CurrentVersion) { continue }
                $manifest=Get-GiteeManifest $row $known $KeyPath $deadline
                if (-not $manifest) { continue }
                $attachments=@(Get-ReleaseAttachments $row)
                foreach ($roleName in $manifest.assets.PSObject.Properties.Name) { Add-DiscoveredLocations $manifest.assets.$roleName $attachments }
                if (-not (Test-AssetRoute $manifest.assets.$Role 'Gitee')) { continue }
                $candidates=@($candidates|Where-Object {-not ($_.source -eq 'Gitee' -and $_.manifest.version -eq $manifest.version)})
                $candidates+=,[pscustomobject]@{manifest=$manifest;source='Gitee'}
                Write-ReleaseEvent 'release_discovery' 'candidate' 'https://gitee.com/' $manifest.version
                # Keep at most three signed domestic fallbacks, never scan an
                # unbounded release history during startup.
                if (@($candidates|Where-Object {$_.source -eq 'Gitee'}).Count -ge 3) { break }
              } catch { Write-ReleaseEvent 'release_discovery' 'candidate_invalid' 'https://gitee.com/';Test-Cancel }
            }
        } catch { Write-ReleaseEvent 'release_discovery' 'unavailable' 'https://gitee.com/';Test-Cancel }
    }
    return @($candidates|Sort-Object @{Expression={[version]$_.manifest.version};Descending=$true},@{Expression={$_.source};Descending=$true})
}
function Get-UpdatePackage([string]$Source,[string]$KeyPath,[string]$Directory,[string]$CurrentVersion='0.0.0',[string]$OfflineDirectory='',[string]$BlockedVersion='',[string]$Role='portable',[int]$DownloadSeconds=180) {
    $candidates=@(Find-ReleaseCandidates $Source $KeyPath $CurrentVersion $OfflineDirectory $Role|Where-Object {$_.manifest.version -ne $BlockedVersion})
    if (-not $candidates.Count) { return $null }
    $deadline=[datetime]::UtcNow.AddSeconds($DownloadSeconds)
    for ($i=0;$i -lt $candidates.Count;$i++) {
        Test-Cancel
        $candidate=$candidates[$i];$remaining=$i -lt $candidates.Count-1
        try {
            Write-Host ('Downloading '+$candidate.manifest.version+' from '+$candidate.source+'. S: skip.')
            $routeDeadline=$deadline
            if ($remaining) { $routeDeadline=[datetime]::UtcNow.AddSeconds([Math]::Min(45,($deadline-[datetime]::UtcNow).TotalSeconds/2)) }
            $archive=Get-AssetFile $candidate.manifest.assets.$Role $Directory $candidate.source $OfflineDirectory $routeDeadline -FallbackAvailable:$remaining
            return [pscustomobject]@{manifest=$candidate.manifest;archive=$archive;source=$candidate.source}
        } catch {
            Test-Cancel
            Write-ReleaseEvent 'update_candidate' 'download_failed' '' $candidate.manifest.version
            Write-Host ('Candidate unavailable: '+$candidate.manifest.version+'; '+$_.Exception.Message)
        }
    }
    throw 'No newer verified version could be downloaded; keeping installed version.'
}
function Receive-File([string]$Url,[string]$Target,$Asset,[datetime]$Deadline,[switch]$SwitchOnSlow) {
    Test-Cancel
    if ([datetime]::UtcNow -ge $Deadline) { throw 'Download time budget exceeded.' }
    if (-not $Url.StartsWith('https://')) { throw 'HTTPS required.' }
    # Each signed URL has its own resume cache. Switching sources must not erase
    # useful progress or append bytes from an unrelated ETag.
    $sha=[Security.Cryptography.SHA256]::Create()
    try { $sourceKey=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Url)))).Replace('-','').Substring(0,16) } finally { $sha.Dispose() }
    $partial=$Target+'.'+$sourceKey+'.partial';$etagFile=$partial+'.json';$offset=0;$etag=$null
    $legacy=$Target+'.partial'
    if (-not (Test-Path -LiteralPath $partial) -and (Test-Path -LiteralPath $legacy) -and (Test-Path -LiteralPath ($legacy+'.json'))) {
        try {
            $old=Get-Content -Raw -LiteralPath ($legacy+'.json')|ConvertFrom-Json
            if ($old.url -eq $Url -and $old.hash -eq $Asset.sha256) {
                Move-Item -LiteralPath $legacy -Destination $partial
                Move-Item -LiteralPath ($legacy+'.json') -Destination $etagFile
            }
        } catch { Write-ReleaseEvent 'transfer' 'legacy_cache_unavailable' $Url }
    }
    if ((Test-Path $partial) -and (Test-Path $etagFile)) {
        $info=Get-Content -Raw -LiteralPath $etagFile|ConvertFrom-Json
        if ($info.url -eq $Url -and $info.hash -eq $Asset.sha256 -and $info.etag) { $offset=(Get-Item $partial).Length;$etag=$info.etag }
    }
    if ($offset -ge $Asset.bytes) { $offset=0 }
    $watch=[Diagnostics.Stopwatch]::StartNew();$received=0L
    $remaining=[Math]::Max(1,[int]($Deadline-[datetime]::UtcNow).TotalMilliseconds)
    $request=New-DownloadRequest $Url;$request.Timeout=[Math]::Min(5000,$remaining);$request.ReadWriteTimeout=[Math]::Min(15000,$remaining);$request.UserAgent='MjsOverlay/1.0.0'
    if ($offset -gt 0) { $request.AddRange($offset);$request.Headers['If-Range']=$etag }
    $response=$request.GetResponse()
    try {
        if ($response.ResponseUri.Scheme -ne 'https' -or $response.ContentType -match 'text/html') { throw 'Rejected non-file response.' }
        if ($offset -gt 0 -and ([int]$response.StatusCode -ne 206 -or $response.Headers['ETag'] -ne $etag -or $response.Headers['Content-Range'] -notmatch ('^bytes '+$offset+'-'))) { $offset=0 }
        if ([int]$response.StatusCode -eq 206 -and $offset -eq 0) { throw 'Unexpected partial response.' }
        @{url=$Url;hash=$Asset.sha256;etag=$response.Headers['ETag']}|ConvertTo-Json|Set-Content -LiteralPath $etagFile -Encoding UTF8
        $mode=[IO.FileMode]::Create;if ($offset -gt 0) { $mode=[IO.FileMode]::Append }
        Write-ReleaseEvent 'transfer' $(if($offset -gt 0){'resumed'}else{'full'}) $Url
        $output=[IO.File]::Open($partial,$mode);$stream=$response.GetResponseStream();$buffer=New-Object byte[] 65536
        try {
            while ($true) {
                Test-Cancel;$remaining=[int]($Deadline-[datetime]::UtcNow).TotalMilliseconds
                if ($remaining -le 0) { throw 'Download time budget exceeded.' }
                if ($stream.CanTimeout) { $stream.ReadTimeout=[Math]::Min(15000,$remaining) }
                $count=$stream.Read($buffer,0,$buffer.Length);if($count -le 0){break}
                $output.Write($buffer,0,$count);$offset+=$count
                $received+=$count
                if ($offset -gt $Asset.bytes) { throw 'Download exceeds declared size.' }
                if ($SwitchOnSlow -and (Test-SlowTransfer $watch.Elapsed.TotalSeconds $received ($Asset.bytes-$offset))) {
                    Write-ReleaseEvent 'transfer' 'slow' $Url
                    throw 'Download stays below 256 KiB/s; trying another verified source.'
                }
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

function Test-DownloadLibrary([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $match=[regex]::Match([IO.File]::ReadAllText($Path),'(?m)^# MJS_DOWNLOAD_LIBRARY: (\d+)\r?$')
    if (-not $match.Success -or [long]$match.Groups[1].Value -lt 3) { return $false }
    $errors=$null;$tokens=$null
    [Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$errors)|Out-Null
    return -not $errors
}
function Install-DownloadLibrary([string]$Payload,[string]$Root) {
    # Called only after signature/hash, extraction and startup self-check passed.
    # Never replace the public key, user configuration or installed version files.
    # The compatible
    # protocol-1 entrypoint is refreshed after the library, never before it.
    $source=Join-Path $Payload 'release\Release.ps1'
    if (-not (Test-DownloadLibrary $source)) { return }
    $destination=Join-Path $Root 'release\Release.ps1'
    $pairs=@();$pairs+=,@($source,$destination)
    $launcher=Join-Path $Payload 'launch.ps1'
    if ((Test-Path -LiteralPath $launcher) -and [IO.File]::ReadAllText($launcher) -match '(?m)^# MJS_LAUNCH_PROTOCOL: 1\r?$') {
        $pairs+=,@($launcher,(Join-Path $Root 'launch.ps1'))
    }
    # Library FIRST: old entrypoints work with the new library, the inverse is
    # not guaranteed. Each atomic replacement retains an independent backup.
    foreach ($pair in $pairs) {
        if ((Get-Sha256 $pair[0]) -eq (Get-Sha256 $pair[1])) { continue }
        $temp=$pair[1]+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
        try { [IO.File]::Copy($pair[0],$temp);[IO.File]::Replace($temp,$pair[1],($pair[1]+'.previous')) }
        finally { Remove-Item -LiteralPath $temp -ErrorAction SilentlyContinue }
    }
}

# A fixed outer launch.cmd/launch.ps1 can outlive many application versions.
# Follow only committed, protocol-compatible libraries in the installed payload.
# Old payloads without this marker keep using this library. No network code is
# executed; these are the same local files already trusted to launch the EXE.
$libraryRoot=Split-Path $PSScriptRoot -Parent
$libraryState=Join-Path $libraryRoot 'current.json'
if (Test-Path -LiteralPath $libraryState) {
    try {
        $installed=Get-Content -Raw -LiteralPath $libraryState|ConvertFrom-Json
        Assert-Version $installed.version
        $library=Join-Path $libraryRoot ('versions\'+$installed.version+'\release\Release.ps1')
        if (Test-DownloadLibrary $library) { . $library }
    } catch { Write-Warning 'Installed download library unavailable; using outer library.' }
}
