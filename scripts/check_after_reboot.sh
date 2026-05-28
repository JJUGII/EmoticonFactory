#!/usr/bin/env bash
# 재부팅 후 KakaoEmoticonFactory 환경 점검 (읽기 전용, 서버는 자동 기동하지 않음)
# 사용법:
#   bash scripts/check_after_reboot.sh
#   bash scripts/check_after_reboot.sh --web    # 웹 사용 시 추가 점검
#   bash scripts/check_after_reboot.sh --notify # macOS 알림 (요약)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE_WEB=false
MODE_NOTIFY=false
FAIL=0
WARN=0

for arg in "$@"; do
    case "$arg" in
        --web) MODE_WEB=true ;;
        --notify) MODE_NOTIFY=true ;;
        -h|--help)
            sed -n '2,6p' "$0"
            exit 0
            ;;
    esac
done

pass() { printf '\033[32m[OK]\033[0m   %s\n' "$*"; }
fail() { printf '\033[31m[FAIL]\033[0m %s\n' "$*" >&2; FAIL=$((FAIL + 1)); }
warn() { printf '\033[33m[WARN]\033[0m %s\n' "$*" >&2; WARN=$((WARN + 1)); }
info() { printf '\033[36m[INFO]\033[0m %s\n' "$*"; }

port_listen() {
    local p="$1"
    lsof -i ":$p" -sTCP:LISTEN -t >/dev/null 2>&1
}

http_ok() {
    curl -sf --max-time 2 "$1" >/dev/null 2>&1
}

