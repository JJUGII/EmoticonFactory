#Requires -Version 5.1
<#
.SYNOPSIS
  Start local FastAPI + public URL via Cloudflare (named tunnel or quick tunnel without domain).
#>
param(
    [int]$Port = 8000,
    [switch]$NoTunnel,
    [switch]$NoBrowser,
    [switch]$QuickTunnel,
    [switch]$NamedTunnel
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

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Backend = Join-Path $Root "web\backend"
$CfConfig = Join-Path $Root "cloudflare\config.yml"
$CfEnv = Join-Path $Root "cloudflare\tunnel.env"
$VenvActivate = Join-Path $Root ".venv\Scripts\Activate.ps1"
$LogDir = Join-Path $Root "logs"
$ApiLogOut = Join-Path $LogDir "fastapi.out.log"
$ApiLogErr = Join-Path $LogDir "fastapi.err.log"
$TunnelLogOut = Join-Path $LogDir "cloudflared.out.log"
$TunnelLogErr = Join-Path $LogDir "cloudflared.err.log"
$QuickUrlFile = Join-Path $LogDir "quick_tunnel_url.txt"

function Get-TunnelHostnameFromEnv {
    param([string]$EnvPath)
    if (-not (Test-Path $EnvPath)) { return $null }
    foreach ($line in Get-Content -Path $EnvPath -Encoding UTF8) {
        if ($line -match '^\s*TUNNEL_HOSTNAME=(.+)$') {
            return $Matches[1].Trim().Trim('"')
        }
    }
    return $null
}

function Test-PlaceholderTunnelHostname {
    param([string]$Hostname)
    if (-not $Hostname) { return $true }
    if ($Hostname -match '(?i)YOUR-DOMAIN') { return $true }
    return ($Hostname -match '(?i)example\.com$') -or ($Hostname -match '(?i)^api\.yourdomain\.com$')
}

function Wait-CloudflaredConnected {
    param([string]$ErrLog, [int]$Seconds = 20)
    for ($i = 0; $i -lt $Seconds; $i++) {
        if (Test-Path $ErrLog) {
            $text = Get-Content $ErrLog -Tail 40 -ErrorAction SilentlyContinue | Out-String
            if ($text -match 'Registered tunnel connection') {
                return $true
            }
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Get-QuickTunnelUrlFromLogs {
    param([string]$OutLog, [string]$ErrLog)
    $pattern = 'https://[a-z0-9-]+\.trycloudflare\.com'
    foreach ($path in @($ErrLog, $OutLog)) {
        if (-not (Test-Path $path)) { continue }
        $text = Get-Content $path -Raw -ErrorAction SilentlyContinue
        if ($text -match $pattern) {
            return $Matches[0]
        }
    }
    return $null
}

function Wait-QuickTunnelUrl {
    param([string]$OutLog, [string]$ErrLog, [int]$Seconds = 45)
    for ($i = 0; $i -lt $Seconds; $i++) {
        $url = Get-QuickTunnelUrlFromLogs -OutLog $OutLog -ErrLog $ErrLog
        if ($url) { return $url }
        Start-Sleep -Seconds 1
    }
    return $null
}

function Show-LogTail {
    param([string]$OutLog, [string]$ErrLog, [int]$Lines = 40)
    if (Test-Path $OutLog) {
        Write-Host "--- stdout (last $Lines) ---"
        Get-Content $OutLog -Tail $Lines -ErrorAction SilentlyContinue
    }
    if (Test-Path $ErrLog) {
        Write-Host "--- stderr (last $Lines) ---"
        Get-Content $ErrLog -Tail $Lines -ErrorAction SilentlyContinue
    }
}

$env:FACTORY_ROOT = $Root
$env:PYTHONUNBUFFERED = "1"

Write-Info "Project root: $Root"

if (-not (Test-Path $VenvActivate)) {
    Write-Err ".venv not found. Run: python -m venv .venv"
    exit 1
}

. $VenvActivate

$WebRequirements = Join-Path $Backend "requirements.txt"
Write-Info "Installing dependencies from web\backend\requirements.txt"
pip install -q -r $WebRequirements
if ($LASTEXITCODE -ne 0) {
    Write-Err "pip install failed"
    exit 1
}

python -c "import uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Err "uvicorn not installed after pip install"
    exit 1
}

$inUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($inUse) {
    Write-Err "Port $Port is already in use (PID $($inUse.OwningProcess -join ','))"
    exit 1
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "web\jobs") | Out-Null

$publicUrl = "http://127.0.0.1:$Port"
$useQuickTunnel = $QuickTunnel
$tunnelHost = Get-TunnelHostnameFromEnv -EnvPath $CfEnv

if (-not $NoTunnel) {
    if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
        Write-Warn "cloudflared not in PATH; running without tunnel"
        $NoTunnel = $true
    }
    elseif ($NamedTunnel) {
        $useQuickTunnel = $false
    }
    elseif ($useQuickTunnel) {
        Write-Info "Quick Tunnel mode (no domain required)"
    }
    elseif (Test-PlaceholderTunnelHostname -Hostname $tunnelHost) {
        Write-Info "No real domain in tunnel.env -> Quick Tunnel (trycloudflare.com)"
        $useQuickTunnel = $true
    }
    elseif (-not (Test-Path $CfConfig)) {
        Write-Info "No cloudflare\config.yml -> Quick Tunnel"
        $useQuickTunnel = $true
    }
    else {
        $publicUrl = "https://$tunnelHost"
    }
}

Write-Info "Starting FastAPI on 127.0.0.1:$Port (cwd=$Backend)"
$uvicornArgs = @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$Port")
$apiProc = Start-Process -FilePath "python" -ArgumentList $uvicornArgs `
    -WorkingDirectory $Backend `
    -RedirectStandardOutput $ApiLogOut `
    -RedirectStandardError $ApiLogErr `
    -PassThru -WindowStyle Hidden

Start-Sleep -Seconds 2
if ($apiProc.HasExited) {
    Write-Err "uvicorn exited immediately. See logs\fastapi.*.log"
    Show-LogTail -OutLog $ApiLogOut -ErrLog $ApiLogErr
    exit 1
}

$healthOk = $false
$healthUri = "http://127.0.0.1:$Port/health"
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri $healthUri -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            $healthOk = $true
            Write-Ok "Health check: $($r.Content)"
            break
        }
    }
    catch {
        Start-Sleep -Milliseconds 500
    }
}

