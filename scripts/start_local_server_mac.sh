#!/usr/bin/env bash
# Mac mini local stack: FastAPI + optional ComfyUI + ngrok or Cloudflare Quick Tunnel.

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
# shellcheck source=common_mac.sh
source "$SCRIPT_DIR/common_mac.sh"

PROJECT_ROOT="$(resolve_project_root "$SCRIPT_PATH")"
export PROJECT_ROOT
export FACTORY_ROOT="$PROJECT_ROOT"

API_PORT="${PORT:-8000}"
TUNNEL_MODE="none"   # ngrok | cloudflare | none (use --tunnel to expose)
WITH_COMFYUI=0
NO_BROWSER=0
DETACH=0
NGROK_API_PORT="${NGROK_API_PORT:-4040}"

LOG_DIR="$PROJECT_ROOT/logs"
FASTAPI_LOG="$LOG_DIR/fastapi.log"
TUNNEL_LOG="$LOG_DIR/tunnel.log"
FASTAPI_PID="$LOG_DIR/fastapi.pid"
TUNNEL_PID="$LOG_DIR/tunnel.pid"
NGROK_URL_FILE="$LOG_DIR/ngrok_url.txt"
QUICK_URL_FILE="$LOG_DIR/quick_tunnel_url.txt"

PUBLIC_URL=""
STARTED_FASTAPI=0
STARTED_TUNNEL=0
STARTED_COMFY=0

cleanup() {
  stop_pid_file "$TUNNEL_PID" "tunnel"
  if [[ "$STARTED_FASTAPI" -eq 1 ]]; then
    stop_pid_file "$FASTAPI_PID" "FastAPI"
  fi
  if [[ "$STARTED_COMFY" -eq 1 && -f "$LOG_DIR/comfyui.pid" ]]; then
    stop_pid_file "$LOG_DIR/comfyui.pid" "ComfyUI"
  fi
}

usage() {
  cat <<'EOF'
Usage: start_local_server_mac.sh [options]

  --tunnel ngrok       Expose FastAPI via ngrok (free = random URL)
  --tunnel cloudflare  Cloudflare Quick Tunnel (default if --tunnel omitted)
  --tunnel none
  --no-tunnel          Local only (same as --tunnel none)
  --with-comfyui       Start ComfyUI if not running; wait for :8188 health
  --no-browser         Do not open /health and /docs
  --detach             Start services and exit (no Enter-to-stop; for CI/second terminal)
  --port PORT          FastAPI port (default: 8000)
  -h, --help

Examples:
  ./start_local_server_mac.sh --no-tunnel
  ./start_local_server_mac.sh --tunnel ngrok
  ./start_local_server_mac.sh --tunnel cloudflare --with-comfyui
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tunnel)
      TUNNEL_MODE="${2:-}"
      shift 2
      ;;
    --no-tunnel) TUNNEL_MODE="none"; shift ;;
    --with-comfyui) WITH_COMFYUI=1; shift ;;
    --no-browser) NO_BROWSER=1; shift ;;
    --detach) DETACH=1; shift ;;
    --port) API_PORT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      log_error "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ "$DETACH" -eq 0 ]]; then
  trap cleanup EXIT INT TERM
fi

ensure_logs_dir "$PROJECT_ROOT"
cleanup_jobs_appledouble "$PROJECT_ROOT"
source_project_dotenv "$PROJECT_ROOT/.env"
load_dotenv_exports "$PROJECT_ROOT/ngrok/ngrok.env"

export FACTORY_ROOT="$PROJECT_ROOT"
export PYTHONUNBUFFERED=1

log_info "Project root: $PROJECT_ROOT"
log_info "FACTORY_ROOT=$FACTORY_ROOT"

ensure_python_venv "$PROJECT_ROOT" || exit 1
install_python_deps "$PROJECT_ROOT" || exit 1

LOCAL_HEALTH="http://127.0.0.1:${API_PORT}/health"
LOCAL_DOCS="http://127.0.0.1:${API_PORT}/docs"
BACKEND_DIR="$PROJECT_ROOT/web/backend"

# --- FastAPI ---
if wait_http_ok "$LOCAL_HEALTH" 2; then
  log_ok "FastAPI already running on port $API_PORT"
  log_ok "Health: $(fetch_health_json "$LOCAL_HEALTH")"
