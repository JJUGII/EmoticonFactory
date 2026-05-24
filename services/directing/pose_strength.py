"""COMFYUI_POSE_STRENGTH — repeat pose tokens in prompts."""

from __future__ import annotations

import os
from typing import Literal

PoseStrength = Literal["low", "medium", "strong", "extreme"]

_ORDER: tuple[PoseStrength, ...] = ("low", "medium", "strong", "extreme")


def load_comfyui_pose_strength() -> PoseStrength:
    raw = (os.getenv("COMFYUI_POSE_STRENGTH") or "strong").strip().lower()
    if raw in _ORDER:
        return raw  # type: ignore[return-value]
    return "strong"


def pose_strength_positive_block(
    base_tokens: str,
    *,
    level: PoseStrength | None = None,
) -> str:
    level = level or load_comfyui_pose_strength()
    if level == "low":
        return base_tokens
    if level == "medium":
        return f"{base_tokens}, {base_tokens}"
    if level == "strong":
        return f"{base_tokens}, {base_tokens}, exaggerated body acting"
    # extreme
    return (
        f"{base_tokens}, {base_tokens}, {base_tokens}, "
        "dynamic pose, dynamic pose, exaggerated body acting, exaggerated body acting"
    )
