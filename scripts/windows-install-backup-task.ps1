# Run once in an elevated PowerShell under the dedicated school Margin account.
param(
    [string]$RepoRoot = (Split-Path $PSScriptRoot -Parent),
    [Parameter(Mandatory=$true)][string]$BackupDirectory,
    [string]$At = '02:00'
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path $RepoRoot).Path
New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
$BackupDirectory = (Resolve-Path $BackupDirectory).Path
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$script = Join-Path $RepoRoot 'scripts\windows-nightly-backup.ps1'
$args = '-NoProfile -ExecutionPolicy Bypass -File "' + $script + '" -RepoRoot "' + $RepoRoot + '" -BackupDirectory "' + $BackupDirectory + '"'
$action = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -Argument $args -WorkingDirectory $RepoRoot
Register-ScheduledTask -TaskName 'Margin nightly backup' -Action $action -Trigger (New-ScheduledTaskTrigger -Daily -At $At) -Principal $principal -Settings $settings -Force | Out-Null
Write-Output 'Nightly backup registered. Run it once in Task Scheduler and verify Last Run Result is 0.'
Write-Output 'Keep a separate encrypted/offline copy and test restore on a spare folder or machine.'
