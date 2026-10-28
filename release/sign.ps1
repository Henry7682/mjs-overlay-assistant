param([Parameter(Mandatory=$true)][string]$Manifest,
      [string]$PrivateKey=(Join-Path $env:USERPROFILE '.mjs-release-signing\release-rsa3072.xml'))
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')+'\'
$key=[IO.Path]::GetFullPath($PrivateKey)
if ($key.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) { throw 'Private signing key must remain outside the repository.' }
$rsa=New-Object Security.Cryptography.RSACryptoServiceProvider
$rsa.PersistKeyInCsp=$false
try {
    $rsa.FromXmlString([IO.File]::ReadAllText($key))
    if ($rsa.KeySize -ne 3072) { throw 'RSA-3072 key required.' }
    if ($rsa.ToXmlString($false) -ne [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'public-key.xml'))) { throw 'Signing key does not match the embedded public key.' }
    $bytes=[IO.File]::ReadAllBytes([IO.Path]::GetFullPath($Manifest))
    $signature=[Convert]::ToBase64String($rsa.SignData($bytes,'SHA256'))
    [IO.File]::WriteAllText(([IO.Path]::ChangeExtension([IO.Path]::GetFullPath($Manifest),'.sig')),$signature)
    Write-Host 'Manifest signed. Private key was not copied.'
} finally { $rsa.Dispose() }
