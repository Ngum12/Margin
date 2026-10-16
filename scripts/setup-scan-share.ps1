#Requires -RunAsAdministrator
<#
Create the copier-only SMB inbox. Run on the Windows school box, not a workstation.
Use the exact inbox path shown in Margin Settings. Existing shares/users are preserved.
Passwords are prompted securely and never written to disk or command-line arguments.
#>
param(
    [Parameter(Mandatory = $true)][string]$InboxPath,
    [string]$ScannerUser = "MarginScanner",
    [string]$ShareName = "Margin"
)
$ErrorActionPreference = "Stop"
if (-not [IO.Path]::IsPathRooted($InboxPath) -or $InboxPath.StartsWith("\\")) {
    throw "Use the local absolute inbox path displayed in Margin Settings."
}
if ($ScannerUser -notmatch '^[A-Za-z][A-Za-z0-9_-]{2,30}$' -or $ShareName -notmatch '^[A-Za-z][A-Za-z0-9_-]{2,30}$') {
    throw "Use simple local account and share names."
}
$folder = New-Item -ItemType Directory -Path $InboxPath -Force
$account = "$env:COMPUTERNAME\$ScannerUser"
if (-not (Get-LocalUser -Name $ScannerUser -ErrorAction SilentlyContinue)) {
    $password = Read-Host "Set the copier account password (also enter it on the copier)" -AsSecureString
    New-LocalUser -Name $ScannerUser -Password $password -Description "Margin copier inbox only" | Out-Null
}
$acl = Get-Acl -LiteralPath $folder.FullName
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($account, "Modify", "ContainerInherit,ObjectInherit", "None", "Allow")
$acl.SetAccessRule($rule)
Set-Acl -LiteralPath $folder.FullName -AclObject $acl
$share = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
if ($share -and $share.Path -ne $folder.FullName) {
    throw "A share named $ShareName already points elsewhere. Choose another ShareName."
}
if (-not $share) {
    New-SmbShare -Name $ShareName -Path $folder.FullName -ChangeAccess $account -CachingMode None | Out-Null
}
$unexpected = Get-SmbShareAccess -Name $ShareName | Where-Object { $_.AccountName -ne $account -and $_.AccessControlType -eq "Allow" }
if ($unexpected) {
    throw "The existing share grants other accounts access. Review its permissions before using it."
}
# SMB2/3 remains required. Never enable SMB1 or guest access for an old copier.
Set-SmbServerConfiguration -EnableSMB2Protocol $true -Force
if (-not (Get-NetFirewallRule -Name "MarginScannerSMB" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name "MarginScannerSMB" -DisplayName "Margin scanner SMB (school subnet)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 445 -RemoteAddress LocalSubnet -Profile Private,Domain | Out-Null
}
Write-Host "Copier destination: \\$env:COMPUTERNAME\$ShareName"
Write-Host "Copier username: $account"
Write-Host "Use the password you entered. Name the copier shortcut Margin."
Write-Host "In Margin Settings, enable the inbox, save, then choose Send test scan."
