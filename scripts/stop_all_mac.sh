#!/usr/bin/env bash
# Stop ComfyUI, FastAPI, and ngrok started by start_all_mac.sh / start_all.command.

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
# shellcheck source=common_mac.sh
source "$SCRIPT_DIR/common_mac.sh"

PROJECT_ROOT="$(resolve_project_root "$SCRIPT_PATH")"
LOG_DIR="$PROJECT_ROOT/logs"

API_PORT="${PORT:-8000}"
COMFY_PORT="${COMFYUI_PORT:-8188}"
NGROK_API_PORT="${NGROK_API_PORT:-4040}"

stop_pid_file "$LOG_DIR/fastapi.pid" "FastAPI"
stop_pid_file "$LOG_DIR/ngrok.pid" "ngrok"
stop_pid_file "$LOG_DIR/tunnel.pid" "tunnel (legacy)"
stop_pid_file "$LOG_DIR/comfyui.pid" "ComfyUI"

# Orphan listeners on default ports (only if pid file missing)
if command -v lsof >/dev/null 2>&1; then
  for port in "$API_PORT" "$COMFY_PORT"; do
    pids="$(pids_on_port "$port" 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      while read -r pid; do
        [[ -z "$pid" ]] && continue
        log_info "Stopping listener on :$port (PID $pid)"
        kill "$pid" 2>/dev/null || true
        sleep 0.5
        kill -9 "$pid" 2>/dev/null || true
      done <<<"$pids"
    fi
  done
fi

rm -f "$LOG_DIR/ngrok_url.txt" "$LOG_DIR/quick_tunnel_url.txt" 2>/dev/null || true

log_ok "All launcher services stopped (FastAPI :$API_PORT, ComfyUI :$COMFY_PORT, ngrok)"
log_info "Logs kept under: $LOG_DIR"
