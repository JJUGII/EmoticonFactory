#!/usr/bin/env bash
# Mac 초기 환경 세팅 스크립트
# 사용법: bash setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

info()  { printf '\033[36m[INFO]\033[0m %s\n' "$*"; }
ok()    { printf '\033[32m[OK]  \033[0m %s\n' "$*"; }
warn()  { printf '\033[33m[WARN]\033[0m %s\n' "$*"; }
err()   { printf '\033[31m[ERROR]\033[0m %s\n' "$*" >&2; }

echo "========================================"
echo "  KakaoEmoticonFactory Mac 환경 세팅"
echo "========================================"
echo ""

# Python 버전 확인 — 3.11 > 3.10 > 시스템 순 우선
PYTHON=""
for candidate in \
    /opt/homebrew/bin/python3.11 \
    /opt/homebrew/bin/python3.10 \
    /usr/local/bin/python3.11 \
    /usr/local/bin/python3.10 \
    python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON=$(command -v "$candidate")
        break
    fi
done
if [[ -z "$PYTHON" ]]; then
    err "Python 3.10+ 없음."
    err "설치: brew install python@3.11"
    exit 1
fi

PY_VER=$("$PYTHON" --version 2>&1)
PY_MINOR=$(echo "$PY_VER" | grep -oE '[0-9]+\.[0-9]+' | head -1 | cut -d. -f2)
info "Python: $PY_VER  ($PYTHON)"
if [[ "${PY_MINOR:-0}" -lt 10 ]]; then
    warn "Python 3.10 미만 감지 — 타입힌트(X|Y) 오류 가능"
    warn "권장: brew install python@3.11  그 후 다시 setup.sh 실행"
fi

# venv 생성
if [[ ! -d "$ROOT/.venv" ]]; then
    info ".venv 생성 중..."
    "$PYTHON" -m venv "$ROOT/.venv"
    ok ".venv 생성 완료"
else
    ok ".venv 이미 존재"
fi

# exFAT 외장드라이브 호환: pip 스크립트 shebang 문제 우회 → python -m pip 사용
PIP="$ROOT/.venv/bin/python -m pip"

# 의존성 설치
info "파이프라인 의존성 설치 중 (requirements.txt)..."
$PIP install -q --upgrade pip
$PIP install -q -r "$ROOT/requirements.txt"
ok "파이프라인 의존성 설치 완료"

info "웹 서버 의존성 설치 중 (web/backend/requirements.txt)..."
$PIP install -q -r "$ROOT/web/backend/requirements.txt"
ok "웹 서버 의존성 설치 완료"

# .env 확인
if [[ ! -f "$ROOT/.env" ]]; then
    if [[ -f "$ROOT/.env.example" ]]; then
        cp "$ROOT/.env.example" "$ROOT/.env"
        warn ".env 파일 생성됨 (.env.example 복사)"
        warn "→ .env 파일을 열어 OPENAI_API_KEY 를 입력하세요"
    else
        warn ".env 파일 없음. 아래 내용으로 생성하세요:"
        warn "  echo 'OPENAI_API_KEY=sk-...' > .env"
    fi
else
    ok ".env 파일 확인됨"
fi

# inputs 폴더
mkdir -p "$ROOT/inputs"
ok "inputs/ 폴더 확인됨"

# 스크립트 실행 권한
chmod +x "$ROOT/scripts/"*.sh 2>/dev/null || true
chmod +x "$ROOT/start_local_server.sh" 2>/dev/null || true
chmod +x "$ROOT/start_local_server_ngrok.sh" 2>/dev/null || true
chmod +x "$ROOT/setup.sh" 2>/dev/null || true
ok "스크립트 실행 권한 설정 완료"

# 선택: Node.js 프론트엔드
FRONTEND="$ROOT/web/frontend"
if [[ -f "$FRONTEND/package.json" ]]; then
    if command -v node >/dev/null 2>&1; then
        NODE_VER=$(node --version)
        info "Node.js $NODE_VER 감지됨"
        info "프론트엔드 의존성 설치 중 (npm install)..."
        (cd "$FRONTEND" && npm install --silent)
        ok "프론트엔드 의존성 설치 완료"
    else
        warn "Node.js 없음 → 웹 UI를 쓰려면 설치 필요: brew install node"
    fi
fi

echo ""
echo "========================================"
ok "세팅 완료!"
echo ""
echo "  다음 단계:"
echo "  1) .env 에 OPENAI_API_KEY 입력 (mock 생성만 쓸 경우 불필요)"
echo "  2) CLI 빠른 테스트:"
echo "       source .venv/bin/activate"
echo "       python app.py --character inputs/reference.png \\"
echo "         --series 'test' --theme '사랑' --generator mock --test-one"
echo "  3) GUI 실행:"
echo "       python gui_app.py"
echo "  4) 웹 서버 실행:"
echo "       bash start_local_server.sh"
echo "========================================"
