param([switch]$CheckOnly)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$python=Join-Path $repo '.venv\Scripts\python.exe'
if(-not(Test-Path -LiteralPath $python)){throw 'Prepare the project Python environment first.'}
$taskName='MjsOverlay-MaintainData'
if($CheckOnly){Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue;exit}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$action=New-ScheduledTaskAction -Execute $python -Argument ('-X utf8 "'+(Join-Path $PSScriptRoot 'maintain_data.py')+'" --publish') -WorkingDirectory $repo
$daily=New-ScheduledTaskTrigger -Daily -At '05:00'
$login=New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal=New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($daily,$login) -Principal $principal -Settings $settings -Description 'Official boards and licensed guides; logged-in account, no wake, no game controls.' -Force
