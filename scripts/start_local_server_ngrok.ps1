#Requires -Version 5.1
<#
.SYNOPSIS
  Local FastAPI + ngrok (fixed domain when NGROK_DOMAIN is set).
#>
param(
    [int]$Port = 8000,
    [int]$NgrokApiPort = 4040,
    [switch]$NoBrowser,
    [switch]$NoNgrok,
    [switch]$ForceRestart
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

function Import-NgrokEnvFiles {
    param([string]$Root)
    $paths = @(
        (Join-Path $Root ".env"),
        (Join-Path $Root "ngrok\ngrok.env")
    )
    foreach ($path in $paths) {
        if (-not (Test-Path $path)) { continue }
        Get-Content -Path $path -Encoding UTF8 | ForEach-Object {
            $line = $_.Trim()
            if ($line -match '^\s*#' -or $line -notmatch '=') { return }
            $parts = $line -split '=', 2
            $key = $parts[0].Trim()
            $val = $parts[1].Trim().Trim('"').Trim("'")
            switch ($key) {
                'NGROK_DOMAIN' { if ($val) { $script:NgrokDomain = $val } }
                'NGROK_AUTHTOKEN' { if ($val) { $env:NGROK_AUTHTOKEN = $val } }
                'NGROK_REGION' { if ($val) { $env:NGROK_REGION = $val } }
                'NGROK_API_PORT' { if ($val -match '^\d+$') { $script:NgrokApiPort = [int]$val } }
            }
        }
    }
}

function Test-NgrokAuthtokenConfigured {
    if ($env:NGROK_AUTHTOKEN -and $env:NGROK_AUTHTOKEN.Length -gt 8) {
        return $true
    }
    $cfgPaths = @(
        (Join-Path $env:LOCALAPPDATA "ngrok\ngrok.yml"),
        (Join-Path $env:USERPROFILE ".ngrok2\ngrok.yml")
    )
    foreach ($cfg in $cfgPaths) {
        if (-not (Test-Path $cfg)) { continue }
        $raw = Get-Content $cfg -Raw -ErrorAction SilentlyContinue
        if ($raw -match '(?m)^\s*authtoken:\s*(\S+)') {
            return $true
        }
    }
    return $false
}

function Get-NgrokPublicUrl {
    param([int]$ApiPort)
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:${ApiPort}/api/tunnels" -UseBasicParsing -TimeoutSec 3
        if (-not $resp.tunnels) { return $null }
        foreach ($t in $resp.tunnels) {
            $url = [string]$t.public_url
            if ($url -match '^https://') {
                return $url.TrimEnd('/')
            }
        }
        foreach ($t in $resp.tunnels) {
            $url = [string]$t.public_url
            if ($url) {
                return $url.TrimEnd('/')
            }
        }
    }
    catch {
        return $null
    }
    return $null
}

function Wait-NgrokPublicUrl {
    param([int]$ApiPort, [int]$Seconds = 45)
    for ($i = 0; $i -lt $Seconds; $i++) {
        $url = Get-NgrokPublicUrl -ApiPort $ApiPort
        if ($url) { return $url }
        Start-Sleep -Seconds 1
    }
    return $null
}

function Test-HttpHealth {
    param([string]$Uri, [hashtable]$Headers = @{})
    try {
        $params = @{
            Uri             = $Uri
            UseBasicParsing = $true
            TimeoutSec      = 5
        }
        if ($Headers.Count -gt 0) {
            $params.Headers = $Headers
        }
        $r = Invoke-WebRequest @params
        return ($r.StatusCode -eq 200)
    }
    catch {
        return $false
    }
}

function Test-NgrokLogHasPaidPlanError {
    param([string]$OutLog, [string]$ErrLog)
    foreach ($path in @($ErrLog, $OutLog)) {
        if (-not (Test-Path $path)) { continue }
        $text = Get-Content $path -Raw -ErrorAction SilentlyContinue
        if ($text -match 'ERR_NGROK_313|custom subdomains') {
            return $true
        }
    }
    return $false
}

