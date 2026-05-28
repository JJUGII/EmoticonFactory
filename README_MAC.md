# KakaoEmoticonFactory — Mac 사용 매뉴얼

> **Mac 전용 안내입니다.** Windows 안내는 `README.md` 참고.  
> 검증 환경: macOS + Python 3.11 (Homebrew) + ngrok 3.x + Node.js 26

---

## 목차

1. [현재 환경 상태](#1-현재-환경-상태)
2. [초기 세팅 (처음 한 번만)](#2-초기-세팅-처음-한-번만)
3. [OpenAI API 키 설정](#3-openai-api-키-설정)
4. [CLI 이모티콘 생성](#4-cli-이모티콘-생성)
5. [GUI 실행](#5-gui-실행)
6. [웹 서버 실행](#6-웹-서버-실행)
7. [외부 공개 URL (터널)](#7-외부-공개-url-터널)
8. [Next.js 웹 UI 실행](#8-nextjs-웹-ui-실행)
9. [출력 결과물 구조](#9-출력-결과물-구조)
10. [CLI 전체 옵션 참고](#10-cli-전체-옵션-참고)
11. [문제 해결](#11-문제-해결)

---

## 1. 현재 환경 상태

이 프로젝트는 **외장 드라이브(exFAT)** 위에 있습니다.

| 항목 | 상태 |
|------|------|
| Python | 3.11.15 (Homebrew: `/opt/homebrew/bin/python3.11`) |
| venv | `.venv/` — 이미 생성 + 패키지 설치 완료 |
| ngrok | ✅ 설치됨 (`/opt/homebrew/bin/ngrok` v3.39.2) |
| cloudflared | ⚠️ 미설치 (ngrok 사용 가능하므로 필수 아님) |
| Node.js | ✅ v26 (`/opt/homebrew/bin/node`) |
| OpenAI API 키 | `.env` 파일에 설정됨 |

> **exFAT 주의사항**: venv가 이 드라이브에 있어 스크립트 shebang 실행이 제한됩니다.  
> 항상 **`bash setup.sh`**, **`bash start_local_server.sh`** 형식으로 `bash`를 명시해서 실행하세요.  
> `./setup.sh` 로 바로 실행하면 "Permission denied" 오류가 납니다.

---

## 2. 초기 세팅 (처음 한 번만)

### 이미 완료된 경우
`.venv/lib/` 폴더가 있으면 이미 세팅 완료입니다. **3번으로 건너뜁니다.**

```bash
ls /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory/.venv/lib/
# python3.11 폴더가 보이면 OK
```

### 세팅이 필요한 경우 (재설치 등)

```bash
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory
bash setup.sh
```

`setup.sh` 가 자동으로 처리하는 것들:
- Python 3.11 (Homebrew) 탐지
- `.venv/` 가상환경 생성
- `requirements.txt` 패키지 설치 (Pillow, OpenCV, OpenAI 등)
- `web/backend/requirements.txt` 설치 (FastAPI, uvicorn 등)
- `web/frontend/` npm install (Next.js)
- 스크립트 실행 권한 설정

완료 메시지 예시:
```
[OK] 세팅 완료!
```

---

## 3. OpenAI API 키 설정

**mock(가짜 이미지) 생성만 할 경우 불필요합니다.**

실제 AI 이미지 생성(`--generator openai`)을 원하면:

```bash
# 텍스트 편집기로 .env 열기
open -e /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory/.env
```

내용 확인 및 수정:
```
OPENAI_API_KEY=sk-proj-여기에실제키입력
```

저장 후 닫습니다. 이후 스크립트 실행 시 자동으로 로드됩니다.

---

## 4. CLI 이모티콘 생성

### 4-1. Python 활성화

터미널을 열고:

```bash
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory

# exFAT 호환 방식 (source 대신 직접 python 경로 사용)
export PATH="/Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory/.venv/bin:$PATH"
```

또는 매번 아래처럼 python 경로를 직접 지정해도 됩니다:

```bash
# .venv/bin/python 으로 직접 실행 (가장 안전)
.venv/bin/python app.py [옵션들...]
```

> **팁**: 아래 모든 예시에서 `python` 대신 `.venv/bin/python` 을 쓰는 게 확실합니다.

### 4-2. 입력 이미지 준비

반려동물 사진을 `inputs/` 폴더에 넣습니다:

```bash
# Finder에서 복사하거나
cp ~/Desktop/내고양이.png inputs/reference.png

# 또는 Finder에서 inputs/ 폴더 열기
open inputs/
```

지원 형식: PNG, JPG, WebP (투명 배경 PNG 권장)

---

### 4-3. 전체 워크플로우 (권장 순서)

#### STEP 1. 베이스 캐릭터 후보 3장 생성

```bash
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory

# mock 테스트 (무료, 즉시, API 불필요)
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "우리집냥이" \
  --theme "사랑" \
  --make-candidates \
  --candidate-count 3 \
  --generator mock \
  --overwrite
```

OpenAI로 실제 AI 후보 생성:
```bash
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "우리집냥이" \
  --theme "사랑" \
  --make-candidates \
  --candidate-count 3 \
  --generator openai \
  --overwrite
```

결과 확인:
```bash
open outputs/우리집냥이/character_candidates/
# candidate_01.png ~ candidate_03.png 가 생성됨
```

---

#### STEP 2. 마음에 드는 후보 선택

후보 이미지를 확인 후, 예를 들어 2번이 마음에 들면:

```bash
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "우리집냥이" \
  --theme "사랑" \
  --select-candidate 2 \
  --overwrite
```

결과: `outputs/우리집냥이/character/canonical_character.png` 가 고정됩니다.

---

#### STEP 3. 3컷 테스트 생성 (빠른 품질 확인)

```bash
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "우리집냥이" \
  --theme "사랑" \
  --generator mock \
  --test-ids "01,02,03" \
  --make-preview \
  --overwrite
```

미리보기 확인:
```bash
open outputs/우리집냥이/preview.html
```

---

#### STEP 4. 16컷 전체 생성

3컷이 마음에 들면 전체 16컷을 생성합니다:

```bash
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "우리집냥이" \
  --theme "사랑" \
  --generator mock \
  --make-preview \
  --overwrite
```

OpenAI로 실제 AI 이미지 생성 (과금):
```bash
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "우리집냥이" \
  --theme "사랑" \
  --generator openai \
  --make-preview \
  --overwrite
```

결과 폴더 열기:
```bash
open outputs/우리집냥이/
```

---

### 4-4. 한 번에 전체 파이프라인 (빠른 테스트용)

```bash
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "우리집냥이" \
  --theme "사랑" \
  --full-pipeline \
  --overwrite
```

`--full-pipeline` 은 내부적으로 아래를 모두 실행합니다:
- `--stylizer mock --generator mock`
- `--postprocess` (후처리)
- `--check-consistency` (일관성 검사)
- `--auto-regenerate` (자동 재생성)
- `--make-webp` (움직이는 WebP 생성)
- `--make-preview` (HTML 미리보기 생성)

---

### 4-5. 동물 종류·성격 힌트 추가

더 정확한 캐릭터를 원할 때:

```bash
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "우리집냥이" \
  --theme "사랑" \
  --species-hint cat \
  --personality-hint "무심하고 시크하지만 귀여움" \
  --generator openai \
  --make-preview \
  --overwrite
```

`--species-hint` 옵션: `cat`, `dog`, `rabbit`, `hamster`, `bird` 등

---

## 5. GUI 실행

```bash
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory
.venv/bin/python gui_app.py
```

창이 열리면 아래 순서로 진행합니다:

| 순서 | 동작 |
|------|------|
| ① | 📁 버튼 클릭 → 반려동물 사진 선택 |
| ② | 시리즈명, 테마, 동물 종류 입력 |
| ③ | 생성 엔진 선택: `mock`(무료) / `openai`(AI, 과금) |
| ④ | **"베이스 후보 생성"** 버튼 → 3장 생성 대기 |
| ⑤ | 3장 중 마음에 드는 것 클릭하여 선택 |
| ⑥ | **"3컷 테스트"** 버튼 → 빠른 미리보기 |
| ⑦ | **"16컷 생성"** 버튼 → 전체 이모티콘 세트 생성 |
| ⑧ | **"출력 폴더 열기"** 버튼 → 결과 확인 |

> **참고**: GUI는 내부적으로 `app.py` CLI를 subprocess로 호출합니다.  
> 오류가 나면 같은 옵션으로 CLI를 직접 실행해 자세한 로그를 볼 수 있습니다.

---

## 6. 웹 서버 실행

브라우저 기반 웹 UI를 사용하려면 FastAPI 서버를 시작합니다.

### 기본 실행 (로컬 전용)

```bash
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory
bash start_local_server.sh --no-tunnel
```

브라우저에서:
- **웹 UI**: `http://localhost:3000` (Next.js 프론트 별도 실행 필요, 8번 참고)
- **API 문서**: `http://127.0.0.1:8000/docs`
- **헬스 체크**: `http://127.0.0.1:8000/health`

### ngrok 터널 포함 실행 (외부 공개 URL 생성)

```bash
bash start_local_server_ngrok.sh
```

실행되면 터미널에 아래와 같이 출력됩니다:
```
[OK] 로컬 API:   http://127.0.0.1:8000
[OK] 공개 URL:   https://xxxx-xxxx.ngrok-free.app
```

공개 URL은 `logs/ngrok_url.txt` 에도 저장됩니다.

### 포트 변경

```bash
bash start_local_server.sh --port 9000
```

### 서버 종료

실행 중인 터미널에서 `Ctrl + C`

---

## 7. 외부 공개 URL (터널)

### 방법 A: ngrok (이미 설치됨 ✅)

**1회 인증 설정** (처음 한 번만):
```bash
# https://dashboard.ngrok.com 에서 Authtoken 복사 후:
ngrok config add-authtoken YOUR_NGROK_TOKEN
```

**서버 시작 (ngrok 자동 포함)**:
```bash
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory
bash start_local_server_ngrok.sh
```

**무료 플랜 특징**:
- 재시작마다 URL이 바뀜
- 최신 URL은 항상 `logs/ngrok_url.txt` 에서 확인

**고정 URL 설정** (ngrok 유료 플랜):
```bash
# ngrok/ngrok.env 파일 생성
mkdir -p ngrok
echo "NGROK_DOMAIN=my-api.ngrok-free.app" > ngrok/ngrok.env
```

---

### 방법 B: Cloudflare Quick Tunnel (설치 필요)

```bash
# 설치
brew install cloudflared

# 서버 시작 (터널 자동 포함)
bash start_local_server.sh
```

Quick Tunnel도 무료 플랜은 재시작마다 URL 변경됩니다. URL은 `logs/quick_tunnel_url.txt` 에 저장됩니다.

---

## 8. Next.js 웹 UI 실행

브라우저에서 전체 UI(사진 업로드 → 후보 선택 → 이모티콘 생성)를 사용하려면 프론트엔드도 실행합니다.

**터미널 2개** 필요:

```bash
# 터미널 1: 백엔드 API 서버
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory
bash start_local_server.sh --no-tunnel

# 터미널 2: Next.js 프론트엔드
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory/web/frontend
npm run dev
```

브라우저에서 `http://localhost:3000` 접속.

### UI 5단계 흐름

| 단계 | 화면 | 내용 |
|------|------|------|
| 1 | **사진 업로드** | 반려동물 사진 드래그&드롭 또는 파일 선택 |
| 2 | **캐릭터 후보** | AI가 만든 3가지 스타일 중 1개 선택 |
| 3 | **감정 편집** | 16개 감정 텍스트 직접 수정 가능 |
| 4 | **생성 진행** | 16컷 실시간 진행률 표시 |
| 5 | **결과** | 이모티콘 그리드 확인 + ZIP 다운로드 |

### 백엔드 URL 설정

프론트가 다른 URL의 백엔드를 바라볼 경우:

```bash
# web/frontend/.env.local 파일 생성
echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" \
  > web/frontend/.env.local

# ngrok URL 사용 시
echo "NEXT_PUBLIC_API_URL=https://xxxx.ngrok-free.app" \
  > web/frontend/.env.local
```

변경 후 `npm run dev` 재시작.

---

## 9. 출력 결과물 구조

모든 결과물은 `outputs/<시리즈명>/` 폴더에 생성됩니다.

```
outputs/우리집냥이/
│
├── character/
│   ├── reference.png              ← 입력 사진 복사본
│   ├── canonical_character.png    ← 선택된 기준 캐릭터 (--select-candidate 이후)
│   ├── character_base.png         ← 540×540 투명 캔버스 기준 이미지
│   ├── character_base_white.png   ← 흰 배경 버전
│   └── character_candidates/
│       ├── candidate_01.png       ← 후보 1번
│       ├── candidate_02.png       ← 후보 2번
│       └── candidate_03.png       ← 후보 3번
│
├── png/                           ← ★ 최종 이모티콘 (카카오 제출용)
│   ├── 01.png                     ← 540×540 RGBA
│   ├── 02.png
│   └── ... 16.png
│
├── png_raw/                       ← --postprocess 사용 시: 후처리 전 원본
│
├── processed/                     ← --postprocess 사용 시: 후처리 완료본
│
├── icon/                          ← 아이콘 이미지
│   ├── 01.png                     ← 78×78 RGBA
│   └── ... 16.png
│
├── share/
│   └── share.png                  ← 600×166 공유 이미지 배너
│
├── webp/                          ← --make-webp 사용 시
│   ├── 01_heart_pop.webp          ← 움직이는 WebP
│   ├── 03_bounce.webp
│   └── 10_sleep.webp
│
├── meta/                          ← 메타데이터 JSON
│   ├── package_info.json          ← 전체 패키지 정보
│   ├── cut_plan.json              ← 16컷 포즈 플랜
│   ├── prompts.json               ← 컷별 생성 프롬프트
│   ├── generation_log.json        ← OpenAI 생성 로그
│   ├── consistency_report.json    ← 일관성 검사 결과
│   ├── identity_profile.json      ← 캐릭터 정체성 프로파일
│   └── webp_report.json           ← WebP 메타 (--make-webp 시)
│
├── failed_consistency/            ← 일관성 검사 미통과 컷 복사본
│
└── preview.html                   ← ★ 브라우저 미리보기 (--make-preview 시)
```

**미리보기 열기**:
```bash
open outputs/우리집냥이/preview.html
```

**Finder에서 열기**:
```bash
open outputs/우리집냥이/
```

---

## 10. CLI 전체 옵션 참고

### 필수 옵션

| 옵션 | 설명 | 예시 |
|------|------|------|
| `--character` | 입력 이미지 경로 | `--character inputs/reference.png` |
| `--series` | 시리즈명 (폴더명 기준) | `--series "우리집냥이"` |
| `--theme` | 감정 테마 | `--theme "사랑"` |

### 생성 엔진

| 옵션 | 설명 |
|------|------|
| `--generator mock` | 무료 목업 이미지 (기본값, API 불필요) |
| `--generator openai` | 실제 AI 이미지 (OPENAI_API_KEY 필요, 과금) |

### 파이프라인 제어

| 옵션 | 설명 |
|------|------|
| `--make-candidates` | 베이스 후보 3장 생성 후 종료 |
| `--candidate-count 3` | 후보 수 (기본 3) |
| `--select-candidate 2` | 후보 2번 선택 후 생성 계속 |
| `--test-one` | 1번 컷만 생성 (빠른 검증) |
| `--test-ids "01,02,03"` | 지정 컷만 생성 |
| `--full-pipeline` | 전체 파이프라인 한 번에 |
| `--overwrite` | 기존 결과 덮어쓰기 (후보/canonical 보존) |
| `--full-reset` | 출력 폴더 전체 삭제 후 재생성 |

### 품질 옵션

| 옵션 | 설명 |
|------|------|
| `--make-preview` | preview.html 생성 |
| `--make-webp` | 움직이는 WebP 생성 (기본 3개) |
| `--postprocess` | 후처리 적용 |
| `--check-consistency` | 일관성 검사 (기본 활성화) |
| `--auto-regenerate` | 실패 컷 자동 재생성 |

### 캐릭터 힌트

| 옵션 | 설명 | 예시 |
|------|------|------|
| `--species-hint` | 동물 종류 힌트 | `cat`, `dog`, `rabbit` |
| `--personality-hint` | 성격 힌트 | `"시크하지만 귀여움"` |
| `--reference-type` | 입력 타입 강제 지정 | `photo`, `character_art`, `auto` |
| `--style-intensity` | 일러스트 질감 강도 | `0.0`~`1.0` (기본 `0.5`) |

---

## 11. 재부팅 후 자동 점검

재부팅 후 **서버는 자동으로 켜지지 않습니다**. 대신 아래 스크립트로 마운트·venv·`.env`·포트·`/health` 등을 한 번에 확인할 수 있습니다.

```bash
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory
bash check_after_reboot.sh              # CLI 기준 필수 항목
bash check_after_reboot.sh --web        # 웹(frontend node_modules) 추가
bash check_after_reboot.sh --notify     # macOS 알림 (요약만)
```

- **종료 코드**: `0` = 필수 항목 통과, `1` = `[FAIL]` 있음 (외장 디스크 미연결, `.venv` 없음 등)
- **서버 자동 기동 없음** — `[WARN]` 으로 8000/3000이 비어 있으면 정상(재부팅 직후). 웹 쓰려면 `start_local_server.sh` / `npm run dev` 수동 실행

### 로그인 시 점검만 자동 실행 (선택)

서버를 켜지 않고 **점검만** 돌리려면 LaunchAgent 예시:

```bash
# plist 예시 경로: ~/Library/LaunchAgents/com.emoticon.healthcheck.plist
# ProgramArguments: /bin/bash, .../check_after_reboot.sh, --notify
# RunAtLoad: true
# StandardOutPath: .../logs/healthcheck.log
```

원하면 `scripts/install_login_healthcheck.sh` 같은 설치 스크립트를 추가할 수 있습니다(명시적 요청 시).

---

## 12. 문제 해결

### "Permission denied" — 스크립트 실행 오류

exFAT 외장 드라이브 특성상 `./start_local_server.sh` 로 직접 실행하면 오류납니다.

```bash
# ❌ 이렇게 하지 마세요
./setup.sh
./start_local_server.sh

# ✅ 항상 bash를 명시하세요
bash setup.sh
bash start_local_server.sh
```

---

### "ModuleNotFoundError" — 패키지 없음

venv가 없거나 패키지 설치가 안 된 경우:

```bash
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory
bash setup.sh
```

---

### "command not found: python" — python 못 찾음

venv python을 직접 지정합니다:

```bash
# .venv/bin/python 으로 직접 실행
.venv/bin/python app.py [옵션들...]
.venv/bin/python gui_app.py
```

또는 PATH에 venv 추가:
```bash
export PATH="/Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory/.venv/bin:$PATH"
python app.py [옵션들...]
```

---

### 포트 이미 사용 중

```bash
# 8000번 포트 사용 프로세스 확인
lsof -i :8000

# 해당 PID 종료 (예: 12345)
kill 12345

# 강제 종료
kill -9 12345
```

---

### 웹 서버 오류 로그 확인

```bash
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory

# FastAPI 로그
tail -50 logs/fastapi.out.log
tail -50 logs/fastapi.err.log

# ngrok 로그
tail -30 logs/ngrok.out.log
```

---

### CLI 오류 디버깅

`--test-one` 으로 1컷만 먼저 테스트:

```bash
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "debug" \
  --theme "사랑" \
  --generator mock \
  --test-one \
  --overwrite
```

---

### OpenAI API 오류 (exit code 7)

`.env` 파일 확인:
```bash
cat .env
# OPENAI_API_KEY=sk-... 가 있어야 함
```

API 키 없이 동작 확인만 하려면 `--generator mock` 사용.

---

### GUI 실행 안 됨 (PySide6 오류)

```bash
bash setup.sh   # PySide6 재설치
.venv/bin/python gui_app.py
```

---

### ngrok 인증 오류

```bash
# ngrok 인증 상태 확인
ngrok config check

# 재인증
ngrok config add-authtoken YOUR_AUTHTOKEN
# 토큰은 https://dashboard.ngrok.com/get-started/your-authtoken 에서 복사
```

---

### 출력 폴더 초기화

```bash
# 특정 시리즈만 삭제
rm -rf outputs/우리집냥이/

# 전체 삭제
rm -rf outputs/
```

---

## 빠른 시작 요약

```bash
# ─────────────────────────────────────
# 0. 프로젝트 폴더로 이동
# ─────────────────────────────────────
cd /Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory

# ─────────────────────────────────────
# 1. 세팅 확인 (처음 or 재설치 시만)
# ─────────────────────────────────────
bash setup.sh

# ─────────────────────────────────────
# 2. 사진 준비
# ─────────────────────────────────────
cp ~/Desktop/내사진.png inputs/reference.png

# ─────────────────────────────────────
# 3. 후보 3장 생성
# ─────────────────────────────────────
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "내이모티콘" \
  --theme "사랑" \
  --make-candidates --generator mock --overwrite

# 결과 확인
open outputs/내이모티콘/character_candidates/

# ─────────────────────────────────────
# 4. 마음에 드는 후보 선택 (예: 1번)
# ─────────────────────────────────────
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "내이모티콘" --theme "사랑" \
  --select-candidate 1 --overwrite

# ─────────────────────────────────────
# 5. 3컷 테스트
# ─────────────────────────────────────
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "내이모티콘" --theme "사랑" \
  --generator mock --test-ids "01,02,03" \
  --make-preview --overwrite

open outputs/내이모티콘/preview.html

# ─────────────────────────────────────
# 6. 전체 16컷 생성
# ─────────────────────────────────────
.venv/bin/python app.py \
  --character inputs/reference.png \
  --series "내이모티콘" --theme "사랑" \
  --generator mock --make-preview --overwrite

# 결과 확인
open outputs/내이모티콘/
open outputs/내이모티콘/preview.html
```

---

*최종 검증: 2026-05-27 | Python 3.11.15 | macOS (exFAT 외장 드라이브)*
