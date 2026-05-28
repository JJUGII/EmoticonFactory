# 로컬 FastAPI + ngrok (Render 없음)

Vercel = 프론트 · PC = FastAPI + OpenAI · **ngrok** = 공개 URL

```
Vercel  →  API_URL=https://xxxx.ngrok-free.app
              →  ngrok http 8000
                  →  http://127.0.0.1:8000 (FastAPI)
```

---

## Free vs Paid (중요)

| 플랜 | `NGROK_DOMAIN` | ngrok 명령 | URL |
|------|----------------|------------|-----|
| **Free (기본)** | 비우기 | `ngrok http 8000` | **실행마다 랜덤** (`https://random.ngrok-free.app`) |
| **Paid** | 설정 | `ngrok http 8000 --domain=...` | **고정 subdomain** |

Free 플랜에서 `NGROK_DOMAIN` + `--domain=` 을 쓰면 **ERR_NGROK_313** 이 납니다.  
스크립트는 이 오류 시 **자동으로 Free 모드로 재시도**합니다.

**Free 사용자:** `.env` / `ngrok/ngrok.env` 에서 `NGROK_DOMAIN` 줄을 **삭제하거나 비워 두세요.**

---

## 빠른 시작 (Free)

1. [ngrok](https://ngrok.com/download) 설치 (`winget install ngrok.ngrok`)
2. Authtoken (1회):
   ```powershell
   ngrok config add-authtoken YOUR_TOKEN
   ```
3. Python venv (1회):
   ```powershell
   pip install -r web\backend\requirements.txt
   ```
4. 루트 `.env` → `OPENAI_API_KEY=...`
5. **`start_local_server_ngrok.bat`** 더블클릭

성공 예 (Free):

```text
[INFO] NGROK_DOMAIN empty -> free mode (random URL each run)
[INFO] Starting ngrok (free): ngrok http 8000
[OK] ngrok public URL:
  https://abc123.ngrok-free.app
```

URL: `logs/ngrok_url.txt`

---

## Vercel 연동 (Free)

1. BAT 실행 후 콘솔 또는 `logs/ngrok_url.txt` 에서 URL 복사
2. Vercel → **Settings → Environment Variables**
   - `API_URL` = `https://abc123.ngrok-free.app` (끝 `/` 없음, `/api` 붙이지 않음)
3. **Redeploy**
4. PC에서 BAT **계속 실행** 유지

**URL이 바뀌면** (BAT 재시작 시) Vercel `API_URL` 갱신 + Redeploy 필요.

---

## Paid: 고정 subdomain

1. [ngrok Domains](https://dashboard.ngrok.com/domains) (유료 플랜)
2. `.env` 또는 `ngrok/ngrok.env`:
   ```env
   NGROK_DOMAIN=my-app.ngrok-free.app
   ```
3. BAT 실행 → 콘솔:
   ```text
   [OK] ngrok static domain:
     https://my-app.ngrok-free.app
   ```
4. Vercel `API_URL` 을 **한 번만** 설정 후 Redeploy

---

## 무료 / 유료 차이

| | Free | Paid |
|--|------|------|
| 명령 | `ngrok http 8000` | `ngrok http 8000 --domain=NAME` |
| Custom subdomain (`--domain`) | **불가** (ERR_NGROK_313) | 가능 |
| URL | 매 실행 변경 | `NGROK_DOMAIN` 고정 |
| Vercel `API_URL` | 재시작 시 수동 갱신 | 고정 시 1회 설정 |

---

## BAT / 스크립트 동작

`start_local_server_ngrok.bat` → `scripts/start_local_server_ngrok.ps1`

1. ngrok 설치·authtoken 확인
2. `.env` + `ngrok/ngrok.env` 로드
3. `NGROK_DOMAIN` 있음 → paid/static 시도, 없음 → **free only**
4. ERR_NGROK_313 → free 모드 자동 fallback
5. FastAPI + local `/health`
6. ngrok + `http://127.0.0.1:4040/api/tunnels` → public URL
7. `logs/ngrok_url.txt` 저장, 브라우저 `/health` `/docs`
8. Enter → 프로세스 종료

---

## Troubleshooting

### ERR_NGROK_313

- Free 플랜: `.env` 에서 **`NGROK_DOMAIN` 제거**
- 또는 유료 플랜 업그레이드 후 `NGROK_DOMAIN` 설정

### `ngrok not found` / authtoken

- `winget install ngrok.ngrok`
- `ngrok config add-authtoken YOUR_TOKEN`

### ngrok 경고 페이지 ("You are about to visit...")

ngrok **무료**는 브라우저 주소창으로 URL을 열면 이 페이지가 뜹니다.

| 용도 | 해결 |
|------|------|
| **Vercel / API 호출** | 자동 처리됨 — 요청 헤더 `ngrok-skip-browser-warning: 1` (프론트 `api.ts` + Vercel `middleware.ts`) |
| **PC에서 Swagger 보기** | `http://127.0.0.1:8000/docs` 사용 (BAT가 이 주소를 엽니다) |
| **ngrok URL을 브라우저에 직접 입력** | "Visit Site" 클릭 또는 유료 플랜 |

완전 제거(브라우저에서도): ngrok **유료** 플랜.

프론트 배포 후 **Vercel Redeploy** 필요 (`middleware.ts` 반영).

### Vercel Failed to fetch

- PC에서 BAT 실행 중인지
- `API_URL` = `logs/ngrok_url.txt` 와 동일한지
- Redeploy 했는지

### Port 8000 already in use

- 이전 BAT 창을 닫지 않았을 수 있음
- 스크립트가 `/health` OK 이면 **기존 FastAPI 재사용** (에러 없음)
- 강제 재시작:
  ```powershell
  .\scripts\start_local_server_ngrok.ps1 -ForceRestart
  ```
- 수동 종료:
  ```powershell
  Stop-Process -Id 108044 -Force
  ```

### uvicorn / OpenAI

- `logs/fastapi.err.log`
- `.env` → `OPENAI_API_KEY` 또는 UI mock

---

## Cloudflare BAT (공존)

| BAT | 용도 |
|-----|------|
| `start_local_server_ngrok.bat` | ngrok (이 문서) |
| `start_local_server_quick.bat` | Cloudflare 랜덤 URL |
| `start_local_server.bat` | Cloudflare Named (본인 도메인) |

---

## Render

사용하지 않습니다. Vercel + ngrok + 로컬 FastAPI 만 사용하세요.
