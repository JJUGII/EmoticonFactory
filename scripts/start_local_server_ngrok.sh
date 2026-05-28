#!/usr/bin/env bash
# Mac: FastAPI 로컬 서버 + ngrok 터널 시작 스크립트
# 사용법: bash scripts/start_local_server_ngrok.sh [--port 8000] [--no-ngrok] [--no-browser]
set -euo pipefail

PORT=8000
NGROK_API_PORT=4040
NO_NGROK=false
NO_BROWSER=false
FORCE_RESTART=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --port) PORT="$2"; shift 2 ;;
        --ngrok-api-port) NGROK_API_PORT="$2"; shift 2 ;;
        --no-ngrok) NO_NGROK=true; shift ;;
        --no-browser) NO_BROWSER=true; shift ;;
        --force-restart) FORCE_RESTART=true; shift ;;
        *) echo "[WARN] 알 수 없는 옵션: $1" >&2; shift ;;
    esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/web/backend"
VENV_ACTIVATE="$ROOT/.venv/bin/activate"
LOG_DIR="$ROOT/logs"
API_LOG_OUT="$LOG_DIR/fastapi.out.log"
API_LOG_ERR="$LOG_DIR/fastapi.err.log"
NGROK_LOG_OUT="$LOG_DIR/ngrok.out.log"
NGROK_LOG_ERR="$LOG_DIR/ngrok.err.log"
NGROK_URL_FILE="$LOG_DIR/ngrok_url.txt"
NGROK_ENV="$ROOT/ngrok/ngrok.env"

info()  { printf '\033[36m[INFO]\033[0m %s\n' "$*"; }
ok()    { printf '\033[32m[OK]  \033[0m %s\n' "$*"; }
warn()  { printf '\033[33m[WARN]\033[0m %s\n' "$*"; }
err()   { printf '\033[31m[ERROR]\033[0m %s\n' "$*" >&2; }

mkdir -p "$LOG_DIR"
mkdir -p "$ROOT/web/jobs"
mkdir -p "$ROOT/ngrok"

# .env 및 ngrok.env 로드
load_env() {
    local file="$1"
    [[ -f "$file" ]] || return 0
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"
        [[ "$line" =~ = ]] || continue
        key="${line%%=*}"
        val="${line#*=}"
        key="$(echo "$key" | xargs)"
        val="$(echo "$val" | xargs | tr -d '"' | tr -d "'")"
        case "$key" in
            NGROK_DOMAIN)    [[ -n "$val" ]] && NGROK_DOMAIN="$val" ;;
            NGROK_AUTHTOKEN) [[ -n "$val" ]] && export NGROK_AUTHTOKEN="$val" ;;
            NGROK_REGION)    [[ -n "$val" ]] && export NGROK_REGION="$val" ;;
        esac
    done < "$file"
}

NGROK_DOMAIN=""
load_env "$ROOT/.env"
load_env "$NGROK_ENV"

# venv 확인
if [[ ! -f "$VENV_ACTIVATE" ]]; then
    err ".venv 없음. setup.sh 를 먼저 실행하세요."
    exit 1
fi

# exFAT 호환: pip 스크립트 대신 python -m pip 사용
VENV_PYTHON="$ROOT/.venv/bin/python"
PIP="$VENV_PYTHON -m pip"

info "web/backend 의존성 설치 중..."
$PIP install -q -r "$BACKEND/requirements.txt"

# ngrok 확인
if [[ "$NO_NGROK" = false ]]; then
    if ! command -v ngrok >/dev/null 2>&1; then
        err "ngrok 없음"
        err "설치: brew install ngrok/ngrok/ngrok  또는  https://ngrok.com/download"
        err "인증: ngrok config add-authtoken YOUR_TOKEN"
        exit 1
    fi
fi

# 포트 충돌 확인 / 재사용
LOCAL_HEALTH="http://127.0.0.1:$PORT/health"
API_PID=""
API_STARTED=false

if lsof -i ":$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    if [[ "$FORCE_RESTART" = true ]]; then
        warn "--force-restart: 포트 $PORT 기존 프로세스 종료"
        lsof -i ":$PORT" -sTCP:LISTEN -t | xargs kill -9 2>/dev/null || true
        sleep 1
    elif curl -sf "$LOCAL_HEALTH" >/dev/null 2>&1; then
        ok "FastAPI 이미 실행 중 (포트 $PORT) — 재사용"
    else
        warn "포트 $PORT 사용 중, /health 실패 → 프로세스 종료 후 재시작"
        lsof -i ":$PORT" -sTCP:LISTEN -t | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
fi

