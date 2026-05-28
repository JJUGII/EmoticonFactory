# UPLOAD_IT — GitHub / 웹 배포용 패키지

이 폴더만 GitHub 저장소 루트에 올리면 **v0.8 Web UI**를 클라우드에 배포할 수 있습니다.  
(로컬 개발용 전체 repo: 상위 `KakaoEmoticonFactory/`)

## 포함 내용

| 경로 | 설명 |
|------|------|
| `app.py`, `config.py`, `services/`, `data/` | 이모티콘 파이프라인 (기존 CLI 로직) |
| `web/backend/` | FastAPI API |
| `web/frontend/` | Next.js UI |
| `web/jobs/` | 업로드·생성 작업 저장 (배포 시 디스크/볼륨 필요) |
| `Dockerfile`, `render.yaml` | API 서버 배포 |
| `.env.example` | 환경 변수 템플릿 |

**제외:** `node_modules`, `.next`, GUI, `AI_CONTEXT`, 로컬 `outputs/`

## 다시 만들기 (소스에서 복사)

```powershell
cd KakaoEmoticonFactory
python scripts/build_upload_it.py
```

---

## 1. GitHub에 올리기

```powershell
cd D:\000_Auto\emiticon\UPLOAD_IT
git init
git add .
git commit -m "Initial web deploy bundle"
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

`.env`는 **절대 커밋하지 마세요.**

---

## 2. 백엔드 (Render Docker)

- Dockerfile 사용, `OPENAI_API_KEY`, `CORS_ORIGINS` 설정
- Disk: `/app/web/jobs`
- Health: `GET /health`

---

## 3. 프론트 (Vercel)

- Root Directory: `web/frontend`
- `NEXT_PUBLIC_API_URL` = API URL

---

## 4. 로컬

```powershell
pip install -r requirements.txt
cd web\backend && uvicorn main:app --reload --port 8000
# 다른 터미널
cd web\frontend && npm install && npm run dev
```

자세한 내용은 빌드 후 생성되는 `UPLOAD_IT/README.md` 전체판 참고.
