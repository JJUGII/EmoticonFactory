"""KakaoEmoticonFactory Web API (v0.8) — run from web/backend or via start_local_server.bat."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
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

from factory_web.config import CORS_ORIGINS, FACTORY_ROOT
from factory_web.routes import router

load_dotenv(FACTORY_ROOT / ".env")

if str(FACTORY_ROOT) not in sys.path:
    sys.path.insert(0, str(FACTORY_ROOT))

from services.env_log import log_openai_check_for_generator, log_openai_env_status  # noqa: E402
from services.generator_config import load_generator_settings, log_startup_config  # noqa: E402

_GENERATOR_SETTINGS = load_generator_settings(FACTORY_ROOT)
log_openai_check_for_generator(_GENERATOR_SETTINGS.emoticon)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    log_startup_config(_GENERATOR_SETTINGS)
    log_openai_check_for_generator(_GENERATOR_SETTINGS.emoticon)
    if _GENERATOR_SETTINGS.emoticon == "comfyui":
        from services.comfyui_checkpoints import ComfyUICheckpointNotFoundError, log_comfyui_checkpoints

        try:
            log_comfyui_checkpoints()
        except ComfyUICheckpointNotFoundError as exc:
            print(f"[COMFYUI] WARNING: {exc}", file=sys.stderr)
    yield


app = FastAPI(
    title="KakaoEmoticonFactory Web API",
    version="0.8.1-local",
    description="사진 → 후보 3 → 감정 16 → 이모티콘 생성 (local worker)",
    lifespan=_lifespan,
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
        "candidate_generator": _GENERATOR_SETTINGS.candidate,
        "emoticon_generator": _GENERATOR_SETTINGS.emoticon,
        "comfyui_url": _GENERATOR_SETTINGS.comfyui_url,
    }
