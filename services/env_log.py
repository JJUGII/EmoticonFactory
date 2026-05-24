"""Safe logging for environment variables (never print full secrets)."""

from __future__ import annotations

import os
import sys


def _key_prefix(key: str, *, show: int = 12) -> str:
    k = (key or "").strip()
    if not k:
        return "(empty)"
    if len(k) <= show:
        return f"{k[:3]}…"
    return f"{k[:show]}…"


def log_openai_env_status(prefix: str = "[ENV]") -> None:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    loaded = bool(key)
    print(f"{prefix} OPENAI_API_KEY loaded: {str(loaded).lower()}", file=sys.stderr)
    if loaded:
        print(f"{prefix} OPENAI_API_KEY prefix: {_key_prefix(key)}", file=sys.stderr)


def log_openai_check_for_generator(generator: str) -> None:
    """Log whether OpenAI key is required for this backend (never prints full key)."""
    g = (generator or "").strip().lower()
    if g == "openai":
        log_openai_env_status("[ENV]")
    else:
        print(
            f"[ENV] OPENAI check skipped for non-openai generator ({g or 'unset'})",
            file=sys.stderr,
        )


def openai_key_present() -> bool:
    return bool((os.getenv("OPENAI_API_KEY") or "").strip())


def require_openai_api_key(*, context: str = "OpenAI") -> None:
    from services.image_generator import OpenAIMissingKeyError

    if not openai_key_present():
        raise OpenAIMissingKeyError(
            f"{context}: OPENAI_API_KEY 가 설정되어 있지 않습니다. "
            ".env 또는 환경변수 OPENAI_API_KEY 를 설정하세요 (.env.example 참고)."
        )


def openai_client_kwargs() -> dict[str, str]:
    """Explicit api_key for OpenAI() — avoids SDK reading a stale or empty env in subprocess."""
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return {}
    return {"api_key": key}


def format_openai_exception(exc: BaseException) -> str:
    import traceback

    lines = [f"{type(exc).__name__}: {exc}"]
    cause = exc.__cause__ or exc.__context__
    if cause is not None:
        lines.append(f"cause: {type(cause).__name__}: {cause}")
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    lines.append(f"OPENAI_API_KEY present: {bool(key)}")
    tb = traceback.format_exc()
    if tb and tb.strip() != "NoneType: None\n":
        lines.append(tb.rstrip())
    return "\n".join(lines)
