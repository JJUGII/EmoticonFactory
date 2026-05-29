"""KakaoEmoticonFactory Web API (v0.8) — run from web/backend or via start_local_server.bat."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure web/backend is on sys.path so `factory_web` package loads (not root app.py).
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

if not os.getenv("FACTORY_ROOT"):
    os.environ["FACTORY_ROOT"] = str(_BACKEND_DIR.parent.parent.resolve())

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from factory_web.config import CORS_ORIGINS, FACTORY_ROOT
from factory_web.routes import router

load_dotenv(FACTORY_ROOT / ".env")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """서버 시작 시 감정 자동 튜닝 모듈을 백그라운드에서 초기화."""
    try:
        from factory_web.services.emotion_auto_tune import initialize_in_background
        initialize_in_background()
    except Exception:
        pass
    yield


app = FastAPI(
    title="KakaoEmoticonFactory Web API",
    version="0.8.1-local",
    description="사진 → 후보 3 → 감정 16 → 이모티콘 생성 (local worker)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "factory_root": str(FACTORY_ROOT.resolve()),
        "backend_dir": str(_BACKEND_DIR),
    }
