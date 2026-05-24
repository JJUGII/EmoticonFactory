#!/usr/bin/env bash
# Start ComfyUI on macOS (127.0.0.1:8188). venv + requirements + launch in one step.

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
# shellcheck source=common_mac.sh
source "$SCRIPT_DIR/common_mac.sh"

PROJECT_ROOT="$(resolve_project_root "$SCRIPT_PATH")"
export PROJECT_ROOT
export FACTORY_ROOT="$PROJECT_ROOT"

COMFY_PORT="${COMFYUI_PORT:-8188}"
COMFY_HOST="${COMFYUI_HOST:-127.0.0.1}"
COMFY_URL="${COMFYUI_URL:-http://${COMFY_HOST}:${COMFY_PORT}}"
LOG_DIR="$PROJECT_ROOT/logs"
COMFY_LOG="$LOG_DIR/comfyui.log"
COMFY_PIP_LOG="$LOG_DIR/comfyui_pip.log"
PID_FILE="$LOG_DIR/comfyui.pid"
FOREGROUND=0
NO_BROWSER=0
SKIP_INSTALL=0
FORCE_INSTALL=0

usage() {
  cat <<'EOF'
Usage: scripts/start_comfyui_mac.sh [options]

  --foreground       Run in foreground (default: background + log)
  --no-browser       Do not open ComfyUI in browser
  --skip-install     Skip python -m pip install (venv activate only)
  --force-install    Reinstall requirements.txt even if deps look OK
  --port PORT        Listen port (default: 8188)
  -h, --help         Show help

Environment:
  COMFYUI_DIR        Path to ComfyUI (default: ../ComfyUI next to factory)
  COMFYUI_URL        Base URL for health check

Notes:
  Always use python -m pip (never the pip executable on exFAT volumes).
  Prefer ComfyUI on APFS (~/ComfyUI) over exFAT external drives.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --foreground) FOREGROUND=1; shift ;;
    --no-browser) NO_BROWSER=1; shift ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    --force-install) FORCE_INSTALL=1; shift ;;
    --port) COMFY_PORT="$2"; COMFY_URL="http://${COMFY_HOST}:${COMFY_PORT}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) log_error "Unknown option: $1"; usage; exit 1 ;;
  esac
done

load_dotenv_exports "$PROJECT_ROOT/.env"
ensure_logs_dir "$PROJECT_ROOT"

if comfyui_health_ok "$COMFY_URL"; then
  log_ok "ComfyUI already running at $COMFY_URL"
  [[ "$NO_BROWSER" -eq 0 ]] && open_url "$COMFY_URL"
  exit 0
fi

if pids_on_port "$COMFY_PORT" | grep -q .; then
  log_error "Port $COMFY_PORT is in use but health check failed at $COMFY_URL"
  exit 1
fi

COMFY_DIR=""
if ! COMFY_DIR="$(find_comfyui_dir)"; then
  log_error "ComfyUI not found. Set COMFYUI_DIR in .env or install under ~/ComfyUI"
  log_info "Candidates: ../ComfyUI, ~/ComfyUI, ~/Documents/ComfyUI, ~/Projects/ComfyUI"
  exit 1
fi

export COMFYUI_DIR="$COMFY_DIR"
log_info "ComfyUI directory: $COMFY_DIR"
warn_if_exfat_path "$COMFY_DIR" "ComfyUI" || true

ensure_comfyui_venv "$COMFY_DIR" || exit 1
log_ok "venv active: ${VIRTUAL_ENV:-unknown}"
log_info "Use: python -m pip ... (pip executable may fail on exFAT)"

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  if [[ "$FORCE_INSTALL" -eq 1 ]]; then
    install_comfyui_deps "$COMFY_DIR" "$COMFY_PIP_LOG" || exit 1
  elif python -c "import sqlalchemy" 2>/dev/null; then
    log_ok "requirements satisfied (sqlalchemy present); use --force-install to reinstall"
    strip_appledouble_in_venv "${VIRTUAL_ENV:-}"
  else
    log_info "Installing ComfyUI requirements (first run or incomplete venv)"
    install_comfyui_deps "$COMFY_DIR" "$COMFY_PIP_LOG" || exit 1
  fi
else
  log_info "Skipping pip install (--skip-install)"
  if ! python -c "import sqlalchemy" 2>/dev/null; then
    log_error "sqlalchemy missing — run without --skip-install"
    exit 1
  fi
fi

cd "$COMFY_DIR"
CMD=(python main.py --listen "$COMFY_HOST" --port "$COMFY_PORT")

if [[ "$FOREGROUND" -eq 1 ]]; then
  log_info "Starting ComfyUI (foreground): ${CMD[*]}"
  exec "${CMD[@]}"
fi

log_info "Starting ComfyUI (background): ${CMD[*]}"
: >"$COMFY_LOG"
nohup "${CMD[@]}" >>"$COMFY_LOG" 2>&1 &
echo $! >"$PID_FILE"

if wait_http_ok "$COMFY_URL" 90; then
  log_ok "ComfyUI health OK: $COMFY_URL"
  if grep -q 'Starting server' "$COMFY_LOG" 2>/dev/null; then
    log_ok "Server log: Starting server"
    grep 'To see the GUI go to:' "$COMFY_LOG" 2>/dev/null | tail -1 || true
  fi
else
  log_warn "ComfyUI may still be starting (first boot can take 1–2 min on exFAT)"
  show_log_tail "$COMFY_LOG" 40
  exit 1
fi

[[ "$NO_BROWSER" -eq 0 ]] && open_url "$COMFY_URL"
log_info "Log: $COMFY_LOG  pip log: $COMFY_PIP_LOG  PID: $(cat "$PID_FILE" 2>/dev/null || echo n/a)"
