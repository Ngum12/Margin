# Run under the same Windows account as Margin. No network service is contacted.
param(
    [string]$RepoRoot = (Split-Path $PSScriptRoot -Parent),
    [Parameter(Mandatory=$true)][string]$BackupDirectory,
    [ValidateRange(7,365)][int]$KeepDays = 30
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path $RepoRoot).Path
$python = Join-Path $RepoRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Install the locked backend dependencies first.' }
New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
$BackupDirectory = (Resolve-Path $BackupDirectory).Path
$destination = Join-Path $BackupDirectory ('margin-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.zip')
Push-Location (Join-Path $RepoRoot 'backend')
try {
    & $python -m app.cli backup --out $destination
    if ($LASTEXITCODE -ne 0) { throw 'Margin backup failed; earlier backups were kept.' }
} finally { Pop-Location }
# Only prune Margin-owned backup names after a successful replacement exists.
$cutoff = (Get-Date).AddDays(-$KeepDays)
Get-ChildItem -LiteralPath $BackupDirectory -Filter 'margin-backup-*.zip' -File |
    Where-Object { $_.Name -match '^margin-backup-\d{8}-\d{6}\.zip$' -and $_.LastWriteTime -lt $cutoff } |
    Remove-Item -Force
Write-Output ('Backup complete: ' + $destination)
