#Requires -Version 5.1
<#
.SYNOPSIS
  Cloudflare Named Tunnel setup (idempotent: re-run safe if tunnel/cert already exist).
#>
param(
    [string]$ProjectRoot = "",
    [string]$TunnelName = "",
    [string]$Hostname = "",
    [switch]$ForceLogin
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) {
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Err([string]$Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $enc = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Content, $enc)
}

function Invoke-Cloudflared {
    param([string[]]$Args)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = & cloudflared @Args 2>&1 | Out-String
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    return @{ Output = $out; ExitCode = $code }
}

function Get-TunnelIdFromList {
    param([string]$Name)
    $list = Invoke-Cloudflared -Args @("tunnel", "list", "--output", "json")
    if ($list.ExitCode -ne 0 -or -not $list.Output.Trim()) {
        return $null
    }
    try {
        $parsed = $list.Output | ConvertFrom-Json
        $row = $parsed | Where-Object { $_.name -eq $Name } | Select-Object -First 1
        if ($row) { return $row.id }
    }
    catch {
        Write-Warn "Could not parse tunnel list JSON"
    }
    return $null
}

$Root = if ($ProjectRoot) {
    (Resolve-Path $ProjectRoot).Path
}
else {
    (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$CfDir = Join-Path $Root "cloudflare"
$EnvFile = Join-Path $CfDir "tunnel.env"
$EnvExample = Join-Path $CfDir "tunnel.env.example"
$CertPem = Join-Path $env:USERPROFILE ".cloudflared\cert.pem"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Err "cloudflared not found in PATH"
    Write-Info "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    exit 1
}

if (-not (Test-Path $EnvFile)) {
    if (-not (Test-Path $EnvExample)) {
        Write-Err "Missing cloudflare\tunnel.env.example"
        exit 1
    }
    Copy-Item $EnvExample $EnvFile
    Write-Info "Created cloudflare\tunnel.env - edit TUNNEL_HOSTNAME then run this script again"
    if (Get-Command notepad -ErrorAction SilentlyContinue) {
        notepad $EnvFile
    }
    exit 0
}

Get-Content -Path $EnvFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -match '^\s*#' -or $line -notmatch '=') { return }
    $parts = $line -split '=', 2
    $key = $parts[0].Trim()
    $val = $parts[1].Trim().Trim('"')
    Set-Item -Path "env:$key" -Value $val
}

if ($TunnelName) { $env:TUNNEL_NAME = $TunnelName }
if ($Hostname) { $env:TUNNEL_HOSTNAME = $Hostname }

if (-not $env:TUNNEL_NAME) { $env:TUNNEL_NAME = "emiticon-api" }
if (-not $env:TUNNEL_HOSTNAME) {
    Write-Err "Set TUNNEL_HOSTNAME=api.your-real-domain.com in cloudflare\tunnel.env"
    exit 1
}

if ($env:TUNNEL_HOSTNAME -match '(?i)example\.com$') {
    Write-Err "TUNNEL_HOSTNAME must be YOUR domain on Cloudflare (not api.example.com)"
    Write-Info "Example: api.mysite.com where mysite.com uses Cloudflare nameservers"
    exit 1
}

if ($ForceLogin) {
    Write-Info "Force login: remove cert.pem if login refuses to overwrite"
    if (Test-Path $CertPem) {
        Remove-Item $CertPem -Force
    }
}

if (Test-Path $CertPem) {
    Write-Ok "Using existing Cloudflare cert: $CertPem (skip login)"
}
else {
    Write-Info "Cloudflare login (browser)"
    $login = Invoke-Cloudflared -Args @("tunnel", "login")
    if ($login.ExitCode -ne 0) {
        if ($login.Output -match 'existing certificate') {
            Write-Warn "Login skipped: cert.pem already exists at $CertPem"
        }
        else {
            Write-Err "cloudflared tunnel login failed"
            Write-Host $login.Output
            exit 1
        }
    }
    else {
        Write-Ok "Cloudflare login complete"
    }
}

