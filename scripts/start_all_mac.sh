#!/usr/bin/env bash
# One-click Mac stack: ComfyUI + FastAPI + ngrok (Finder launcher backend).

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
# shellcheck source=common_mac.sh
source "$SCRIPT_DIR/common_mac.sh"

PROJECT_ROOT="$(resolve_project_root "$SCRIPT_PATH")"
export PROJECT_ROOT
export FACTORY_ROOT="$PROJECT_ROOT"

API_PORT="${PORT:-8000}"
COMFY_PORT="${COMFYUI_PORT:-8188}"
COMFY_HOST="${COMFYUI_HOST:-127.0.0.1}"
COMFY_URL="${COMFYUI_URL:-http://${COMFY_HOST}:${COMFY_PORT}}"
NGROK_API_PORT="${NGROK_API_PORT:-4040}"

LOG_DIR="$PROJECT_ROOT/logs"
FASTAPI_LOG="$LOG_DIR/fastapi.log"
COMFY_LOG="$LOG_DIR/comfyui.log"
NGROK_LOG="$LOG_DIR/ngrok.log"
FASTAPI_PID="$LOG_DIR/fastapi.pid"
NGROK_PID="$LOG_DIR/ngrok.pid"
COMFY_PID="$LOG_DIR/comfyui.pid"
NGROK_URL_FILE="$LOG_DIR/ngrok_url.txt"

LOCAL_HEALTH="http://127.0.0.1:${API_PORT}/health"
LOCAL_DOCS="http://127.0.0.1:${API_PORT}/docs"
BACKEND_DIR="$PROJECT_ROOT/web/backend"

OPEN_LOG_TABS="${OPEN_LOG_TABS:-1}"
PUBLIC_URL=""

ensure_launcher_executable() {
  local root="$PROJECT_ROOT"
  local need=0
  for f in "$root/start_all.command" "$root/stop_all.command" \
    "$root/scripts/start_all_mac.sh" "$root/scripts/stop_all_mac.sh" \
    "$root/scripts/start_comfyui_mac.sh" "$root/scripts/start_local_server_mac.sh" \
    "$root/scripts/common_mac.sh"; do
    [[ -f "$f" ]] || continue
    if [[ ! -x "$f" ]]; then
      chmod +x "$f" 2>/dev/null || true
      need=1
    fi
  done
  if [[ "$need" -eq 1 ]]; then
    log_warn "Some scripts were not executable — ran chmod +x automatically."
    log_info "If Finder still blocks launch: right-click → Open, or run:"
    echo "  chmod +x \"$root/start_all.command\" \"$root/stop_all.command\""
  fi
}

cleanup_stale_pids() {
  log_info "Cleaning stale PID files from previous runs"
  bash "$SCRIPT_DIR/stop_all_mac.sh" || true
}

read_ngrok_public_url() {
  curl -sf --max-time 2 "http://127.0.0.1:${NGROK_API_PORT}/api/tunnels" 2>/dev/null \
    | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    for t in d.get('tunnels', []):
        u = t.get('public_url', '')
        if u.startswith('https://'):
            print(u.rstrip('/'))
            break
except Exception:
    pass
" 2>/dev/null || true
}

start_fastapi() {
  if wait_http_ok "$LOCAL_HEALTH" 2; then
    log_ok "FastAPI already running on port $API_PORT"
    return 0
  fi
  if port_in_use "$API_PORT"; then
    log_error "Port $API_PORT is in use but /health failed"
    return 1
  fi

  ensure_python_venv "$PROJECT_ROOT" || return 1
  install_python_deps "$PROJECT_ROOT" || return 1

  log_info "Starting FastAPI on 127.0.0.1:$API_PORT"
  : >"$FASTAPI_LOG"
  (
    cd "$BACKEND_DIR"
    export FACTORY_ROOT="$PROJECT_ROOT"
    export PYTHONUNBUFFERED=1
    exec python -m uvicorn main:app --host 127.0.0.1 --port "$API_PORT"
  ) >>"$FASTAPI_LOG" 2>&1 &
  echo $! >"$FASTAPI_PID"

  sleep 2
  if ! kill -0 "$(cat "$FASTAPI_PID")" 2>/dev/null; then
    log_error "uvicorn exited — see $FASTAPI_LOG"
    show_log_tail "$FASTAPI_LOG" 40
    return 1
  fi
  if ! wait_http_ok "$LOCAL_HEALTH" 40; then
    log_error "FastAPI health timeout: $LOCAL_HEALTH"
    show_log_tail "$FASTAPI_LOG" 40
    return 1
  fi
  log_ok "FastAPI health OK"
  return 0
}