else
  if port_in_use "$API_PORT"; then
    log_error "Port $API_PORT is in use but /health failed"
    log_info "Stop with: lsof -ti :$API_PORT | xargs kill"
    exit 1
  fi

  log_info "Starting FastAPI on 127.0.0.1:$API_PORT (cwd=$BACKEND_DIR)"
  : >"$FASTAPI_LOG"
  (
    cd "$BACKEND_DIR"
    export FACTORY_ROOT
    exec python -m uvicorn main:app --host 127.0.0.1 --port "$API_PORT"
  ) >>"$FASTAPI_LOG" 2>&1 &
  echo $! >"$FASTAPI_PID"
  STARTED_FASTAPI=1

  sleep 2
  if ! kill -0 "$(cat "$FASTAPI_PID")" 2>/dev/null; then
    log_error "uvicorn exited immediately. See $FASTAPI_LOG"
    show_log_tail "$FASTAPI_LOG" 40
    exit 1
  fi

  if ! wait_http_ok "$LOCAL_HEALTH" 35; then
    log_error "No response from $LOCAL_HEALTH"
    show_log_tail "$FASTAPI_LOG" 40
    exit 1
  fi
  HEALTH_BODY="$(fetch_health_json "$LOCAL_HEALTH")"
  log_ok "Health check: ${HEALTH_BODY:-ok}"
fi

# --- ComfyUI (optional) ---
if [[ "$WITH_COMFYUI" -eq 1 ]]; then
  COMFY_URL="${COMFYUI_URL:-http://127.0.0.1:8188}"
  if comfyui_health_ok "$COMFY_URL"; then
    log_ok "ComfyUI already running at $COMFY_URL"
  else
    log_info "Starting ComfyUI via scripts/start_comfyui_mac.sh"
    if bash "$SCRIPT_DIR/start_comfyui_mac.sh" --no-browser; then
      STARTED_COMFY=1
    else
      log_warn "ComfyUI start failed — 16-cut generation may not work"
    fi
  fi
fi

# --- Tunnel ---
start_ngrok_tunnel() {
  if ! command -v ngrok >/dev/null 2>&1; then
    log_error "ngrok not in PATH. Run: scripts/setup_ngrok_mac.sh"
    return 1
  fi

  local static_domain=""
  if [[ -n "${NGROK_DOMAIN:-}" ]]; then
    static_domain="${NGROK_DOMAIN}"
    log_info "NGROK_DOMAIN set → static mode (paid plan)"
  elif [[ -n "${NGROK_URL:-}" ]]; then
    # Paid reserved URL: ngrok http --url=https://xxx.ngrok-free.app
    log_info "NGROK_URL set → ngrok http --url=$NGROK_URL"
  else
    log_info "Free ngrok mode (random URL each run)"
  fi

  rm -f "$NGROK_URL_FILE"
  : >"$TUNNEL_LOG"

  local ngrok_args=(http "$API_PORT" --log=stdout)
  if [[ -n "${NGROK_URL:-}" ]]; then
    ngrok_args+=(--url="$NGROK_URL")
  elif [[ -n "$static_domain" ]]; then
    ngrok_args+=(--domain="$static_domain")
  fi
  if [[ -n "${NGROK_REGION:-}" ]]; then
    ngrok_args+=(--region="$NGROK_REGION")
  fi

  nohup ngrok "${ngrok_args[@]}" >>"$TUNNEL_LOG" 2>&1 &
  echo $! >"$TUNNEL_PID"
  STARTED_TUNNEL=1
  sleep 3

  if grep -qE 'ERR_NGROK_313|custom subdomains' "$TUNNEL_LOG" 2>/dev/null; then
    log_warn "ERR_NGROK_313: falling back to free random URL"
    stop_pid_file "$TUNNEL_PID" "ngrok"
    : >"$TUNNEL_LOG"
    nohup ngrok http "$API_PORT" --log=stdout >>"$TUNNEL_LOG" 2>&1 &
    echo $! >"$TUNNEL_PID"
    sleep 2
  fi

  local i url=""
  for ((i = 0; i < 45; i++)); do
    url="$(curl -sf --max-time 2 "http://127.0.0.1:${NGROK_API_PORT}/api/tunnels" 2>/dev/null \
      | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    for t in d.get('tunnels',[]):
        u=t.get('public_url','')
        if u.startswith('https://'):
            print(u.rstrip('/'))
            break
except Exception:
    pass
" 2>/dev/null || true)"
    [[ -n "$url" ]] && break
    sleep 1
  done

  if [[ -z "$url" ]]; then
    log_error "Could not read ngrok public URL from http://127.0.0.1:${NGROK_API_PORT}/api/tunnels"
    show_log_tail "$TUNNEL_LOG" 30
    return 1
  fi

  PUBLIC_URL="$url"
  echo "$PUBLIC_URL" >"$NGROK_URL_FILE"
  log_ok "ngrok public URL: $PUBLIC_URL"
  log_info "Saved: $NGROK_URL_FILE"
  return 0
}