function Get-ListeningPidsOnPort {
    param([int]$LocalPort)
    $conns = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return @() }
    return @($conns | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Stop-ListenersOnPort {
    param([int]$LocalPort, [string]$Label)
    $pids = Get-ListeningPidsOnPort -LocalPort $LocalPort
    foreach ($procId in $pids) {
        Write-Warn "Stopping $Label on port $LocalPort (PID $procId)"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    if ($pids.Count -gt 0) {
        Start-Sleep -Seconds 2
    }
}

function Start-NgrokTunnelProcess {
    param(
        [int]$LocalPort,
        [string]$StaticDomain,
        [string]$OutLog,
        [string]$ErrLog
    )
    $args = @("http", "$LocalPort", "--log=stdout")
    if ($StaticDomain) {
        $args += "--domain=$StaticDomain"
    }
    if ($env:NGROK_REGION) {
        $args += "--region=$($env:NGROK_REGION)"
    }
    return @{
        Process = Start-Process -FilePath "ngrok" -ArgumentList $args `
            -RedirectStandardOutput $OutLog `
            -RedirectStandardError $ErrLog `
            -PassThru -WindowStyle Hidden
        Args    = ($args -join ' ')
    }
}

function Show-LogTail {
    param([string]$OutLog, [string]$ErrLog, [int]$Lines = 30)
    if (Test-Path $OutLog) {
        Write-Host "--- stdout (last $Lines) ---"
        Get-Content $OutLog -Tail $Lines -ErrorAction SilentlyContinue
    }
    if (Test-Path $ErrLog) {
        Write-Host "--- stderr (last $Lines) ---"
        Get-Content $ErrLog -Tail $Lines -ErrorAction SilentlyContinue
    }
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Backend = Join-Path $Root "web\backend"
$VenvActivate = Join-Path $Root ".venv\Scripts\Activate.ps1"
$LogDir = Join-Path $Root "logs"
$ApiLogOut = Join-Path $LogDir "fastapi.out.log"
$ApiLogErr = Join-Path $LogDir "fastapi.err.log"
$NgrokLogOut = Join-Path $LogDir "ngrok.out.log"
$NgrokLogErr = Join-Path $LogDir "ngrok.err.log"
$NgrokUrlFile = Join-Path $LogDir "ngrok_url.txt"
$script:NgrokDomain = $null

$env:FACTORY_ROOT = $Root
$env:PYTHONUNBUFFERED = "1"

Import-NgrokEnvFiles -Root $Root

Write-Info "Project root: $Root"

if (-not $NoNgrok) {
    if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
        Write-Err "ngrok not found in PATH"
        Write-Info "Install: https://ngrok.com/download"
        Write-Info "Or: winget install ngrok.ngrok"
        Write-Info "Then: ngrok config add-authtoken YOUR_TOKEN"
        exit 1
    }
    if (-not (Test-NgrokAuthtokenConfigured)) {
        Write-Err "ngrok authtoken not configured"
        Write-Info "1) Sign up: https://dashboard.ngrok.com/signup"
        Write-Info "2) Copy token from https://dashboard.ngrok.com/get-started/your-authtoken"
        Write-Info "3) Run: ngrok config add-authtoken YOUR_TOKEN"
        Write-Info "Or add to .env: NGROK_AUTHTOKEN=..."
        exit 1
    }
    if ($NgrokDomain) {
        Write-Info "NGROK_DOMAIN set -> paid/static mode (ngrok http $Port --domain=...)"
    }
    else {
        Write-Info "NGROK_DOMAIN empty -> free mode (random URL each run)"
    }
}

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
    Write-Err "uvicorn not installed"
    exit 1
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "web\jobs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "ngrok") | Out-Null

$localHealth = "http://127.0.0.1:$Port/health"
$apiProc = $null
$apiStartedByScript = $false
$ngrokStartedByScript = $false

$apiPids = Get-ListeningPidsOnPort -LocalPort $Port
if ($apiPids.Count -gt 0) {
    if ($ForceRestart) {
        Write-Warn "ForceRestart: stopping process on port $Port"
        Stop-ListenersOnPort -LocalPort $Port -Label "port $Port listener"
    }
    elseif (Test-HttpHealth -Uri $localHealth) {
        Write-Ok "FastAPI already running on port $Port (PID $($apiPids -join ',')) - reusing"
        try {
            $r = Invoke-WebRequest -Uri $localHealth -UseBasicParsing -TimeoutSec 3
            Write-Ok "Local health: $($r.Content)"
        }
        catch {
            Write-Ok "Local health: OK"
        }
    }
    else {
        Write-Warn "Port $Port in use but /health failed - stopping PID $($apiPids -join ',')"
        Stop-ListenersOnPort -LocalPort $Port -Label "port $Port listener"
    }
}

if (-not (Test-HttpHealth -Uri $localHealth)) {
    Write-Info "Starting FastAPI on 127.0.0.1:$Port"
    $uvicornArgs = @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$Port")
    $apiProc = Start-Process -FilePath "python" -ArgumentList $uvicornArgs `
        -WorkingDirectory $Backend `
        -RedirectStandardOutput $ApiLogOut `
        -RedirectStandardError $ApiLogErr `
        -PassThru -WindowStyle Hidden
    $apiStartedByScript = $true

    Start-Sleep -Seconds 2
    if ($apiProc.HasExited) {
        Write-Err "uvicorn exited immediately"
        Show-LogTail -OutLog $ApiLogOut -ErrLog $ApiLogErr
        exit 1
    }

    $healthOk = $false
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-HttpHealth -Uri $localHealth) {
            $healthOk = $true
            try {
                $r = Invoke-WebRequest -Uri $localHealth -UseBasicParsing -TimeoutSec 3
                Write-Ok "Local health: $($r.Content)"
            }
            catch {
                Write-Ok "Local health: OK"
            }
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $healthOk) {
        Write-Err "No response from $localHealth"
        Show-LogTail -OutLog $ApiLogOut -ErrLog $ApiLogErr
        Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue
        exit 1
    }
}

if (-not $NoNgrok) {
    $ngrokPids = Get-ListeningPidsOnPort -LocalPort $NgrokApiPort
    if ($ngrokPids.Count -gt 0) {
        $existingNgrokUrl = Get-NgrokPublicUrl -ApiPort $NgrokApiPort
        if ($ForceRestart -or -not $existingNgrokUrl) {
            Write-Warn "Stopping previous ngrok on port $NgrokApiPort (PID $($ngrokPids -join ','))"
            Stop-ListenersOnPort -LocalPort $NgrokApiPort -Label "ngrok API"
        }
        else {
            Write-Ok "ngrok already running on port $NgrokApiPort - will reuse tunnel API"
        }
    }
}

$ngrokProc = $null
$publicUrl = $null
$ngrokStaticMode = $false
$ngrokHeaders = @{ "ngrok-skip-browser-warning" = "true" }

if (-not $NoNgrok) {
    $existingNgrokUrl = Get-NgrokPublicUrl -ApiPort $NgrokApiPort
    if ($existingNgrokUrl -and -not $ForceRestart) {
        $publicUrl = $existingNgrokUrl
        $ngrokStaticMode = $false
        Set-Content -Path $NgrokUrlFile -Value $publicUrl -Encoding UTF8
        Write-Host ""
        Write-Ok "ngrok public URL (reused):"
        Write-Host "  $publicUrl" -ForegroundColor Green
        Write-Host ""
    }
    else {
    if (Test-Path $NgrokUrlFile) { Remove-Item $NgrokUrlFile -Force -ErrorAction SilentlyContinue }

    $ngrokStaticMode = -not [string]::IsNullOrWhiteSpace($NgrokDomain)
    $staticDomain = if ($ngrokStaticMode) { $NgrokDomain.Trim() } else { $null }

    if ($ngrokStaticMode) {
        Write-Info "Starting ngrok (paid/static): ngrok http $Port --domain=$staticDomain"
    }
    else {
        Write-Info "Starting ngrok (free): ngrok http $Port"
    }

    $started = Start-NgrokTunnelProcess -LocalPort $Port -StaticDomain $staticDomain `
        -OutLog $NgrokLogOut -ErrLog $NgrokLogErr
    $ngrokProc = $started.Process
    $ngrokStartedByScript = $true

    Start-Sleep -Seconds 3
    $paidPlanError = Test-NgrokLogHasPaidPlanError -OutLog $NgrokLogOut -ErrLog $NgrokLogErr

    if ($ngrokStaticMode -and ($ngrokProc.HasExited -or $paidPlanError)) {
        Write-Warn "ERR_NGROK_313: custom subdomain requires a paid ngrok plan"
        Write-Warn "Falling back to free mode (remove NGROK_DOMAIN from .env to skip this step)"
        if (-not $ngrokProc.HasExited) {
            Stop-Process -Id $ngrokProc.Id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
        if (Test-Path $NgrokLogOut) { Clear-Content $NgrokLogOut -ErrorAction SilentlyContinue }
        if (Test-Path $NgrokLogErr) { Clear-Content $NgrokLogErr -ErrorAction SilentlyContinue }

        $ngrokStaticMode = $false
        $staticDomain = $null
        Write-Info "Starting ngrok (free): ngrok http $Port"
        $started = Start-NgrokTunnelProcess -LocalPort $Port -StaticDomain $null `
            -OutLog $NgrokLogOut -ErrLog $NgrokLogErr
        $ngrokProc = $started.Process
        Start-Sleep -Seconds 2
    }

    if ($ngrokProc.HasExited) {
        Write-Err "ngrok exited immediately"
        Show-LogTail -OutLog $NgrokLogOut -ErrLog $NgrokLogErr
        if ($apiStartedByScript -and $null -ne $apiProc) {
            Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue
        }
        exit 1
    }

    $publicUrl = Wait-NgrokPublicUrl -ApiPort $NgrokApiPort
    if (-not $publicUrl) {
        Write-Err "Could not read ngrok public URL from http://127.0.0.1:${NgrokApiPort}/api/tunnels"
        Show-LogTail -OutLog $NgrokLogOut -ErrLog $NgrokLogErr
        Stop-Process -Id $ngrokProc.Id -Force -ErrorAction SilentlyContinue
        if ($apiStartedByScript -and $null -ne $apiProc) {
            Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue
        }
        exit 1
    }

    Set-Content -Path $NgrokUrlFile -Value $publicUrl -Encoding UTF8
    Write-Host ""
    if ($ngrokStaticMode) {
        Write-Ok "ngrok static domain:"
    }
    else {
        Write-Ok "ngrok public URL:"
        Write-Warn "Free plan: copy URL to Vercel API_URL after each restart (see logs\ngrok_url.txt)"
    }
    Write-Host "  $publicUrl" -ForegroundColor Green
    Write-Host ""

    $publicHealth = "$publicUrl/health"
    if (Test-HttpHealth -Uri $publicHealth -Headers $ngrokHeaders) {
        Write-Ok "Public health via ngrok: $publicHealth"
    }
    else {
        Write-Warn "Public health check failed (browser may still work)"
        Write-Info "Free tier: add header ngrok-skip-browser-warning for API clients"
    }
    }
}

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:$Port/docs"
    Start-Process $localHealth
    if ($publicUrl) {
        Write-Info "Browser: local /docs (ngrok URL in address bar shows interstitial page)"
        Start-Process "$publicUrl/health"
    }
}

Write-Host ""
Write-Host "========================================"
Write-Ok "Local API:  http://127.0.0.1:$Port"
if ($publicUrl) {
    Write-Ok "Public URL: $publicUrl"
    if ($ngrokStaticMode) {
        Write-Info "Vercel API_URL=$publicUrl  (fixed while NGROK_DOMAIN unchanged)"
    }
    else {
        Write-Info "Vercel API_URL=$publicUrl  (update + redeploy when URL changes)"
    }
    Write-Info "Saved: logs\ngrok_url.txt"
}
Write-Info "Logs: logs\fastapi.*.log, logs\ngrok.*.log"
if ($apiStartedByScript -or $ngrokStartedByScript) {
    Write-Info "Press Enter to stop processes started by this script"
}
else {
    Write-Info "Press Enter to exit (FastAPI/ngrok were already running)"
}
Write-Host "========================================"

Read-Host "Press Enter to shutdown"

if ($ngrokStartedByScript -and $null -ne $ngrokProc -and -not $ngrokProc.HasExited) {
    Stop-Process -Id $ngrokProc.Id -Force -ErrorAction SilentlyContinue
    Write-Ok "Stopped ngrok"
}
if ($apiStartedByScript -and $null -ne $apiProc -and -not $apiProc.HasExited) {
    Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue
    Write-Ok "Stopped FastAPI"
}
if (-not $apiStartedByScript -and -not $ngrokStartedByScript) {
    Write-Info "No processes started by this run were stopped"
}

Write-Ok "Done"