if ! curl -sf "$LOCAL_HEALTH" >/dev/null 2>&1; then
    export FACTORY_ROOT="$ROOT"
    export PYTHONUNBUFFERED=1
    info "FastAPI 시작 중 (127.0.0.1:$PORT)..."
    (cd "$BACKEND" && python -m uvicorn main:app --host 127.0.0.1 --port "$PORT") \
        >"$API_LOG_OUT" 2>"$API_LOG_ERR" &
    API_PID=$!
    API_STARTED=true

    HEALTH_OK=false
    for i in $(seq 1 60); do
        if curl -sf "$LOCAL_HEALTH" >/dev/null 2>&1; then
            HEALTH_OK=true
            HEALTH=$(curl -s "$LOCAL_HEALTH" 2>/dev/null || echo "ok")
            ok "FastAPI 응답: $HEALTH"
            break
        fi
        sleep 0.5
    done

    if [[ "$HEALTH_OK" = false ]]; then
        err "$LOCAL_HEALTH 응답 없음"
        tail -20 "$API_LOG_OUT" 2>/dev/null || true
        tail -20 "$API_LOG_ERR" 2>/dev/null || true
        [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null || true
        exit 1
    fi
fi

# ngrok 터널
NGROK_PID=""
NGROK_STARTED=false
PUBLIC_URL=""

if [[ "$NO_NGROK" = false ]]; then
    # ngrok API에서 기존 URL 확인
    EXISTING_URL=$(curl -sf "http://127.0.0.1:$NGROK_API_PORT/api/tunnels" 2>/dev/null \
        | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for t in d.get('tunnels', []):
        u = t.get('public_url','')
        if u.startswith('https://'):
            print(u); break
    else:
        for t in d.get('tunnels', []):
            u = t.get('public_url','')
            if u: print(u); break
except: pass
" 2>/dev/null || true)

    if [[ -n "$EXISTING_URL" ]] && [[ "$FORCE_RESTART" = false ]]; then
        PUBLIC_URL="$EXISTING_URL"
        echo "$PUBLIC_URL" > "$NGROK_URL_FILE"
        ok "ngrok 이미 실행 중 — 재사용: $PUBLIC_URL"
    else
        [[ -f "$NGROK_URL_FILE" ]] && rm -f "$NGROK_URL_FILE"

        NGROK_ARGS=("http" "$PORT" "--log=stdout")
        if [[ -n "$NGROK_DOMAIN" ]]; then
            NGROK_ARGS+=("--domain=$NGROK_DOMAIN")
            info "ngrok 시작 (static domain): ngrok ${NGROK_ARGS[*]}"
        else
            info "ngrok 시작 (무료/랜덤 URL): ngrok http $PORT"
        fi
        [[ -n "${NGROK_REGION:-}" ]] && NGROK_ARGS+=("--region=$NGROK_REGION")

        ngrok "${NGROK_ARGS[@]}" >"$NGROK_LOG_OUT" 2>"$NGROK_LOG_ERR" &
        NGROK_PID=$!
        NGROK_STARTED=true
        sleep 3

        # ngrok API에서 URL 대기
        for i in $(seq 1 45); do
            NGROK_URL=$(curl -sf "http://127.0.0.1:$NGROK_API_PORT/api/tunnels" 2>/dev/null \
                | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for t in d.get('tunnels', []):
        u = t.get('public_url','')
        if u.startswith('https://'): print(u); break
    else:
        for t in d.get('tunnels', []):
            u = t.get('public_url','')
            if u: print(u); break
except: pass
" 2>/dev/null || true)
            if [[ -n "$NGROK_URL" ]]; then
                PUBLIC_URL="$NGROK_URL"
                echo "$PUBLIC_URL" > "$NGROK_URL_FILE"
                break
            fi
            sleep 1
        done

        if [[ -z "$PUBLIC_URL" ]]; then
            err "ngrok URL을 읽지 못했습니다. logs/ngrok.*.log 확인"
            cat "$NGROK_LOG_ERR" 2>/dev/null | tail -20 || true
            [[ -n "$NGROK_PID" ]] && kill "$NGROK_PID" 2>/dev/null || true
            [[ "$API_STARTED" = true ]] && [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null || true
            exit 1
        fi

        echo ""
        if [[ -n "$NGROK_DOMAIN" ]]; then
            ok "ngrok static domain: $PUBLIC_URL"
        else
            ok "ngrok 공개 URL: $PUBLIC_URL"
            warn "무료 플랜: 재시작마다 URL 변경. logs/ngrok_url.txt 참고"
        fi
    fi

    # 공개 헬스체크
    if curl -sf -H "ngrok-skip-browser-warning: true" "$PUBLIC_URL/health" >/dev/null 2>&1; then
        ok "ngrok 경유 헬스체크 OK: $PUBLIC_URL/health"
    else
        warn "ngrok 경유 헬스체크 실패 (브라우저에서는 동작할 수 있음)"
    fi
fi

if [[ "$NO_BROWSER" = false ]]; then
    open "http://127.0.0.1:$PORT/docs" 2>/dev/null || true
fi

echo ""
echo "========================================"
ok "로컬 API:   http://127.0.0.1:$PORT"
[[ -n "$PUBLIC_URL" ]] && ok "공개 URL:   $PUBLIC_URL"
[[ -f "$NGROK_URL_FILE" ]] && info "URL 파일:  logs/ngrok_url.txt"
info "로그: logs/fastapi.*.log, logs/ngrok.*.log"
info "종료: Ctrl+C"
echo "========================================"

cleanup() {
    echo ""
    info "종료 중..."
    if [[ "$NGROK_STARTED" = true ]] && [[ -n "$NGROK_PID" ]]; then
        kill "$NGROK_PID" 2>/dev/null && ok "ngrok 종료" || true
    fi
    if [[ "$API_STARTED" = true ]] && [[ -n "$API_PID" ]]; then
        kill "$API_PID" 2>/dev/null && ok "FastAPI 종료" || true
    fi
}
trap cleanup EXIT INT TERM

if [[ -n "$API_PID" ]]; then
    wait "$API_PID" 2>/dev/null || true
else
    info "FastAPI는 이 스크립트 밖에서 실행 중 — 직접 종료하세요."
    while true; do sleep 60; done
fi
