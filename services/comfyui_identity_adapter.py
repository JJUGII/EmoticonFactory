"""ComfyUI identity adapters (IPAdapter with graceful img2img fallback)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.comfyui_client import ComfyUIClient


@dataclass(frozen=True)
class IdentityAdapterConfig:
    adapter: str
    weight: float
    enabled: bool


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def load_identity_adapter_config() -> IdentityAdapterConfig:
    adapter = (os.getenv("COMFYUI_IDENTITY_ADAPTER") or "none").strip().lower()
    weight = max(0.0, min(1.0, _env_float("COMFYUI_IPADAPTER_WEIGHT", 0.65)))
    return IdentityAdapterConfig(
        adapter=adapter,
        weight=weight,
        enabled=adapter not in ("", "none", "off", "false", "0"),
    )


def identity_adapter_requested(cfg: IdentityAdapterConfig | None = None) -> bool:
    c = cfg or load_identity_adapter_config()
    return c.enabled and c.adapter in ("ipadapter", "ip_adapter", "ipa")


def _comfy_models_dir() -> Path | None:
    raw = (os.getenv("COMFYUI_DIR") or "").strip()
    if raw:
        p = Path(raw) / "models"
        if p.is_dir():
            return p
    sibling = Path(__file__).resolve().parents[2].parent / "ComfyUI" / "models"
    return sibling if sibling.is_dir() else None


def ipadapter_model_on_disk() -> bool:
    models = _comfy_models_dir()
    if models is None:
        return False
    for sub in ("ipadapter", "clip_vision"):
        d = models / sub
        if d.is_dir() and any(d.glob("*.safetensors")):
            return True
        if d.is_dir() and any(d.glob("*.bin")):
            return True
    return False


def ipadapter_runtime_ready(client: ComfyUIClient | None) -> bool:
    cfg = load_identity_adapter_config()
    if not identity_adapter_requested(cfg):
        return False
    if not ipadapter_model_on_disk():
        return False
    if client is None:
        return False
    from services.comfyui_workflow_patcher import (
        pick_ipadapter_apply_class,
        pick_ipadapter_loader_class,
    )

    return (
        pick_ipadapter_loader_class(client) is not None
        and pick_ipadapter_apply_class(client) is not None
    )


def identity_strategy_for_source_mode(source_mode: str) -> str:
    if (source_mode or "").strip().lower() == "character":
        return "canonical_character_lock"
    return "reference_identity"


def log_identity_strategy(
    *,
    source_mode: str,
    config: IdentityAdapterConfig | None = None,
    weight_override: float | None = None,
    cut_id: str | None = None,
) -> None:
    cfg = config or load_identity_adapter_config()
    strategy = identity_strategy_for_source_mode(source_mode)
    w = cfg.weight if weight_override is None else weight_override
    cut_note = f" cut={cut_id}" if cut_id else ""
    print(
        f"[IDENTITY] strategy={strategy} adapter={cfg.adapter} "
        f"ipadapter_weight={w:.2f} enabled={str(cfg.enabled).lower()}{cut_note}",
        file=sys.stderr,
    )


def log_identity_adapter(
    *,
    applied: bool,
    adapter_type: str,
    weight: float,
    cut_id: str | None = None,
) -> None:
    if applied:
        cut_note = f" cut={cut_id}" if cut_id else ""
        print(
            f"[IDENTITY_ADAPTER] type={adapter_type} weight={weight:.2f}{cut_note}",
            file=sys.stderr,
        )
    else:
        print(
            "[IDENTITY_ADAPTER] unavailable fallback=img2img",
            file=sys.stderr,
        )


def patch_workflow_for_identity(
    workflow: dict[str, Any],
    *,
    reference_image: str,
    config: IdentityAdapterConfig | None = None,
    weight_override: float | None = None,
    bindings: dict[str, Any] | None = None,
    client: ComfyUIClient | None = None,
    cut_id: str | None = None,
) -> dict[str, Any]:
    cfg = config or load_identity_adapter_config()
    w = cfg.weight if weight_override is None else float(weight_override)

    if not identity_adapter_requested(cfg):
        return workflow

    if client is None or not ipadapter_runtime_ready(client):
        log_identity_adapter(applied=False, adapter_type=cfg.adapter, weight=w, cut_id=cut_id)
        return workflow

    from services.comfyui_workflow_patcher import inject_ipadapter

    patched, ok = inject_ipadapter(
        workflow,
        bindings=bindings or {},
        client=client,
        uploaded_reference=reference_image,
        weight=w,
    )
    if ok:
        log_identity_adapter(applied=True, adapter_type="ipadapter", weight=w, cut_id=cut_id)
        return patched

    log_identity_adapter(applied=False, adapter_type=cfg.adapter, weight=w, cut_id=cut_id)
    return workflow
