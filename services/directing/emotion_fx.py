"""Comic emotion FX — short tags only."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from services.directing.acting_intensity import ActingIntensity, load_comfyui_acting_intensity


@dataclass(frozen=True)
class EmotionFxSpec:
    fx_ids: tuple[str, ...]
    positive_tags: str


# emotion → (fx_ids, short comma tags)
_EMOTION_FX: dict[str, tuple[tuple[str, ...], str], ...] = {
    "happy": (
        (("sparkle",), "sparkle, small hearts"),
        (("impact_lines",), "joy lines, sparkle"),
    ),
    "love": (
        (("hearts",), "heart stickers, pink blush"),
        (("hearts", "glow"), "floating hearts"),
    ),
    "cheering": (
        (("sparkle", "impact_lines"), "sparkle, cheer lines"),
        (("sparkle",), "star burst"),
    ),
    "sad": (
        (("tears",), "tears, sad lines"),
        (("tears",), "teardrops"),
    ),
    "angry": (
        (("anger_mark",), "anger mark, steam puff"),
        (("anger_mark",), "vein pop, steam"),
    ),
    "surprised": (
        (("sweat_drop",), "sweat drop, shock lines"),
        (("impact_lines",), "exclamation lines"),
    ),
    "embarrassed": (
        (("blush",), "blush marks"),
        (("blush", "wavy_lines"), "blush, wavy lines"),
    ),
    "shy": (
        (("blush",), "blush marks"),
        (("blush",), "embarrassed blush"),
    ),
    "sleepy": (
        (("zzz",), "zzz bubble"),
        (("dizzy_spiral",), "dizzy eyes"),
    ),
    "tired": (
        (("zzz",), "zzz bubble"),
        (("sweat_drop",), "tired sweat"),
    ),
    "awkward": (
        (("sweat_drop",), "awkward sweat"),
        (("dots",), "ellipsis dots"),
    ),
    "hungry": (
        (("drool",), "drool drop"),
        (("sparkle",), "food sparkle"),
    ),
    "neutral": (
        (("dots",), "pause dots"),
        (("sweat_drop",), "sweat drop"),
    ),
}

_ALIASES = {
    "surprise": "surprised",
    "shy": "embarrassed",
    "tired": "sleepy",
}


def _fx_category(emotion_category: str) -> str:
    cat = (emotion_category or "neutral").strip().lower()
    return _ALIASES.get(cat, cat if cat in _EMOTION_FX else "neutral")


def resolve_emotion_fx(
    emotion_category: str,
    cut_index: int,
    *,
    intensity: ActingIntensity | None = None,
) -> EmotionFxSpec:
    level = intensity or load_comfyui_acting_intensity()
    cat = _fx_category(emotion_category)
    variants = _EMOTION_FX.get(cat) or _EMOTION_FX["neutral"]
    fx_ids, tags = variants[cut_index % len(variants)]
    if level in ("low", "medium"):
        tags = tags.split(",")[0].strip()
    return EmotionFxSpec(fx_ids=fx_ids, positive_tags=tags)


def log_emotion_fx(cut_id: str, spec: EmotionFxSpec) -> None:
    fx_csv = ",".join(spec.fx_ids)
    print(f"[EMOTION_FX] cut={cut_id} fx={fx_csv}", file=sys.stderr)
