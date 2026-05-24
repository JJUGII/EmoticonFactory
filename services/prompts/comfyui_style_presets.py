"""ComfyUI sticker style presets (prompt vocabulary + sampler tuning)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Literal

StylePresetName = Literal["default", "kakao_flat"]


@dataclass(frozen=True)
class ComfyUISamplerParams:
    steps: int
    cfg: float
    denoise: float
    sampler_name: str = "euler"
    scheduler: str = "normal"


@dataclass(frozen=True)
class ComfyUIStylePreset:
    name: StylePresetName
    positive_core: str
    negative_core: str
    sampler: ComfyUISamplerParams
    positive_suffix: str = ""
    negative_suffix: str = ""


# Shared anti-anime / anti-illustration negatives for Kakao flat stickers
_KAKAO_FLAT_NEGATIVE_EXTRA = (
    "anime screenshot, pixiv, detailed anime rendering, cinematic anime, "
    "high detail anime, light novel illustration, vtuber style, "
    "anime illustration, dramatic lighting, cinematic composition, soft shading, "
    "detailed shading, glowing rim light, anime blush, detailed hair strands, "
    "complex highlights, realistic shading, 3d render, volumetric light, rim light, "
    "detailed eyelashes, detailed hair rendering, japanese anime portrait, "
    "cel shading gradients, airbrush skin, painterly portrait"
)

_KAKAO_FLAT_POSITIVE_CORE = (
    "flat 2d sticker, kakao talk sticker style, mobile messenger sticker, "
    "simple kakao emoticon character, exaggerated facial expression, "
    "dynamic pose and composition, big readable emotion, simple clean outline, "
    "simple vector-like shading, minimal shading, flat pastel fill, limited color palette, "
    "simple rounded facial features, simple eyes, simple mouth, "
    "clean sticker silhouette, reduced detail, minimal lighting, no dramatic shadows, "
    "clean white background, minimal background, cute overreaction, "
    "readable full-body silhouette, domestic messenger sticker art"
)

_DEFAULT_STICKER_POSITIVE = (
    "simple chibi sticker, kakao emoticon style, exaggerated facial expression, "
    "dynamic pose and composition, big readable emotion, thick outline, flat pastel colors, "
    "clean white background, minimal background, cute overreaction, readable full-body silhouette"
)

_DEFAULT_STICKER_NEGATIVE = (
    "realistic, cinematic, detailed background, complex lighting, full anime illustration, "
    "photorealistic, different character, animal ears, paw, fur, tail, extra fingers, "
    "text artifacts, blurry, low quality, busy background"
)

_PRESETS: dict[str, ComfyUIStylePreset] = {
    "default": ComfyUIStylePreset(
        name="default",
        positive_core=_DEFAULT_STICKER_POSITIVE,
        negative_core=_DEFAULT_STICKER_NEGATIVE,
        sampler=ComfyUISamplerParams(steps=28, cfg=6.5, denoise=0.52),
    ),
    "kakao_flat": ComfyUIStylePreset(
        name="kakao_flat",
        positive_core=_KAKAO_FLAT_POSITIVE_CORE,
        negative_core=(
            "realistic, photorealistic, detailed background, complex lighting, busy background, "
            "different character, animal ears, paw, fur, tail, extra fingers, "
            "text artifacts, blurry, low quality, watermark, logo, "
            + _KAKAO_FLAT_NEGATIVE_EXTRA
        ),
        sampler=ComfyUISamplerParams(steps=20, cfg=5.0, denoise=0.48),
        positive_suffix="flat messenger sticker, not anime illustration",
        negative_suffix="anime portrait, pixiv style, SDXL anime rendering",
    ),
}


def _env_float(name: str, default: float, *, lo: float, hi: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return max(lo, min(hi, v))


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    return max(lo, min(hi, v))


def _character_mode_sampler_defaults() -> ComfyUISamplerParams:
    """Lower denoise for canonical sticker acting (img2img stays on-design)."""
    return ComfyUISamplerParams(steps=20, cfg=4.5, denoise=0.28)


def load_comfyui_style_preset(*, source_mode: str | None = None) -> ComfyUIStylePreset:
    """Resolve preset from ``EMOTICON_STYLE_PRESET`` with optional sampler env overrides."""
    key = (os.getenv("EMOTICON_STYLE_PRESET") or "kakao_flat").strip().lower()
    base = _PRESETS.get(key) or _PRESETS["kakao_flat"]
    sm = (source_mode or os.getenv("EMOTICON_SOURCE_MODE") or "").strip().lower()
    sampler_base = _character_mode_sampler_defaults() if sm == "character" else base.sampler

    steps = _env_int("COMFYUI_STEPS", sampler_base.steps, lo=8, hi=60)
    cfg = _env_float("COMFYUI_CFG", sampler_base.cfg, lo=1.0, hi=15.0)
    denoise = _env_float("COMFYUI_DENOISE", sampler_base.denoise, lo=0.1, hi=0.95)
    sampler_name = (os.getenv("COMFYUI_SAMPLER") or base.sampler.sampler_name).strip() or "euler"
    scheduler = (os.getenv("COMFYUI_SCHEDULER") or base.sampler.scheduler).strip() or "normal"

    sampler = ComfyUISamplerParams(
        steps=steps,
        cfg=cfg,
        denoise=denoise,
        sampler_name=sampler_name,
        scheduler=scheduler,
    )
    if sampler == sampler_base and sampler_base == base.sampler and key in _PRESETS:
        return base
    return ComfyUIStylePreset(
        name=base.name,
        positive_core=base.positive_core,
        negative_core=base.negative_core,
        sampler=sampler,
        positive_suffix=base.positive_suffix,
        negative_suffix=base.negative_suffix,
    )


def sticker_prompt_cores(preset: ComfyUIStylePreset | None = None) -> tuple[str, str]:
    p = preset or load_comfyui_style_preset()
    pos = p.positive_core
    neg = p.negative_core
    if p.positive_suffix:
        pos = f"{pos}, {p.positive_suffix}"
    if p.negative_suffix:
        neg = f"{neg}, {p.negative_suffix}"
    return pos, neg


def apply_sampler_preset(
    workflow: dict[str, Any],
    preset: ComfyUIStylePreset | None = None,
    *,
    source_mode: str | None = None,
) -> int:
    """Patch all ``KSampler`` nodes in a ComfyUI prompt graph. Returns count patched."""
    p = preset or load_comfyui_style_preset(source_mode=source_mode)
    s = p.sampler
    patched = 0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if str(node.get("class_type") or "") != "KSampler":
            continue
        inputs = node.setdefault("inputs", {})
        inputs["steps"] = s.steps
        inputs["cfg"] = s.cfg
        inputs["denoise"] = s.denoise
        inputs["sampler_name"] = s.sampler_name
        inputs["scheduler"] = s.scheduler
        patched += 1
    return patched


def log_comfyui_style_preset(
    preset: ComfyUIStylePreset | None = None,
    *,
    source_mode: str | None = None,
) -> None:
    p = preset or load_comfyui_style_preset(source_mode=source_mode)
    s = p.sampler
    print(
        f"[COMFYUI] style_preset={p.name} steps={s.steps} cfg={s.cfg} denoise={s.denoise} "
        f"sampler={s.sampler_name} scheduler={s.scheduler}",
        file=sys.stderr,
    )