start_ngrok() {
  if [[ -f "$NGROK_PID" ]] && kill -0 "$(cat "$NGROK_PID" 2>/dev/null)" 2>/dev/null; then
    PUBLIC_URL="$(read_ngrok_public_url)"
    if [[ -n "$PUBLIC_URL" ]]; then
      log_ok "ngrok already running: $PUBLIC_URL"
      echo "$PUBLIC_URL" >"$NGROK_URL_FILE"
      return 0
    fi
  fi

  if ! command -v ngrok >/dev/null 2>&1; then
    log_error "ngrok not in PATH. Run: scripts/setup_ngrok_mac.sh"
    return 1
  fi

  rm -f "$NGROK_URL_FILE" "$LOG_DIR/tunnel.pid"
  : >"$NGROK_LOG"

  local ngrok_args=(http "$API_PORT" --log=stdout)
  if [[ -n "${NGROK_URL:-}" ]]; then
    ngrok_args+=(--url="$NGROK_URL")
  elif [[ -n "${NGROK_DOMAIN:-}" ]]; then
    ngrok_args+=(--domain="$NGROK_DOMAIN")
  fi
  if [[ -n "${NGROK_REGION:-}" ]]; then
    ngrok_args+=(--region="$NGROK_REGION")
  fi

  log_info "Starting ngrok → http://127.0.0.1:$API_PORT"
  nohup ngrok "${ngrok_args[@]}" >>"$NGROK_LOG" 2>&1 &
  echo $! >"$NGROK_PID"
  echo $! >"$LOG_DIR/tunnel.pid"

  sleep 3
  if grep -qE 'ERR_NGROK_313|custom subdomains' "$NGROK_LOG" 2>/dev/null; then
    log_warn "ERR_NGROK_313 — retrying free random URL"
    stop_pid_file "$NGROK_PID" "ngrok"
    : >"$NGROK_LOG"
    nohup ngrok http "$API_PORT" --log=stdout >>"$NGROK_LOG" 2>&1 &
    echo $! >"$NGROK_PID"
    sleep 2
  fi

  local i url=""
  for ((i = 0; i < 45; i++)); do
    url="$(read_ngrok_public_url)"
    [[ -n "$url" ]] && break
    sleep 1
  done

  if [[ -z "$url" ]]; then
    log_error "Could not read ngrok public URL (API :$NGROK_API_PORT)"
    show_log_tail "$NGROK_LOG" 30
    return 1
  fi

  PUBLIC_URL="$url"
  echo "$PUBLIC_URL" >"$NGROK_URL_FILE"
  log_ok "ngrok public URL: $PUBLIC_URL"
  return 0
}

start_comfyui_if_needed() {
  if comfyui_health_ok "$COMFY_URL"; then
    log_ok "ComfyUI already running at $COMFY_URL"
    return 0
  fi
  log_info "ComfyUI not responding — starting via scripts/start_comfyui_mac.sh"
  bash "$SCRIPT_DIR/start_comfyui_mac.sh" --no-browser
}

open_log_terminal_tab() {
  local title="$1"
  local log_file="$2"
  local tab_script="$LOG_DIR/.launcher_tab_${title// /_}.sh"
  mkdir -p "$LOG_DIR"
  cat >"$tab_script" <<EOF
#!/usr/bin/env bash
cd "$(printf '%q' "$PROJECT_ROOT")"
clear
echo "=== KakaoEmoticonFactory — $title ==="
echo "Log: $log_file"
echo "Press Ctrl+C to stop tail only (service keeps running)."
echo
if [[ -f "$log_file" ]]; then
  tail -n 30 -f "$log_file"
else
  echo "Waiting for log file..."
  while [[ ! -f "$log_file" ]]; do sleep 1; done
  tail -n 30 -f "$log_file"
fi
EOF
  chmod +x "$tab_script"
  local q_script
  q_script="$(printf '%q' "$tab_script")"
  osascript <<APPLESCRIPT 2>/dev/null || true
tell application "Terminal"
  activate
  if (count of windows) is greater than 0 then
    tell application "System Events" to tell process "Terminal" to keystroke "t" using command down
    delay 0.35
  end if
  do script "bash $q_script" in front window
end tell
APPLESCRIPT
}

