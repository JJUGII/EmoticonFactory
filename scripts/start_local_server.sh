#!/usr/bin/env bash
# Mac: FastAPI 로컬 서버 + Cloudflare 터널 시작 스크립트
# 사용법: bash scripts/start_local_server.sh [--port 8000] [--no-tunnel] [--no-browser]
set -euo pipefail

PORT=8000
NO_TUNNEL=false
NO_BROWSER=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --port) PORT="$2"; shift 2 ;;
        --no-tunnel) NO_TUNNEL=true; shift ;;
        --no-browser) NO_BROWSER=true; shift ;;
        *) echo "[WARN] 알 수 없는 옵션: $1" >&2; shift ;;
    esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/web/backend"
VENV_ACTIVATE="$ROOT/.venv/bin/activate"
LOG_DIR="$ROOT/logs"
API_LOG_OUT="$LOG_DIR/fastapi.out.log"
API_LOG_ERR="$LOG_DIR/fastapi.err.log"
CF_LOG_OUT="$LOG_DIR/cloudflared.out.log"
CF_LOG_ERR="$LOG_DIR/cloudflared.err.log"
QUICK_URL_FILE="$LOG_DIR/quick_tunnel_url.txt"
CF_ENV="$ROOT/cloudflare/tunnel.env"
CF_CONFIG="$ROOT/cloudflare/config.yml"

info()  { printf '\033[36m[INFO]\033[0m %s\n' "$*"; }
ok()    { printf '\033[32m[OK]  \033[0m %s\n' "$*"; }
warn()  { printf '\033[33m[WARN]\033[0m %s\n' "$*"; }
err()   { printf '\033[31m[ERROR]\033[0m %s\n' "$*" >&2; }

mkdir -p "$LOG_DIR"
mkdir -p "$ROOT/web/jobs"

# venv 확인
if [[ ! -f "$VENV_ACTIVATE" ]]; then
    err ".venv 없음. 먼저 아래를 실행하세요:"
    err "  cd $ROOT"
    err "  python3 -m venv .venv"
    err "  source .venv/bin/activate"
    err "  pip install -r requirements.txt"
    err "  pip install -r web/backend/requirements.txt"
    exit 1
fi

# exFAT 호환: pip 스크립트 대신 python -m pip 사용
VENV_PYTHON="$ROOT/.venv/bin/python"
PIP="$VENV_PYTHON -m pip"

info "web/backend 의존성 설치 중..."
$PIP install -q -r "$BACKEND/requirements.txt"

# 포트 충돌 확인
if lsof -i ":$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    err "포트 $PORT 이미 사용 중. 확인: lsof -i :$PORT"
    exit 1
fi

export FACTORY_ROOT="$ROOT"
export PYTHONUNBUFFERED=1

info "FastAPI 시작 중 (127.0.0.1:$PORT)..."
(cd "$BACKEND" && python -m uvicorn main:app --host 127.0.0.1 --port "$PORT") \
    >"$API_LOG_OUT" 2>"$API_LOG_ERR" &
API_PID=$!

# 헬스체크 대기
HEALTH_OK=false
for i in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        HEALTH_OK=true
        HEALTH=$(curl -s "http://127.0.0.1:$PORT/health" 2>/dev/null || echo "ok")
        ok "FastAPI 응답: $HEALTH"
        break
    fi
    sleep 0.5
done

if [[ "$HEALTH_OK" = false ]]; then
    err "http://127.0.0.1:$PORT/health 응답 없음 (30초 타임아웃)"
    echo "--- FastAPI stdout (마지막 20줄) ---"
    tail -20 "$API_LOG_OUT" 2>/dev/null || true
    echo "--- FastAPI stderr (마지막 20줄) ---"
    tail -20 "$API_LOG_ERR" 2>/dev/null || true
    kill "$API_PID" 2>/dev/null || true
    exit 1
fi

# Cloudflare 터널
TUNNEL_PID=""
PUBLIC_URL="http://127.0.0.1:$PORT"

