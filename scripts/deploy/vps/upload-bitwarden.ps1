# Upload only Vaultwarden to VPS — no git pull, no CRM deploy.
# Run from repo root in PowerShell:
#   .\scripts\deploy\vps\upload-bitwarden.ps1
#   .\scripts\deploy\vps\upload-bitwarden.ps1 -Host 146.19.125.32

param(
    [string]$Host = "146.19.125.32",
    [string]$RemotePath = "/opt/vaultwarden",
    [string]$User = "root"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
$Source = Join-Path $Root "deploy\bitwarden"

if (-not (Test-Path $Source)) {
    Write-Error "Not found: $Source"
}

Write-Host "Uploading $Source -> ${User}@${Host}:${RemotePath}"
Write-Host "CRM will NOT be updated."
Write-Host ""

ssh "${User}@${Host}" "mkdir -p $RemotePath"
scp -r "$Source\*" "${User}@${Host}:${RemotePath}/"

Write-Host ""
Write-Host "Next on server:"
Write-Host "  ssh ${User}@${Host}"
Write-Host "  bash ${RemotePath}/install.sh"
Write-Host ""
Write-Host "User guide: docs/BITWARDEN_USER_GUIDE.md"
