"""ComfyUI runtime hints (Apple MPS, batch env)."""

from __future__ import annotations

import os
import sys


def detect_mps_available() -> bool:
    """True when PyTorch MPS backend is available (Apple Silicon)."""
    try:
        import torch

        return bool(getattr(torch.backends, "mps", None)) and torch.backends.mps.is_available()
    except Exception:
        return sys.platform == "darwin"


def log_comfyui_runtime_hints(*, batch_size: int, queue_concurrency: int) -> None:
    if detect_mps_available():
        print(
            "[COMFYUI] MPS detected, prefer workflow batching over queue concurrency",
            file=sys.stderr,
        )
        if queue_concurrency > 1 and batch_size <= 1:
            print(
                "[COMFYUI] hint: set COMFYUI_BATCH_CONCURRENCY=1 and COMFYUI_BATCH_SIZE=2 "
                "for diffusion efficiency on Apple Silicon",
                file=sys.stderr,
            )
    if batch_size > 1 and queue_concurrency > 1:
        print(
            "[COMFYUI] WARNING: workflow batch_size>1 with queue concurrency>1 may OOM on Mac — "
            "prefer COMFYUI_BATCH_CONCURRENCY=1",
            file=sys.stderr,
        )


def load_comfyui_batch_size() -> int:
    raw = (os.getenv("COMFYUI_BATCH_SIZE") or "1").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 1
    n = max(1, min(n, 8))
    if n > 4:
        print(
            "[COMFYUI] WARNING: COMFYUI_BATCH_SIZE>4 — unified workflow may exhaust RAM/VRAM on Mac",
            file=sys.stderr,
        )
    return n


def resolve_workflow_batch_size(param: int | None = None) -> tuple[int, dict[str, int | str]]:
    """
    Resolve workflow batch size — env/settings win over accidental ``param=1``.

    Returns ``(resolved, debug_sources)``.
    """
    from services.generator_config import load_generator_settings

    env_raw = (os.getenv("COMFYUI_BATCH_SIZE") or "").strip()
    from_env = load_comfyui_batch_size()
    from_settings = load_generator_settings().comfyui_batch_size
    explicit = int(param) if param is not None else 1
    resolved = max(1, from_env, from_settings)
    if explicit > 1:
        resolved = max(resolved, explicit)
    resolved = max(1, min(8, resolved))
    return resolved, {
        "env_raw": env_raw or "(empty)",
        "from_env": from_env,
        "from_settings": from_settings,
        "param": explicit,
        "resolved": resolved,
    }