if (-not $healthOk) {
    Write-Err "No response from $healthUri"
    Show-LogTail -OutLog $ApiLogOut -ErrLog $ApiLogErr
    Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

$tunnelProc = $null
if (-not $NoTunnel) {
    if ($useQuickTunnel) {
        if (Test-Path $QuickUrlFile) { Remove-Item $QuickUrlFile -Force -ErrorAction SilentlyContinue }
        Write-Info "Starting Cloudflare Quick Tunnel -> http://127.0.0.1:$Port"
        $tunnelProc = Start-Process -FilePath "cloudflared" `
            -ArgumentList @("tunnel", "--url", "http://127.0.0.1:$Port") `
            -RedirectStandardOutput $TunnelLogOut `
            -RedirectStandardError $TunnelLogErr `
            -PassThru -WindowStyle Hidden
        $quickUrl = Wait-QuickTunnelUrl -OutLog $TunnelLogOut -ErrLog $TunnelLogErr
        if ($quickUrl) {
            $publicUrl = $quickUrl.TrimEnd('/')
            Set-Content -Path $QuickUrlFile -Value $publicUrl -Encoding UTF8
            Write-Ok "Quick Tunnel URL: $publicUrl"
            Write-Warn "URL changes every time you restart. Update Vercel API_URL after each run."
        }
        else {
            Write-Warn "Could not read trycloudflare URL yet. Check logs\cloudflared.err.log"
            Show-LogTail -OutLog $TunnelLogOut -ErrLog $TunnelLogErr -Lines 20
        }
    }
    else {
        $tunnelProtocol = $env:TUNNEL_PROTOCOL
        if (-not $tunnelProtocol) { $tunnelProtocol = "http2" }
        Write-Info "Starting Named Tunnel (protocol=$tunnelProtocol)"
        $tunnelProc = Start-Process -FilePath "cloudflared" `
            -ArgumentList @("tunnel", "--config", $CfConfig, "--protocol", $tunnelProtocol, "run") `
            -RedirectStandardOutput $TunnelLogOut `
            -RedirectStandardError $TunnelLogErr `
            -PassThru -WindowStyle Hidden
        if ($tunnelProc.HasExited) {
            Write-Warn "cloudflared exited early. See logs\cloudflared.*.log"
            Show-LogTail -OutLog $TunnelLogOut -ErrLog $TunnelLogErr
            $tunnelProc = $null
        }
        elseif (Wait-CloudflaredConnected -ErrLog $TunnelLogErr) {
            Write-Ok "Named tunnel connected to edge"
        }
        else {
            Write-Warn "Named tunnel not confirmed. Try: -QuickTunnel (no domain)"
            Show-LogTail -OutLog $TunnelLogOut -ErrLog $TunnelLogErr -Lines 15
        }
    }
}

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:$Port/docs"
    if (-not $NoTunnel -and $publicUrl -notlike "http://127.0.0.1*") {
        Start-Process "$publicUrl/health"
    }
}

Write-Host ""
Write-Host "========================================"
Write-Ok "Local API:  http://127.0.0.1:$Port"
if ($publicUrl -notlike "http://127.0.0.1*") {
    Write-Ok "Public URL: $publicUrl"
    Write-Info "Vercel: API_URL=$publicUrl  (redeploy after URL change)"
}
else {
    Write-Info "Public URL: none (tunnel off or URL not ready)"
}
Write-Info "Logs: logs\fastapi.{out,err}.log, logs\cloudflared.{out,err}.log"
if ($useQuickTunnel) {
    Write-Info "Quick URL file: logs\quick_tunnel_url.txt"
}
Write-Info "Press Enter to stop API and tunnel"
Write-Host "========================================"

Read-Host "Press Enter to shutdown"

if ($null -ne $tunnelProc -and -not $tunnelProc.HasExited) {
    Stop-Process -Id $tunnelProc.Id -Force -ErrorAction SilentlyContinue
}
if (-not $apiProc.HasExited) {
    Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue
}

Write-Ok "Stopped"
