"""Per-framing img2img denoise (break passport regression from low fixed denoise)."""

from __future__ import annotations

import os
import sys

from services.prompts.comfyui_style_presets import ComfyUISamplerParams


def _env_bool(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def adaptive_denoise_enabled() -> bool:
    if _env_bool("COMFYUI_ADAPTIVE_DENOISE"):
        return True
    # Default on for character sticker tuning unless explicitly disabled
    raw = (os.getenv("COMFYUI_ADAPTIVE_DENOISE") or "true").strip().lower()
    return raw not in ("0", "false", "off", "no")


def resolve_adaptive_denoise(
    framing: str,
    *,
    layout_type: str = "",
    base: float | None = None,
) -> float:
    """closeup 0.28, action/reaction 0.40–0.45, full_body 0.42, lying 0.44."""
    if base is None:
        base = 0.32
    if not adaptive_denoise_enabled():
        return base

    key = (framing or "").strip().lower()
    lt = (layout_type or "").strip().lower()
    if lt == "lying_pose":
        return 0.44
    if lt == "reaction_burst":
        return 0.45
    table = {
        "closeup": 0.28,
        "upper_body": 0.34,
        "full_body": 0.42,
        "side_pose": 0.38,
        "diagonal_pose": 0.40,
        "action_pose": 0.40,
        "sitting_pose": 0.38,
        "leaning_pose": 0.36,
        "reaction_burst": 0.45,
        "lying_pose": 0.44,
    }
    return table.get(key, base)


def log_adaptive_denoise(cut_id: str, framing: str, denoise: float) -> None:
    print(
        f"[ADAPTIVE_DENOISE] cut={cut_id} framing={framing} denoise={denoise:.2f}",
        file=sys.stderr,
    )


def sampler_params_with_denoise(
    base: ComfyUISamplerParams,
    denoise: float,
) -> ComfyUISamplerParams:
    return ComfyUISamplerParams(
        steps=base.steps,
        cfg=base.cfg,
        denoise=denoise,
        sampler_name=base.sampler_name,
        scheduler=base.scheduler,
    )
