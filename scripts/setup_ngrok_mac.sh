#!/usr/bin/env bash
# ngrok setup helper for macOS (install check + authtoken guidance).

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
# shellcheck source=common_mac.sh
source "$SCRIPT_DIR/common_mac.sh"

PROJECT_ROOT="$(resolve_project_root "$SCRIPT_PATH")"
NGROK_ENV="$PROJECT_ROOT/ngrok/ngrok.env"
NGROK_ENV_EXAMPLE="$PROJECT_ROOT/ngrok/ngrok.env.example"

echo "========================================"
echo " ngrok setup (macOS)"
echo "========================================"
echo

if ! command -v brew >/dev/null 2>&1; then
  log_warn "Homebrew not found. Install from https://brew.sh or download ngrok manually."
else
  if ! command -v ngrok >/dev/null 2>&1; then
    log_info "Install ngrok via Homebrew:"
    echo "  brew install ngrok/ngrok/ngrok"
    echo
  else
    log_ok "ngrok found: $(command -v ngrok) ($(ngrok version 2>/dev/null | head -1 || true))"
  fi
fi

if ! command -v ngrok >/dev/null 2>&1; then
  log_info "Alternative: https://ngrok.com/download"
  exit 1
fi

log_info "Configure authtoken (one-time):"
echo "  1) Sign up: https://dashboard.ngrok.com/signup"
echo "  2) Token:    https://dashboard.ngrok.com/get-started/your-authtoken"
echo "  3) Run:      ngrok config add-authtoken YOUR_TOKEN"
echo
log_warn "Free plan: do NOT set NGROK_DOMAIN / NGROK_URL (random URL each run)."
log_info "Paid plan only: fixed domain via NGROK_DOMAIN in ngrok/ngrok.env"
echo

mkdir -p "$PROJECT_ROOT/ngrok"
if [[ ! -f "$NGROK_ENV" && -f "$NGROK_ENV_EXAMPLE" ]]; then
  cp "$NGROK_ENV_EXAMPLE" "$NGROK_ENV"
  log_ok "Created $NGROK_ENV from example"
fi

if [[ -f "$HOME/Library/Application Support/ngrok/ngrok.yml" ]]; then
  if grep -q 'authtoken:' "$HOME/Library/Application Support/ngrok/ngrok.yml" 2>/dev/null; then
    log_ok "ngrok authtoken appears configured in ngrok.yml"
  fi
elif [[ -f "$HOME/.ngrok2/ngrok.yml" ]]; then
  if grep -q 'authtoken:' "$HOME/.ngrok2/ngrok.yml" 2>/dev/null; then
    log_ok "ngrok authtoken appears configured (legacy path)"
  fi
else
  log_warn "No ngrok.yml found yet — run ngrok config add-authtoken"
fi

echo
log_info "Start API + tunnel:"
echo "  ./start_local_server_mac.sh --tunnel ngrok"
echo
log_info "Public URL saved to: logs/ngrok_url.txt"
