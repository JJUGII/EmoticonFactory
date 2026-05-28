# 로컬 FastAPI + Cloudflare Tunnel (Render 대체)

Vercel = 프론트 UI만 · PC = AI 워커(FastAPI + `app.py` 파이프라인) · Cloudflare Tunnel = 고정 공개 URL

## 아키텍처

```
브라우저 (Vercel)
    → https://api.yourdomain.com/api/...
        → Cloudflare Tunnel
            → http://127.0.0.1:8000 (로컬 FastAPI)
                → subprocess app.py + OpenAI
```

## 사전 준비

1. Python 3.11+ venv

```powershell
cd KakaoEmoticonFactory
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r web\backend\requirements.txt
```

2. 프로젝트 루트 `.env`

```env
OPENAI_API_KEY=sk-...
```

3. [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) 설치 후 PATH 등록 (도메인 없어도 Quick Tunnel 가능)

---

## ngrok 고정 URL (Vercel API_URL 고정)

도메인 없이 **고정 `*.ngrok-free.app`** 을 쓰려면 → **`README_NGROK.md`** + `start_local_server_ngrok.bat`

---

## 도메인 없을 때 (Cloudflare Quick)

**본인 도메인이 없으면** Named Tunnel(`api.example.com` 등)은 쓰지 마세요.

```text
start_local_server_quick.bat 더블클릭
```

또는 `start_local_server.bat` — `tunnel.env`에 placeholder만 있으면 **자동으로 Quick Tunnel** 사용.

| 항목 | 내용 |
|------|------|
| 공개 URL | `https://xxxx.trycloudflare.com` (실행할 때마다 **바뀜**) |
| 저장 위치 | `logs/quick_tunnel_url.txt` |
| Vercel | **매 실행 후** `API_URL`을 새 URL로 바꾸고 **Redeploy** |
| 비용 | 무료 (개발/테스트용, 상시 운영·고정 URL에는 부적합) |

콘솔에 `[OK] Quick Tunnel URL: https://...` 가 보이면 브라우저에서 `.../health` 로 확인.

---

## 1회 설정: Named Tunnel (도메인 있을 때만)

```powershell
# tunnel.env 작성 후 브라우저 login + tunnel create
.\setup_cloudflare_tunnel.bat
```

수동 요약:

1. `cloudflare\tunnel.env.example` → `cloudflare\tunnel.env` 복사
2. `TUNNEL_NAME`, `TUNNEL_HOSTNAME` 수정 — **Cloudflare에 등록한 실제 도메인** (예: `api.mysite.com`). `api.example.com`은 동작하지 않음
3. `cloudflared tunnel login`
4. `cloudflared tunnel create emiticon-api`
5. `cloudflared tunnel route dns emiticon-api api.example.com`
6. `cloudflare\config.yml` 생성 (스크립트가 자동 생성)

생성된 **고정 URL**: `https://TUNNEL_HOSTNAME`

---

## 매일 실행

```text
start_local_server.bat 더블클릭
```

동작:

1. venv 활성화 + `FACTORY_ROOT` = 프로젝트 루트
2. 포트 8000 점유 확인
3. FastAPI (`web/backend/main.py`)
4. Cloudflare Tunnel (`cloudflare/config.yml`)
5. 브라우저: `http://127.0.0.1:8000/docs`, 공개 URL `/health`

종료: 콘솔에서 Enter

옵션 (PowerShell):

```powershell
.\scripts\start_local_server.ps1 -QuickTunnel   # 도메인 없이 trycloudflare
.\scripts\start_local_server.ps1 -NamedTunnel     # config.yml 고정 터널 강제
.\scripts\start_local_server.ps1 -NoTunnel        # 로컬만
.\scripts\start_local_server.ps1 -Port 8001
```

---

## Vercel 연동

**Settings → Environment Variables**

| Key | Value |
|-----|--------|
| `API_URL` | `https://api.yourdomain.com` |

- 끝에 `/` 없음
- `/api` 붙이지 않음 (프론트가 `/api/upload` 등을 붙임)

저장 후 **Redeploy** 필수.

Render 백엔드는 사용하지 않습니다.

