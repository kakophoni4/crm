# Staging / prod post-deploy smoke (API + auth + chats + optional metrics + frontend).
#
# Usage:
#   $env:BASE_URL = "https://api.staging.example.com"
#   $env:FRONTEND_URL = "https://app.staging.example.com"
#   $env:SMOKE_EMAIL = "admin@staging.example.com"
#   $env:SMOKE_PASSWORD = "ChangeMe!Staging234"
#   .\scripts\smoke\staging_smoke.ps1
#
# Exit: 0 = all checks passed, 1 = at least one failed.
$ErrorActionPreference = "Stop"

function Get-EnvOrDefault([string]$Name, [string]$Default) {
    $v = [Environment]::GetEnvironmentVariable($Name)
    if ($v) { return $v }
    return $Default
}

$BaseUrl = (Get-EnvOrDefault "BASE_URL" "https://api.staging.example").TrimEnd("/")
if ($env:FRONTEND_URL) { $FrontendUrl = $env:FRONTEND_URL }
elseif ($env:APP_URL) { $FrontendUrl = $env:APP_URL }
else { $FrontendUrl = "https://app.staging.example" }
$FrontendUrl = $FrontendUrl.TrimEnd("/")
$MetricsEnabled = if ($null -ne $env:METRICS_ENABLED) { $env:METRICS_ENABLED } else { "true" }
if ($env:SMOKE_EMAIL) { $SmokeEmail = $env:SMOKE_EMAIL }
elseif ($env:SEED_ADMIN_EMAIL) { $SmokeEmail = $env:SEED_ADMIN_EMAIL }
else { $SmokeEmail = "admin@staging.example.com" }
if ($env:SMOKE_PASSWORD) { $SmokePassword = $env:SMOKE_PASSWORD }
elseif ($env:SEED_ADMIN_PASSWORD) { $SmokePassword = $env:SEED_ADMIN_PASSWORD }
else { $SmokePassword = "ChangeMe!Staging234" }
$Api = "$BaseUrl/api/v1"

$script:Passed = 0
$script:Failed = 0

function Test-MetricsEnabled {
    switch -Regex ($MetricsEnabled.Trim().ToLowerInvariant()) {
        "^(0|false|no|off)$" { return $false }
        default { return $true }
    }
}

function Write-Ok([string]$Message) {
    Write-Host "[OK]   $Message" -ForegroundColor Green
    $script:Passed++
}

function Write-Fail([string]$Message) {
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    $script:Failed++
}

function Invoke-SmokeRequest {
    param(
        [string]$Method = "GET",
        [string]$Uri,
        [hashtable]$Headers = @{},
        [string]$Body = $null
    )
    $params = @{
        Method      = $Method
        Uri         = $Uri
        TimeoutSec  = 30
        Headers     = $Headers
        ErrorAction = "Stop"
    }
    if ($Body) {
        $params.Body = $Body
        $params.ContentType = "application/json"
    }
    return Invoke-WebRequest @params
}

Write-Host "==> GET $BaseUrl/healthz"
try {
    $hz = Invoke-SmokeRequest -Uri "$BaseUrl/healthz"
    if ($hz.StatusCode -eq 200) { Write-Ok "healthz HTTP 200" } else { Write-Fail "healthz expected HTTP 200, got $($hz.StatusCode)" }
} catch {
    Write-Fail "healthz: $($_.Exception.Message)"
}

Write-Host "==> GET $BaseUrl/readyz"
try {
    $rz = Invoke-SmokeRequest -Uri "$BaseUrl/readyz"
    $payload = $rz.Content | ConvertFrom-Json
    if ($payload.status -eq "ready") { Write-Ok "readyz status=ready" } else { Write-Fail "readyz expected status=ready, got '$($payload.status)'" }
} catch {
    Write-Fail "readyz: $($_.Exception.Message)"
}

if (Test-MetricsEnabled) {
    Write-Host "==> GET $BaseUrl/metrics (METRICS_ENABLED)"
    try {
        $mx = Invoke-SmokeRequest -Uri "$BaseUrl/metrics"
        if ($mx.Content -match "http_requests_total") { Write-Ok "metrics contains http_requests_total" }
        else { Write-Fail "metrics missing http_requests_total" }
    } catch {
        Write-Fail "metrics: $($_.Exception.Message)"
    }
} else {
    Write-Host "==> SKIP /metrics (METRICS_ENABLED=false)"
}

Write-Host "==> POST $Api/auth/login"
$accessToken = $null
try {
    $loginBody = (@{ email = $SmokeEmail; password = $SmokePassword } | ConvertTo-Json -Compress)
    $login = Invoke-SmokeRequest -Method POST -Uri "$Api/auth/login" -Body $loginBody
    $loginJson = $login.Content | ConvertFrom-Json
    $accessToken = $loginJson.access_token
    if ($accessToken) { Write-Ok "auth login returned access_token" }
    else { Write-Fail "auth login missing access_token for $SmokeEmail" }
} catch {
    Write-Fail "auth login failed for ${SmokeEmail}: $($_.Exception.Message)"
}

if ($accessToken) {
    Write-Host "==> GET $Api/chats"
    try {
        $chats = Invoke-SmokeRequest -Uri "$Api/chats?limit=1" -Headers @{ Authorization = "Bearer $accessToken" }
        if ($chats.StatusCode -eq 200) { Write-Ok "GET /chats HTTP 200" }
        else { Write-Fail "GET /chats expected HTTP 200, got $($chats.StatusCode)" }
    } catch {
        Write-Fail "GET /chats: $($_.Exception.Message)"
    }
} else {
    Write-Fail "GET /chats skipped (no token)"
}

Write-Host "==> GET $FrontendUrl/"
try {
    $fe = Invoke-SmokeRequest -Uri "$FrontendUrl/"
    $ct = $fe.Headers["Content-Type"]
    if ($fe.StatusCode -eq 200 -and ($ct -match "html")) { Write-Ok "frontend HTTP 200 (text/html)" }
    elseif ($fe.StatusCode -eq 200) { Write-Ok "frontend HTTP 200" }
    else { Write-Fail "frontend expected HTTP 200, got $($fe.StatusCode)" }
} catch {
    Write-Fail "frontend: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Smoke summary: $Passed passed, $Failed failed"
if ($Failed -gt 0) { exit 1 }
Write-Host "Staging smoke passed."
exit 0