if [[ "$NO_TUNNEL" = false ]]; then
    if ! command -v cloudflared >/dev/null 2>&1; then
        warn "cloudflared 없음 → 터널 없이 로컬 전용으로 실행합니다."
        warn "설치: brew install cloudflared"
        NO_TUNNEL=true
    fi
fi

if [[ "$NO_TUNNEL" = false ]]; then
    # named tunnel 여부 확인
    TUNNEL_HOST=""
    if [[ -f "$CF_ENV" ]]; then
        TUNNEL_HOST=$(grep -E '^\s*TUNNEL_HOSTNAME=' "$CF_ENV" 2>/dev/null \
            | head -1 | cut -d= -f2 | tr -d '"' | tr -d "'" | xargs 2>/dev/null || true)
    fi

    USE_QUICK_TUNNEL=true
    if [[ -n "$TUNNEL_HOST" ]] && ! echo "$TUNNEL_HOST" | grep -qiE 'YOUR-DOMAIN|example\.com|yourdomain'; then
        USE_QUICK_TUNNEL=false
    fi

    if [[ "$USE_QUICK_TUNNEL" = true ]]; then
        info "Cloudflare Quick Tunnel 시작 중..."
        rm -f "$QUICK_URL_FILE"
        cloudflared tunnel --url "http://127.0.0.1:$PORT" \
            >"$CF_LOG_OUT" 2>"$CF_LOG_ERR" &
        TUNNEL_PID=$!

        for i in $(seq 1 45); do
            QUICK_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' \
                "$CF_LOG_OUT" "$CF_LOG_ERR" 2>/dev/null | head -1 || true)
            if [[ -n "$QUICK_URL" ]]; then
                PUBLIC_URL="$QUICK_URL"
                echo "$PUBLIC_URL" > "$QUICK_URL_FILE"
                ok "Quick Tunnel URL: $PUBLIC_URL"
                warn "무료 플랜: 재시작마다 URL이 바뀝니다. logs/quick_tunnel_url.txt 참고"
                break
            fi
            sleep 1
        done
        if [[ "$PUBLIC_URL" = "http://127.0.0.1:$PORT" ]]; then
            warn "Quick Tunnel URL을 읽지 못했습니다. logs/cloudflared.*.log 확인"
        fi
    else
        PROTOCOL="${TUNNEL_PROTOCOL:-http2}"
        info "Named Tunnel 시작 중 (protocol=$PROTOCOL)..."
        cloudflared tunnel --config "$CF_CONFIG" --protocol "$PROTOCOL" run \
            >"$CF_LOG_OUT" 2>"$CF_LOG_ERR" &
        TUNNEL_PID=$!
        PUBLIC_URL="https://$TUNNEL_HOST"
        sleep 3
        ok "Named Tunnel: $PUBLIC_URL"
    fi
fi

# 브라우저 열기
if [[ "$NO_BROWSER" = false ]]; then
    open "http://127.0.0.1:$PORT/docs" 2>/dev/null || true
fi

echo ""
echo "========================================"
ok "로컬 API:   http://127.0.0.1:$PORT"
ok "Swagger UI: http://127.0.0.1:$PORT/docs"
if [[ "$PUBLIC_URL" != "http://127.0.0.1:$PORT" ]]; then
    ok "공개 URL:   $PUBLIC_URL"
    info "Vercel에서 API_URL=$PUBLIC_URL 로 설정 후 재배포"
fi
info "로그: logs/fastapi.*.log, logs/cloudflared.*.log"
info "종료: Ctrl+C"
echo "========================================"

# 종료 시 정리
cleanup() {
    echo ""
    info "종료 중..."
    if [[ -n "$TUNNEL_PID" ]]; then
        kill "$TUNNEL_PID" 2>/dev/null && ok "cloudflared 종료" || true
    fi
    kill "$API_PID" 2>/dev/null && ok "FastAPI 종료" || true
}
trap cleanup EXIT INT TERM

wait "$API_PID" 2>/dev/null || true
