$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Release.ps1')
try {
    $manifest=Read-Release 'Auto' (Join-Path $PSScriptRoot 'public-key.xml')
    @{version=$manifest.version;status='verified'}|ConvertTo-Json -Compress
} catch { @{status='unavailable'}|ConvertTo-Json -Compress }