open_log_tabs() {
  [[ "$OPEN_LOG_TABS" == "1" ]] || return 0
  command -v osascript >/dev/null 2>&1 || return 0
  log_info "Opening log tail tabs in Terminal (ComfyUI / FastAPI / ngrok)"
  open_log_terminal_tab "ComfyUI" "$COMFY_LOG"
  sleep 0.4
  open_log_terminal_tab "FastAPI" "$FASTAPI_LOG"
  sleep 0.4
  open_log_terminal_tab "ngrok" "$NGROK_LOG"
}

print_status_block() {
  local health_body comfy_ok ngrok_line
  health_body="$(fetch_health_json "$LOCAL_HEALTH")"
  if comfyui_health_ok "$COMFY_URL"; then
    comfy_ok="OK ($COMFY_URL)"
  else
    comfy_ok="not responding ($COMFY_URL)"
  fi
  if [[ -n "$PUBLIC_URL" ]]; then
    ngrok_line="$PUBLIC_URL"
  elif [[ -f "$NGROK_URL_FILE" ]]; then
    ngrok_line="$(cat "$NGROK_URL_FILE" 2>/dev/null || echo n/a)"
  else
    ngrok_line="(not started)"
  fi

  echo
  echo "========================================"
  echo " KakaoEmoticonFactory — stack ready"
  echo "========================================"
  echo " API (local):   http://127.0.0.1:${API_PORT}"
  echo " API docs:      $LOCAL_DOCS"
  echo " Health:        $LOCAL_HEALTH"
  echo " Health body:   ${health_body:-n/a}"
  echo " ComfyUI:       $comfy_ok"
  echo " ngrok URL:     $ngrok_line"
  if [[ -n "$ngrok_line" && "$ngrok_line" != "(not started)" ]]; then
    echo " Public health: ${ngrok_line}/health"
    echo
    echo " Vercel API_URL=$ngrok_line"
  fi
  echo
  echo " PID files: $LOG_DIR/{fastapi,ngrok,comfyui}.pid"
  echo " Logs:      $FASTAPI_LOG, $COMFY_LOG, $NGROK_LOG"
  echo " Stop all:  ./stop_all.command"
  echo "========================================"
  echo
}

log_tail_menu() {
  while true; do
    echo "Log tail menu (services keep running):"
    echo "  1) FastAPI   ($FASTAPI_LOG)"
    echo "  2) ComfyUI   ($COMFY_LOG)"
    echo "  3) ngrok     ($NGROK_LOG)"
    echo "  4) Refresh status"
    echo "  5) Open API docs + ComfyUI in browser"
    echo "  q) Quit this window (servers stay up)"
    echo -n "Choice: "
    local choice=""
    read -r choice || choice="q"
    case "$choice" in
      1) show_log_tail "$FASTAPI_LOG" 50 ;;
      2) show_log_tail "$COMFY_LOG" 50 ;;
      3) show_log_tail "$NGROK_LOG" 50 ;;
      4) print_status_block ;;
      5)
        open_url "$LOCAL_DOCS"
        open_url "$COMFY_URL"
        ;;
      q|Q) log_info "Launcher window closed. Use stop_all.command to shut down services."; break ;;
      *) log_warn "Unknown choice: $choice" ;;
    esac
    echo
  done
}

main() {
  ensure_logs_dir "$PROJECT_ROOT"
  ensure_launcher_executable
  cleanup_stale_pids
  cleanup_jobs_appledouble "$PROJECT_ROOT"
  source_project_dotenv "$PROJECT_ROOT/.env"
  load_dotenv_exports "$PROJECT_ROOT/ngrok/ngrok.env"

  log_info "Project root: $PROJECT_ROOT"

  start_comfyui_if_needed
  start_fastapi
  start_ngrok

  open_url "$LOCAL_DOCS"
  open_url "$COMFY_URL"

  if [[ -f "$NGROK_URL_FILE" ]]; then
    PUBLIC_URL="$(cat "$NGROK_URL_FILE" 2>/dev/null || true)"
    [[ -n "$PUBLIC_URL" ]] && open_url "${PUBLIC_URL}/health"
  fi

  print_status_block
  open_log_tabs

  if [[ -t 0 ]]; then
    log_tail_menu
  else
    log_info "Non-interactive run — services left running in background."
  fi
}

main "$@"
