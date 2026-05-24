#!/usr/bin/env bash
# Cloudflare Tunnel setup helper for macOS (quick tunnel + named tunnel pointers).

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
# shellcheck source=common_mac.sh
source "$SCRIPT_DIR/common_mac.sh"

PROJECT_ROOT="$(resolve_project_root "$SCRIPT_PATH")"
CF_DIR="$PROJECT_ROOT/cloudflare"
CF_ENV="$CF_DIR/tunnel.env"
CF_ENV_EXAMPLE="$CF_DIR/tunnel.env.example"

echo "========================================"
echo " Cloudflare Tunnel setup (macOS)"
echo "========================================"
echo

if ! command -v brew >/dev/null 2>&1; then
  log_warn "Homebrew not found. Install cloudflared from:"
  echo "  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
else
  if ! command -v cloudflared >/dev/null 2>&1; then
    log_info "Install cloudflared:"
    echo "  brew install cloudflared"
    echo
  else
    log_ok "cloudflared found: $(command -v cloudflared) ($(cloudflared --version 2>/dev/null | head -1 || true))"
  fi
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  exit 1
fi

echo "--- Quick Tunnel (no domain, free) ---"
log_info "Used automatically by:"
echo "  ./start_local_server_mac.sh --tunnel cloudflare"
echo
echo "Command equivalent:"
echo "  cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000"
echo
log_warn "URL changes every restart → update Vercel API_URL from logs/quick_tunnel_url.txt"
echo

echo "--- Named Tunnel (your domain on Cloudflare) ---"
mkdir -p "$CF_DIR"
if [[ ! -f "$CF_ENV" && -f "$CF_ENV_EXAMPLE" ]]; then
  cp "$CF_ENV_EXAMPLE" "$CF_ENV"
  log_ok "Created $CF_ENV — edit TUNNEL_HOSTNAME then run Windows setup or:"
  echo "  cloudflared tunnel login"
  echo "  cloudflared tunnel create emiticon-api"
  echo "  cloudflared tunnel route dns emiticon-api api.yourdomain.com"
fi
log_info "Windows one-shot setup (same repo): setup_cloudflare_tunnel.bat"
log_info "Or copy cloudflare/config.yml from a machine already configured."
echo
log_info "Start with named config when ready:"
echo "  ./start_local_server_mac.sh --tunnel cloudflare"
echo "  (uses cloudflare/config.yml when tunnel.env has a real hostname)"