start_cloudflare_quick_tunnel() {
  if ! command -v cloudflared >/dev/null 2>&1; then
    log_error "cloudflared not in PATH. Run: scripts/setup_tunnel_mac.sh"
    return 1
  fi

  rm -f "$QUICK_URL_FILE"
  : >"$TUNNEL_LOG"

  log_info "Starting Cloudflare Quick Tunnel → http://127.0.0.1:$API_PORT"
  nohup cloudflared tunnel --protocol http2 --url "http://127.0.0.1:${API_PORT}" \
    >>"$TUNNEL_LOG" 2>&1 &
  echo $! >"$TUNNEL_PID"
  STARTED_TUNNEL=1

  local url=""
  local i
  for ((i = 0; i < 60; i++)); do
    url="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1 || true)"
    [[ -n "$url" ]] && break
    sleep 1
  done

  if [[ -z "$url" ]]; then
    log_warn "Quick Tunnel URL not detected yet — check $TUNNEL_LOG"
    show_log_tail "$TUNNEL_LOG" 25
    return 0
  fi

  PUBLIC_URL="${url%/}"
  echo "$PUBLIC_URL" >"$QUICK_URL_FILE"
  log_ok "Quick Tunnel URL: $PUBLIC_URL"
  log_info "Saved: $QUICK_URL_FILE"
  log_warn "URL changes every restart — update Vercel API_URL after each run"
  return 0
}

case "$TUNNEL_MODE" in
  ngrok)
    start_ngrok_tunnel || exit 1
    ;;
  cloudflare)
    start_cloudflare_quick_tunnel || true
    ;;
  none)
    log_info "Tunnel disabled (--no-tunnel)"
    ;;
  *)
    log_error "Invalid --tunnel value: $TUNNEL_MODE (use ngrok, cloudflare, none)"
    exit 1
    ;;
esac

# Public health (ngrok interstitial may block curl without header)
if [[ -n "$PUBLIC_URL" ]]; then
  if curl -sf --max-time 5 -H "ngrok-skip-browser-warning: true" "$PUBLIC_URL/health" >/dev/null 2>&1; then
    log_ok "Public health: $PUBLIC_URL/health"
  else
    log_warn "Public health check failed (browser may still work)"
  fi
fi

if [[ "$NO_BROWSER" -eq 0 ]]; then
  open_url "$LOCAL_DOCS"
  open_url "$LOCAL_HEALTH"
  if [[ -n "$PUBLIC_URL" ]]; then
    open_url "$PUBLIC_URL/health"
  fi
fi

echo
echo "========================================"
log_ok "Local API:  http://127.0.0.1:$API_PORT"
log_ok "Health:     $LOCAL_HEALTH"
log_ok "Docs:       $LOCAL_DOCS"
if [[ -n "$PUBLIC_URL" ]]; then
  log_ok "Public URL: $PUBLIC_URL"
  echo
  log_info "Vercel Environment Variable:"
  echo "  API_URL=$PUBLIC_URL"
  echo "  (no trailing slash; redeploy after URL changes)"
fi
log_info "Logs: $FASTAPI_LOG, $TUNNEL_LOG"
if [[ "$WITH_COMFYUI" -eq 1 ]]; then
  log_info "ComfyUI log: $LOG_DIR/comfyui.log"
fi
echo "========================================"
if [[ "$DETACH" -eq 1 ]] || [[ ! -t 0 ]]; then
  log_info "Services left running (PID files in logs/). Stop manually or re-run with Enter in foreground."
  if [[ "$DETACH" -eq 1 ]]; then
    echo "  kill \$(cat $FASTAPI_PID 2>/dev/null)  # FastAPI"
    [[ "$STARTED_TUNNEL" -eq 1 ]] && echo "  kill \$(cat $TUNNEL_PID 2>/dev/null)   # tunnel"
    [[ "$STARTED_COMFY" -eq 1 ]] && echo "  kill \$(cat $LOG_DIR/comfyui.pid 2>/dev/null)  # ComfyUI"
  fi
  trap - EXIT INT TERM
  exit 0
fi

log_info "Press Enter to stop services started by this script"
read -r _

# trap runs cleanup on exit
log_ok "Shutdown complete"