mask_key() {
    local k="$1"
    local n=${#k}
    if [[ "$n" -lt 12 ]]; then
        echo "(too short)"
        return
    fi
    echo "${k:0:8}…${k: -4} (${n} chars)"
}

echo "========================================"
echo "  KakaoEmoticonFactory — 재부팅 후 점검"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "  ROOT=$ROOT"
echo "========================================"
echo ""

# ── 1. 프로젝트 경로 / 외장 디스크 ──
info "1) 프로젝트 경로"
if [[ -d "$ROOT" ]]; then
    pass "프로젝트 폴더 존재: $ROOT"
else
    fail "프로젝트 폴더 없음 — 외장 디스크(/Volumes/JJU 등) 연결 여부 확인"
fi

if [[ "$ROOT" == /Volumes/* ]]; then
    vol="/$(echo "$ROOT" | cut -d/ -f1-3)"
    if [[ -d "$vol" ]]; then
        pass "볼륨 마운트됨: $vol"
    else
        fail "볼륨 미마운트: $vol"
    fi
fi

# ── 2. Python venv ──
info "2) Python 가상환경"
VENV_PY="$ROOT/.venv/bin/python"
if [[ -x "$VENV_PY" ]] || [[ -f "$VENV_PY" ]]; then
    if "$VENV_PY" -c "import sys; assert sys.version_info >= (3,10)" 2>/dev/null; then
        pass "venv Python: $("$VENV_PY" --version 2>&1)"
    else
        fail "venv Python 실행 실패 — bash setup.sh 재실행"
    fi
else
    fail ".venv 없음 — cd $ROOT && bash setup.sh"
fi

if [[ -f "$VENV_PY" ]]; then
    if "$VENV_PY" -c "import PIL, openai" 2>/dev/null; then
        pass "핵심 패키지 (Pillow, openai) import OK"
    else
        warn "패키지 누락 가능 — bash setup.sh"
    fi
fi

# ── 3. .env / API 키 ──
info "3) 환경 변수 (.env)"
ENV_FILE="$ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
    pass ".env 파일 존재"
    if grep -qE '^[[:space:]]*OPENAI_API_KEY[[:space:]]*=' "$ENV_FILE" 2>/dev/null; then
        key=$(grep -E '^[[:space:]]*OPENAI_API_KEY[[:space:]]*=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        if [[ -n "$key" && "$key" != sk-your-key-here && "$key" != sk-proj-your-key-here ]]; then
            pass "OPENAI_API_KEY 설정됨 $(mask_key "$key")"
        else
            warn "OPENAI_API_KEY 비어있거나 placeholder — mock만 가능, openai 불가"
        fi
    else
        warn "OPENAI_API_KEY 항목 없음 — --generator mock 만 가능"
    fi
else
    warn ".env 없음 — OpenAI 실사 생성 시 KakaoEmoticonFactory/.env 필요"
fi

# ── 4. CLI 스모크 ──
info "4) CLI (app.py)"
if [[ -f "$ROOT/app.py" ]]; then
    pass "app.py 존재"
else
    fail "app.py 없음"
fi

# ── 5. 도구 (선택) ──
info "5) 시스템 도구 (선택)"
for cmd in bash curl lsof; do
    if command -v "$cmd" >/dev/null 2>&1; then
        pass "$cmd 사용 가능"
    else
        warn "$cmd 없음"
    fi
done

if command -v node >/dev/null 2>&1; then
    pass "node $(node --version 2>/dev/null)"
else
    warn "node 없음 — 웹 프론트(npm run dev) 불가"
fi

if command -v ngrok >/dev/null 2>&1; then
    pass "ngrok $(ngrok version 2>/dev/null | head -1 || true)"
else
    info "ngrok 미설치 (외부 터널 쓸 때만 필요)"
fi

# ── 6. 서버 상태 (재부팅 후 보통 꺼짐 — 안내용) ──
info "6) 로컬 서버 (재부팅 후에는 보통 OFF — 켜야 웹 UI 동작)"
API_PORT=8000
WEB_PORT=3000

if port_listen "$API_PORT"; then
    pass "포트 $API_PORT (FastAPI) LISTEN 중"
    if http_ok "http://127.0.0.1:$API_PORT/health"; then
        pass "GET /health 응답 OK"
    else
        warn "포트는 열려 있으나 /health 응답 없음"
    fi
else
    warn "포트 $API_PORT 비어 있음 → 웹 쓰려면: bash start_local_server.sh --no-tunnel"
fi

if port_listen "$WEB_PORT"; then
    pass "포트 $WEB_PORT (Next.js) LISTEN 중"
else
    warn "포트 $WEB_PORT 비어 있음 → 웹 쓰려면: cd web/frontend && npm run dev"
fi

if [[ -f "$ROOT/logs/ngrok_url.txt" ]]; then
    url=$(tr -d '[:space:]' <"$ROOT/logs/ngrok_url.txt")
    url="${url#$'\ufeff'}"
    if [[ -n "$url" ]]; then
        info "마지막 ngrok URL (파일): $url — 재부팅 후 터널 재시작 시 URL 바뀔 수 있음"
        if http_ok "$url/health" 2>/dev/null; then
            pass "ngrok URL /health 응답 OK"
        else
            warn "ngrok URL 응답 없음 — bash start_local_server_ngrok.sh 재실행"
        fi
    fi
fi

# ── 7. 웹 모드 추가 ──
if $MODE_WEB; then
    info "7) 웹 모드 (--web)"
    if [[ -d "$ROOT/web/frontend/node_modules" ]]; then
        pass "frontend node_modules 존재"
    else
        warn "frontend node_modules 없음 — cd web/frontend && npm install"
    fi
    if [[ -f "$ROOT/web/backend/main.py" ]]; then
        pass "web/backend/main.py 존재"
    else
        fail "web/backend/main.py 없음"
    fi
fi

# ── 요약 ──
echo ""
echo "========================================"
if [[ "$FAIL" -eq 0 ]]; then
    if [[ "$WARN" -eq 0 ]]; then
        echo "  결과: 모두 통과 — CLI 바로 사용 가능"
    else
        echo "  결과: 필수 OK, 경고 ${WARN}건 (웹/서버는 수동 기동 필요할 수 있음)"
    fi
    echo ""
    echo "  CLI 예: cd $ROOT"
    echo "       .venv/bin/python app.py --help"
    echo ""
    echo "  웹 예: bash start_local_server.sh --no-tunnel"
    echo "       cd web/frontend && npm run dev"
else
    echo "  결과: 실패 ${FAIL}건 — 위 [FAIL] 항목 먼저 해결"
fi
echo "========================================"

if $MODE_NOTIFY && command -v osascript >/dev/null 2>&1; then
    if [[ "$FAIL" -eq 0 ]]; then
        osascript -e "display notification \"경고 ${WARN}건 — 로그는 터미널 참고\" with title \"Emoticon 점검 OK\""
    else
        osascript -e "display notification \"실패 ${FAIL}건 — bash scripts/check_after_reboot.sh\" with title \"Emoticon 점검 FAIL\""
    fi
fi

exit "$([[ "$FAIL" -eq 0 ]] && echo 0 || echo 1)"
