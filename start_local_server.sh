#!/usr/bin/env bash
# Mac: Cloudflare 터널로 서버 시작 (루트 래퍼)
set -euo pipefail
cd "$(dirname "$0")"
exec bash scripts/start_local_server.sh "$@"
