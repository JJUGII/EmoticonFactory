# KakaoEmoticonFactory Web UI (v0.8)

사진 → 후보 3 → 감정 16 → 이모티콘 16 생성 웹 앱.

## 구조

```
web/
  backend/   FastAPI (기존 pipeline_runner / app.py 재사용)
  frontend/  Next.js App Router
```

## 실행

### 1. 백엔드 (KakaoEmoticonFactory 루트에서 venv 권장)

```powershell
cd KakaoEmoticonFactory
pip install -r web/backend/requirements.txt
cd web/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

OpenAI 사용 시 프로젝트 루트 `.env`에 `OPENAI_API_KEY` 설정.

### 2. 프론트엔드

```powershell
cd web/frontend
npm install
npm run dev
```

브라우저: http://localhost:3000  
API 기본: http://localhost:8000 (`NEXT_PUBLIC_API_URL`로 변경 가능)

## API

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/upload` | 사진 업로드 + job 생성 |
| POST | `/api/generate-candidates` | 후보 3장 (`--make-candidates`) |
| GET | `/api/candidates/{job_id}` | 후보 목록 |
| POST | `/api/select-candidate` | canonical 고정 |
| POST | `/api/generate-emoticons` | 16컷 생성 |
| GET | `/api/job/{job_id}` | 진행률 (폴링) |
| GET | `/api/result/{job_id}` | 결과 JSON |
| GET | `/api/download/{job_id}` | ZIP 다운로드 |

작업 데이터: `web/jobs/<job_id>/`  
패키지 출력: `web/jobs/<job_id>/outputs/<series>/`

## 플로우

1. 업로드 → 2. 후보 생성 → 3. 후보 선택(canonical) → 4. 감정 16 수정 → 5. 생성 → 6. 결과/ZIP

후보 선택 전에는 16컷 생성 UI에 도달하지 않습니다.
