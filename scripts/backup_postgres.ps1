# Backup PostgreSQL (dev: docker container crm-postgres).
# Example Task Scheduler: daily 03:00 — powershell -File scripts\backup_postgres.ps1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$BackupDir = if ($env:BACKUP_DIR) { $env:BACKUP_DIR } else { Join-Path $Root "backups\postgres" }
$Container = if ($env:POSTGRES_CONTAINER) { $env:POSTGRES_CONTAINER } else { "crm-postgres" }
$PgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "crm" }
$PgDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "crm" }
$RetentionDays = if ($env:BACKUP_RETENTION_DAYS) { [int]$env:BACKUP_RETENTION_DAYS } else { 14 }

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$OutFile = Join-Path $BackupDir "crm_$Timestamp.dump"

$exists = docker inspect $Container 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Container $Container not found. Start dev stack first."
}

$RemoteDump = "/tmp/crm_backup_$Timestamp.dump"
Write-Host "Dumping $PgDb -> $OutFile"
docker exec $Container pg_dump -U $PgUser -d $PgDb -Fc -f $RemoteDump
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker cp "${Container}:${RemoteDump}" $OutFile
docker exec $Container rm -f $RemoteDump
$size = (Get-Item $OutFile).Length
Write-Host "OK: $([math]::Round($size / 1MB, 2)) MB"

if ($RetentionDays -gt 0) {
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    Get-ChildItem $BackupDir -Filter "crm_*.dump" | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force
    Write-Host "Pruned dumps older than $RetentionDays days"
}
