"""COMFYUI_ACTING_INTENSITY — face, hands, body, composition force level."""

from __future__ import annotations

import os
from typing import Literal

ActingIntensity = Literal["low", "medium", "strong", "extreme"]

_ORDER: tuple[ActingIntensity, ...] = ("low", "medium", "strong", "extreme")


def load_comfyui_acting_intensity() -> ActingIntensity:
    raw = (os.getenv("COMFYUI_ACTING_INTENSITY") or "extreme").strip().lower()
    if raw in _ORDER:
        return raw  # type: ignore[return-value]
    return "extreme"


def _rank(level: ActingIntensity) -> int:
    return _ORDER.index(level)


def acting_intensity_positive_block(level: ActingIntensity) -> str:
    parts = [
        "body acting priority over face-only portrait",
        "big body gesture",
        "readable silhouette",
        "full arm acting",
        "clear pose line",
        "dynamic body language",
        "visible hands and arms",
        "cartoon acting pose",
    ]
    if _rank(level) >= _rank("strong"):
        parts.extend(
            [
                "extreme pose change per cut",
                "different camera framing per cut",
                "hands must read emotion at thumbnail size",
            ]
        )
    if level == "extreme":
        parts.extend(
            [
                "force different framing from previous cuts",
                "force different hand gesture from previous cuts",
                "force different full body pose from previous cuts",
                "exaggerated kakao emoticon staging",
                "not a repeated bust shot",
            ]
        )
    return ", ".join(parts)