if ($env:TUNNEL_ID) {
    Write-Ok "TUNNEL_ID from tunnel.env: $($env:TUNNEL_ID)"
}
else {
    $fromList = Get-TunnelIdFromList -Name $env:TUNNEL_NAME
    if ($fromList) {
        $env:TUNNEL_ID = $fromList
        Write-Ok "TUNNEL_ID from existing tunnel list: $($env:TUNNEL_ID)"
    }
}

if (-not $env:TUNNEL_ID) {
    Write-Info "Creating tunnel: $($env:TUNNEL_NAME)"
    $create = Invoke-Cloudflared -Args @("tunnel", "create", $env:TUNNEL_NAME)
    Write-Host $create.Output
    if ($create.Output -match '([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})') {
        $env:TUNNEL_ID = $Matches[1]
    }
    if (-not $env:TUNNEL_ID -and $create.Output -match 'already exists') {
        $env:TUNNEL_ID = Get-TunnelIdFromList -Name $env:TUNNEL_NAME
        if ($env:TUNNEL_ID) {
            Write-Ok "Tunnel already exists; reusing TUNNEL_ID=$($env:TUNNEL_ID)"
        }
    }
    if (-not $env:TUNNEL_ID -and $create.ExitCode -ne 0) {
        Write-Err "Could not create or resolve tunnel $($env:TUNNEL_NAME)"
        exit 1
    }
}

if (-not $env:TUNNEL_ID) {
    Write-Err "TUNNEL_ID not found. Add it to cloudflare\tunnel.env"
    exit 1
}

Write-Ok "TUNNEL_ID=$($env:TUNNEL_ID)"

$credDefault = Join-Path $env:USERPROFILE ".cloudflared\$($env:TUNNEL_ID).json"
if (-not (Test-Path $credDefault)) {
    Write-Warn "Credentials file missing: $credDefault"
    Write-Info "If tunnel was created on another PC, copy the .json from that machine"
}

Write-Info "DNS route for $($env:TUNNEL_HOSTNAME)"
$dns = Invoke-Cloudflared -Args @("tunnel", "route", "dns", $env:TUNNEL_NAME, $env:TUNNEL_HOSTNAME)
Write-Host $dns.Output
if ($dns.ExitCode -ne 0) {
    if ($dns.Output -match 'already exists|Record already exists|CNAME') {
        Write-Warn "DNS route may already exist (continuing)"
    }
    else {
        Write-Warn "DNS route command returned exit $($dns.ExitCode); check Cloudflare dashboard"
    }
}

$configYml = Join-Path $CfDir "config.yml"
$yaml = @"
tunnel: $($env:TUNNEL_ID)
credentials-file: $credDefault
protocol: http2

ingress:
  - hostname: $($env:TUNNEL_HOSTNAME)
    service: http://127.0.0.1:8000
  - service: http_status:404
"@

Write-Utf8NoBom -Path $configYml -Content $yaml

$lines = Get-Content -Path $EnvFile -Encoding UTF8
$updated = @()
$seenId = $false
foreach ($line in $lines) {
    if ($line -match '^\s*TUNNEL_NAME=') {
        $updated += "TUNNEL_NAME=$($env:TUNNEL_NAME)"
    }
    elseif ($line -match '^\s*TUNNEL_HOSTNAME=') {
        $updated += "TUNNEL_HOSTNAME=$($env:TUNNEL_HOSTNAME)"
    }
    elseif ($line -match '^\s*TUNNEL_ID=') {
        $updated += "TUNNEL_ID=$($env:TUNNEL_ID)"
        $seenId = $true
    }
    else {
        $updated += $line
    }
}
if (-not $seenId) { $updated += "TUNNEL_ID=$($env:TUNNEL_ID)" }
Write-Utf8NoBom -Path $EnvFile -Content (($updated -join "`n") + "`n")

Write-Host ""
Write-Ok "Wrote $configYml"
Write-Info "Vercel: API_URL=https://$($env:TUNNEL_HOSTNAME)"
Write-Info "Next: run start_local_server.bat"
