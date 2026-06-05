# Run migrations then start staging/prod stack.
#
# Usage:
#   .\scripts\deploy\migrate_and_up.ps1 staging
#   .\scripts\deploy\migrate_and_up.ps1 prod
#   .\scripts\deploy\migrate_and_up.ps1 staging -DryRun
#   .\scripts\deploy\migrate_and_up.ps1 prod -NoBuild
param(
    [ValidateSet("staging", "prod")]
    [string]$Stack = "staging",
    [switch]$DryRun,
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

$EnvFile = "deploy/.env.$Stack"
if (-not (Test-Path $EnvFile)) {
    throw "Missing $EnvFile - copy from deploy/env.$Stack.example"
}

$ComposeFiles = @("-f", "docker/docker-compose.staging.yaml")
if ($Stack -eq "prod") {
    $ComposeFiles += @("-f", "docker/docker-compose.prod.yaml")
}

$Override = "deploy/$Stack/docker-compose.override.yaml"
if (Test-Path $Override) {
    $ComposeFiles += @("-f", $Override)
    Write-Host "Using compose override: $Override"
}

$ComposeBase = @("compose", "--env-file", $EnvFile) + $ComposeFiles

foreach ($line in Get-Content $EnvFile) {
    if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
    $pair = $line -split '=', 2
    if ($pair.Count -eq 2) {
        Set-Item -Path "env:$($pair[0].Trim())" -Value $pair[1].Trim()
    }
}

$rawEnv = Get-Content $EnvFile -Raw
if ($rawEnv -match 'CHANGE_ME') {
    throw "ERROR: $EnvFile still contains CHANGE_ME placeholders."
}
if ($env:JWT_SECRET -and $env:JWT_SECRET.Length -lt 32) {
    throw "ERROR: JWT_SECRET must be at least 32 characters."
}
if ($env:POSTGRES_PASSWORD -and $env:DATABASE_URL -and $env:DATABASE_URL -notlike "*$($env:POSTGRES_PASSWORD)*") {
    throw "ERROR: DATABASE_URL password does not match POSTGRES_PASSWORD."
}
if ((Test-Path $Override) -and -not $env:GHCR_OWNER) {
    throw "ERROR: $Override is present but GHCR_OWNER is not set in $EnvFile."
}

$ProfileArgs = @()
if ($env:COMPOSE_PROFILES) {
    foreach ($p in $env:COMPOSE_PROFILES.Split(',')) {
        $p = $p.Trim()
        if ($p) { $ProfileArgs += @("--profile", $p) }
    }
}

function Invoke-DockerCompose {
    & docker @ComposeBase @ProfileArgs @Args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($DryRun) {
    Write-Host "Validating compose config for stack=$Stack ..."
    Invoke-DockerCompose config --quiet
    Write-Host "Compose config OK for stack=$Stack"
    exit 0
}

$skipBuild = $NoBuild -or $env:SKIP_COMPOSE_BUILD -eq "1" -or (Test-Path $Override) -or ($env:CRM_API_IMAGE -like "ghcr.io/*")
if ($skipBuild) {
    Write-Host "Skipping image build (GHCR override, ghcr.io image, SKIP_COMPOSE_BUILD=1, or -NoBuild)."
} else {
    Write-Host "Building images..."
    Invoke-DockerCompose build api worker frontend
}

Write-Host "Starting data stores..."
Invoke-DockerCompose up -d postgres redis minio
Invoke-DockerCompose up -d minio-init

Write-Host "Waiting for postgres..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    $pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "crm" }
    $pgDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "crm" }
    & docker @ComposeBase @ProfileArgs exec -T postgres pg_isready -U $pgUser -d $pgDb 2>$null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    throw "Postgres not ready after 60s - check logs: docker compose logs postgres"
}

Write-Host "Running alembic upgrade head..."
Invoke-DockerCompose run --rm --no-deps api alembic upgrade head

Write-Host "Starting full stack..."
Invoke-DockerCompose up -d

Write-Host ""
Invoke-DockerCompose ps
