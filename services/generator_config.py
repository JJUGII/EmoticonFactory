"""Generator backends from environment (.env) — candidate vs emoticon split."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from config import PROJECT_ROOT

_VALID = frozenset({"mock", "openai", "comfyui"})


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _norm_backend(value: str | None, default: str) -> str:
    v = (value or "").strip().lower() or default
    if v not in _VALID:
        raise ValueError(f"지원하지 않는 generator: {v!r} (허용: {', '.join(sorted(_VALID))})")
    return v


def _env_int(name: str, default: int, *, min_v: int = 1, max_v: int = 16) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        n = int(raw)
    except ValueError:
        n = default
    return max(min_v, min(max_v, n))


@dataclass(frozen=True)
class GeneratorSettings:
    candidate: str
    emoticon: str
    comfyui_url: str
    comfyui_workflow: str
    openai_fallback_emoticons: bool
    comfyui_batch_concurrency: int
    comfyui_batch_size: int
    factory_root: Path

    def workflow_path(self) -> Path:
        p = Path(self.comfyui_workflow)
        if p.is_absolute():
            return p
        return (self.factory_root / p).resolve()


def _resolve_factory_root(factory_root: str | Path | None) -> Path:
    if factory_root is not None and str(factory_root).strip():
        return Path(factory_root).resolve()
    env_root = (os.getenv("FACTORY_ROOT") or "").strip()
    if env_root:
        return Path(env_root).resolve()
    try:
        return PROJECT_ROOT.resolve()
    except Exception:
        return Path.cwd().resolve()


def load_generator_settings(factory_root: str | Path | None = None) -> GeneratorSettings:
    root = _resolve_factory_root(factory_root)
    env_path = root / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    else:
        load_dotenv()
        cwd_env = Path.cwd() / ".env"
        if cwd_env.is_file() and cwd_env != env_path:
            load_dotenv(cwd_env)
    wf = (os.getenv("COMFYUI_WORKFLOW") or "workflows/comfyui/canonical_to_emoticon_sdxl.json").strip()
    return GeneratorSettings(
        candidate=_norm_backend(os.getenv("GENERATOR_CANDIDATE"), "openai"),
        emoticon=_norm_backend(os.getenv("GENERATOR_EMOTICON"), "comfyui"),
        comfyui_url=(os.getenv("COMFYUI_URL") or "http://127.0.0.1:8188").strip().rstrip("/"),
        comfyui_workflow=wf,
        openai_fallback_emoticons=_env_bool("OPENAI_FALLBACK_FOR_EMOTICONS", False),
        comfyui_batch_concurrency=_env_int("COMFYUI_BATCH_CONCURRENCY", 1),
        comfyui_batch_size=_env_int("COMFYUI_BATCH_SIZE", 1, max_v=8),
        factory_root=root.resolve(),
    )


def resolve_candidate_generator(override: str | None = None) -> str:
    """후보 3장 전용. ``comfyui`` 는 허용하지 않음."""
    o = (override or "").strip().lower()
    if not o or o in ("auto", "default"):
        g = load_generator_settings().candidate
    else:
        g = _norm_backend(o, "openai")
    if g == "comfyui":
        raise ValueError(
            "GENERATOR_CANDIDATE=comfyui 는 지원하지 않습니다. 후보 3장은 openai 또는 mock 을 사용하세요."
        )
    return g


def candidate_generator_from_env() -> str:
    """메타데이터용 — 검증 없이 .env ``GENERATOR_CANDIDATE`` 값만 반환."""
    return load_generator_settings().candidate


def resolve_cli_candidate_generator(
    *,
    candidate_generator: str = "",
    generator_flag: str = "",
) -> str:
    """``--make-candidates`` 일 때만 호출. ``--generator`` 는 후보 백엔드로 해석."""
    override = (candidate_generator or "").strip() or (generator_flag or "").strip()
    return resolve_candidate_generator(override or None)


def resolve_emoticon_generator(
    override: str | None = None,
    *,
    cli: bool = False,
) -> str:
    """Resolve 16-cut backend. Web/API: empty or ``openai`` → ``GENERATOR_EMOTICON`` from .env.

    ``openai`` is ignored for web because the upload UI uses the same field for *candidates*.
    CLI (``cli=True``): ``--generator openai`` is honored.
    """
    o = (override or "").strip().lower()
    if not cli and o == "openai":
        o = ""
    if not o or o in ("auto", "default"):
        return load_generator_settings().emoticon
    return _norm_backend(o, "comfyui")


def log_startup_config(settings: GeneratorSettings | None = None) -> None:
    s = settings or load_generator_settings()
    preset_name = (os.getenv("EMOTICON_STYLE_PRESET") or "kakao_flat").strip()
    for line in (
        f"[CONFIG] candidate_generator={s.candidate}",
        f"[CONFIG] emoticon_generator={s.emoticon}",
        f"[CONFIG] comfyui_url={s.comfyui_url}",
        f"[CONFIG] comfyui_workflow={s.comfyui_workflow}",
        f"[CONFIG] emoticon_style_preset={preset_name}",
        f"[CONFIG] openai_fallback_for_emoticons={str(s.openai_fallback_emoticons).lower()}",
        f"[CONFIG] comfyui_batch_concurrency={s.comfyui_batch_concurrency}",
        f"[CONFIG] comfyui_batch_size={s.comfyui_batch_size}",
    ):
        print(line, file=sys.stderr)
    if s.emoticon == "comfyui":
        try:
            from services.prompts.comfyui_style_presets import log_comfyui_style_preset

            log_comfyui_style_preset()
        except Exception:
            pass


def log_generator_phase(*, candidate: str | None = None, emoticon: str | None = None) -> None:
    if candidate is not None:
        print(f"[GENERATOR] candidate={candidate}", file=sys.stderr)
    if emoticon is not None:
        print(f"[GENERATOR] emoticon={emoticon}", file=sys.stderr)
