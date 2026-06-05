$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$ComposeFile = "docker/docker-compose.dev.yaml"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

Write-Host "Starting dev dependencies..."
docker compose -f $ComposeFile up -d --wait 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "All services reported healthy (docker compose --wait)."
} else {
    docker compose -f $ComposeFile up -d
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Waiting up to 20s for healthchecks..."
    Start-Sleep -Seconds 20
}

Write-Host ""
Write-Host "=== CRM Chat Center — local dev URLs ==="
Write-Host "API (run app locally):  http://localhost:8000"
Write-Host "Adminer (PostgreSQL):   http://localhost:8080"
Write-Host "MinIO console:          http://localhost:9001  (user: minio / miniominio)"
Write-Host "MinIO S3 API:           http://localhost:9000"
Write-Host "MailHog (SMTP UI):      http://localhost:8025  (SMTP: localhost:1025)"
Write-Host "Frontend (Vite):        http://localhost:5173"
Write-Host ""
docker compose -f $ComposeFile ps
