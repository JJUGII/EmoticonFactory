"""Web API paths (KakaoEmoticonFactory root)."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_factory_root() -> Path:
    """Project root: FACTORY_ROOT env > auto-detect from this file."""
    env = (os.getenv("FACTORY_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    # web/backend/factory_web/config.py → parents[3] = KakaoEmoticonFactory
    return Path(__file__).resolve().parents[3]


FACTORY_ROOT = resolve_factory_root()
WEB_ROOT = FACTORY_ROOT / "web"
JOBS_ROOT = WEB_ROOT / "jobs"
UPLOADS_SUBDIR = "uploads"
OUTPUTS_SUBDIR = "outputs"

ALLOWED_UPLOAD_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

DEFAULT_EMOTIONS = [
    "사랑해",
    "좋아",
    "고마워",
    "미안해",
    "배고파",
    "졸려",
    "행복해",
    "화났어",
    "놀랐어",
    "응원해",
    "가지마",
    "안아줘",
    "심심해",
    "축하해",
    "잘자",
    "보고싶어",
]

_CORS_EXTRA = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "").split(",")
    if o.strip()
]

CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    *_CORS_EXTRA,
]