---

## import 충돌 해결 (`app.py` vs `app` 패키지)

루트에 `app.py` CLI가 있어 `web/backend/app/` 패키지명과 충돌했습니다.

→ **`factory_web`** 패키지로 변경 (`from factory_web.config import ...`)

FastAPI 실행:

- 작업 디렉터리: `web/backend`
- `FACTORY_ROOT` 환경 변수: `KakaoEmoticonFactory` 루트
- `/health` 응답 예:

```json
{
  "status": "ok",
  "factory_root": "D:\\...\\KakaoEmoticonFactory",
  "backend_dir": "D:\\...\\web\\backend"
}
```

---

## exit code 7 (파이프라인)

`app.py`는 **OpenAI API 키 없음** 시 `return 7` (`OpenAIMissingKeyError`).

| 증상 | 조치 |
|------|------|
| UI에서 OpenAI 선택 후 생성 실패, job `exit 7` | `.env`에 `OPENAI_API_KEY` 설정 |
| 테스트만 | UI **생성 엔진 → 목업(mock)** |

웹 job의 `log_tail` / `logs/fastapi.err.log`에서 `OpenAIMissingKeyError` 문자열 확인.

---

## Troubleshooting

### ModuleNotFoundError: app.config

- 구버전 `web/backend/app` 사용 중 → `factory_web` + 최신 `main.py` pull
- 루트에서 `uvicorn app:app` 실행 금지 → `start_local_server.bat` 사용

### HTTP 404 (Vercel 업로드)

- Vercel `API_URL` 미설정 또는 redeploy 안 함
- PC에서 `start_local_server.bat` 실행 중인지
- `https://TUNNEL_HOSTNAME/health` 브라우저 확인

### 포트 8000 사용 중

```powershell
Get-NetTCPConnection -LocalPort 8000
Stop-Process -Id <PID> -Force
```

### 로컬 OK, 공개 URL만 안 됨 (`https://api.example.com` 등)

1. **`TUNNEL_HOSTNAME`이 placeholder인지** — `cloudflare/tunnel.env`에 `api.example.com`이면 **절대 동작하지 않음**. Cloudflare에 연결된 **본인 도메인**으로 변경 (예: `api.mysite.com`).
2. **DNS** — `setup_cloudflare_tunnel.bat` 재실행 또는 대시보드에서 CNAME이 터널을 가리키는지 확인.
3. **터널 연결** — `logs/cloudflared.err.log`에 `Registered tunnel connection` 있는지. `quic: timeout`이면 스크립트가 기본 `http2` 사용; 방화벽/VPN에서 UDP 차단 여부 확인.

### cloudflared 실패

- `logs/cloudflared.err.log` / `cloudflared.out.log` 확인
- `cloudflare/config.yml`의 `credentials-file` 경로
- Tunnel이 Cloudflare 대시보드에 active 인지

### FACTORY_ROOT / outputs 경로

- `FACTORY_ROOT`는 반드시 `KakaoEmoticonFactory` 루트
- 웹 job 출력: `web/jobs/<id>/outputs/`
- CLI 기본 outputs: 루트 `outputs/` (웹 API는 job별 output_root 사용)

### subprocess / 경로

- `PipelineRunner`는 `python app.py ...` 를 **FACTORY_ROOT** 를 cwd로 실행
- 업로드 이미지: `web/jobs/<job_id>/uploads/`
- `data/big_emoticon_templates.json` 루트에 있어야 함

---

## 파일 위치

| 파일 | 용도 |
|------|------|
| `start_local_server.bat` | 원클릭 실행 |
| `scripts/start_local_server.ps1` | 실제 로직 |
| `setup_cloudflare_tunnel.bat` | Tunnel 1회 설정 |
| `cloudflare/config.yml` | Tunnel ingress (git 제외 권장) |
| `cloudflare/tunnel.env` | 호스트명 설정 (git 제외) |
| `web/backend/main.py` | FastAPI 엔트리 |
| `web/backend/factory_web/` | API 패키지 |

`.gitignore`에 추가 권장: `cloudflare/config.yml`, `cloudflare/tunnel.env`, `logs/`
