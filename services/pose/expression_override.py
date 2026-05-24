"""Emotion-specific facial acting overrides (canonical identity + extreme expression)."""

from __future__ import annotations

import os
import re
import sys
from collections import deque
from dataclasses import dataclass
from typing import Literal

from services.prompts.common_cut_spec import CutSpec

ExpressionStrength = Literal["low", "medium", "strong", "extreme"]

_STRENGTH_ORDER: tuple[ExpressionStrength, ...] = ("low", "medium", "strong", "extreme")

# Negative fragments that suppress readable sticker acting (filtered out).
_EXPRESSION_SUPPRESSING_NEGATIVE = frozenset(
    {
        "deformed face",
        "bad face",
        "bad anatomy face",
        "exaggerated expression",
        "overexaggerated face",
        "mutated face",
        "distorted face",
        "ugly face",
        "neutral smile",
        "same expression",
        "boring expression",
        "subtle expression",
        "minimal expression",
    }
)


@dataclass(frozen=True)
class ExpressionActingSpec:
    eye_style: str
    mouth_style: str
    positive_tags: str
    effects: str = ""


@dataclass(frozen=True)
class ExpressionOverride:
    emotion_category: str
    eye_style: str
    mouth_style: str
    intensity: ExpressionStrength
    positive_block: str
    effects: str
    rerolled: bool = False


# Multiple variants per category — diversity tracker avoids repeating last 2 combos.
_EMOTION_VARIANTS: dict[str, tuple[ExpressionActingSpec, ...]] = {
    "happy": (
        ExpressionActingSpec(
            "crescent_eyes",
            "huge_smile",
            "huge smile, crescent eyes, lifted cheeks, beaming face",
            "sparkle eyes",
        ),
        ExpressionActingSpec(
            "star_eyes",
            "open_grin",
            "star eyes, wide open grin, laughing mouth, joyful cheeks",
            "small sparkles",
        ),
        ExpressionActingSpec(
            "closed_happy_eyes",
            "toothy_grin",
            "closed happy arc eyes, big toothy grin, raised eyebrows",
        ),
        ExpressionActingSpec(
            "wide_happy_eyes",
            "big_u_smile",
            "wide happy eyes, big U-shaped smile, excited eyebrows",
            "blush marks optional",
        ),
    ),
    "angry": (
        ExpressionActingSpec(
            "angry_arc",
            "shouting_mouth",
            "sharp angled eyes, angry eyebrows, shouting open mouth, puffed cheeks",
            "anger mark",
        ),
        ExpressionActingSpec(
            "narrow_glare",
            "gritted_teeth",
            "narrow glaring eyes, gritted teeth, furrowed brows, tense mouth",
            "steam puff",
        ),
        ExpressionActingSpec(
            "v_shape_angry",
            "yelling",
            "inverted V angry eyes, yelling mouth, red cheeks",
            "comic anger veins",
        ),
    ),
    "sad": (
        ExpressionActingSpec(
            "teary_wide",
            "wobble_mouth",
            "giant teary eyes, trembling wavy mouth, downturned eyebrows",
            "streaming tears",
        ),
        ExpressionActingSpec(
            "crying_closed",
            "open_sob",
            "closed crying eyes, open sobbing mouth, tear streams on cheeks",
            "large tears",
        ),
        ExpressionActingSpec(
            "sad_dots",
            "small_frown",
            "sad dot eyes, small downturned mouth, droopy eyelids",
            "single tear",
        ),
    ),
    "love": (
        ExpressionActingSpec(
            "heart_eyes",
            "shy_smile",
            "heart-shaped eyes, shy curved smile, pink blush cheeks",
            "floating hearts",
        ),
        ExpressionActingSpec(
            "sparkle_love_eyes",
            "kiss_mouth",
            "sparkling love eyes, small kiss mouth, heavy blush",
            "heart stickers",
        ),
        ExpressionActingSpec(
            "closed_blush",
            "wavy_happy_mouth",
            "closed happy eyes with blush, wavy mouth, embarrassed smile",
            "blush lines",
        ),
    ),
    "surprise": (
        ExpressionActingSpec(
            "huge_round_eyes",
            "small_o_mouth",
            "huge round surprised eyes, small O mouth, raised brows",
            "sweat drop",
        ),
        ExpressionActingSpec(
            "shocked_wide",
            "gasp_mouth",
            "shocked wide eyes, gasping mouth, stiff eyebrows",
            "exclamation mood",
        ),
    ),
    "shy": (
        ExpressionActingSpec(
            "squint_shy",
            "wavy_embarrassed",
            "squint shy eyes, wavy embarrassed mouth, heavy blush cheeks",
            "blush",
        ),
        ExpressionActingSpec(
            "peek_eyes",
            "small_w_mouth",
            "peeking shy eyes, small wavy mouth, pink cheeks",
            "embarrassment steam",
        ),
    ),
    "tired": (
        ExpressionActingSpec(
            "half_closed",
            "droopy_mouth",
            "half closed sleepy eyes, droopy mouth, relaxed brows",
            "zzz optional",
        ),
        ExpressionActingSpec(
            "sleepy_lines",
            "yawn_mouth",
            "sleepy line eyes, yawning open mouth, tilted head feeling",
            "sleep bubble",
        ),
    ),
    "neutral": (
        ExpressionActingSpec(
            "dot_calm",
            "flat_line_mouth",
            "simple dot eyes, flat line mouth, calm brows",
        ),
        ExpressionActingSpec(
            "wide_neutral",
            "small_open",
            "wide neutral eyes, small open mouth, thinking look",
        ),
        ExpressionActingSpec(
            "side_glance_eyes",
            "smirk_small",
            "side glance eyes, tiny smirk mouth, one raised brow",
        ),
        ExpressionActingSpec(
            "blink_eyes",
            "pursed_mouth",
            "one eye blink, pursed mouth, unimpressed brows",
        ),
    ),
}

# Map free-text hints → category keys for overrides
_EXTRA_CATEGORY_ALIASES: tuple[tuple[str, str], ...] = (
    ("sad", "crying"),
    ("sad", "cry"),
    ("sad", "눈물"),
    ("sad", "울"),
    ("shy", "embarrassed"),
    ("shy", "부끄"),
    ("shy", "쑥"),
    ("tired", "sleepy"),
    ("tired", "졸"),
    ("tired", "피곤"),
    ("happy", "excited"),
    ("happy", "신남"),
    ("angry", "짜증"),
    ("angry", "화"),
)


def load_comfyui_expression_strength() -> ExpressionStrength:
    raw = (os.getenv("COMFYUI_EXPRESSION_STRENGTH") or "extreme").strip().lower()
    if raw in _STRENGTH_ORDER:
        return raw  # type: ignore[return-value]
    return "extreme"


def _intensity_rank(level: ExpressionStrength) -> int:
    return _STRENGTH_ORDER.index(level)


def dramatic_acting_priority_block(intensity: ExpressionStrength) -> str:
    parts = [
        "same sticker character",
        "preserve canonical character design",
        "BUT dramatically different facial acting for this cut",
        "extreme expression change from other cuts",
        "extreme mouth variation",
        "extreme eye shape variation",
        "big emotional acting",
        "dynamic body acting",
        "visible emotional gesture",
    ]
    if _intensity_rank(intensity) >= _intensity_rank("strong"):
        parts.extend(
            [
                "overacted facial expression",
                "emoji-like expression",
                "dramatic cartoon emotion",
                "instant emotion readability at small size",
            ]
        )
    if intensity == "extreme":
        parts.extend(
            [
                "force different eye shape for this emotion",
                "force different mouth shape for this emotion",
                "allow blush marks tears sweat drops comic symbols",
                "not a copy of previous cut face",
            ]
        )
    return ", ".join(parts)


def sticker_acting_positive_boost() -> str:
    return (
        "big mouth acting, emoji-like expression, dramatic cartoon emotion, "
        "overacted facial expression, readable at small size, instant emotion readability, "
        "kakao emoticon acting"
    )


def filter_expression_suppressing_negatives(negative: str) -> str:
    if not negative.strip():
        return negative
    parts = [p.strip() for p in negative.split(",") if p.strip()]
    kept: list[str] = []
    for part in parts:
        low = part.lower()
        if any(bad in low for bad in _EXPRESSION_SUPPRESSING_NEGATIVE):
            continue
        kept.append(part)
    return ", ".join(kept)


def _resolve_category(emotion_category: str, cut: CutSpec) -> str:
    cat = (emotion_category or "neutral").strip().lower()
    if cat in _EMOTION_VARIANTS:
        return cat
    blob = f"{cut.emotion} {cut.facial_expression} {cut.text} {cut.action}".lower()
    for key, hint in _EXTRA_CATEGORY_ALIASES:
        if hint in blob:
            return key
    for key in _EMOTION_VARIANTS:
        if key in blob:
            return key
    return "neutral"


def _build_positive_block(spec: ExpressionActingSpec, intensity: ExpressionStrength) -> str:
    chunks = [
        f"eye style {spec.eye_style}",
        f"mouth style {spec.mouth_style}",
        spec.positive_tags,
    ]
    if spec.effects and _intensity_rank(intensity) >= _intensity_rank("medium"):
        chunks.append(spec.effects)
    if _intensity_rank(intensity) >= _intensity_rank("strong"):
        chunks.append("facial expression is the main focus of this sticker")
    return ", ".join(chunks)


class ExpressionDiversityTracker:
    """Avoid identical eye+mouth combos across recent cuts (and repeated neutral smiles)."""

    def __init__(self, *, history_len: int = 2) -> None:
        self._combos: deque[tuple[str, str]] = deque(maxlen=history_len)
        self._mouth_history: deque[str] = deque(maxlen=4)

    def would_duplicate(self, eye_style: str, mouth_style: str) -> bool:
        combo = (eye_style, mouth_style)
        if combo in self._combos:
            return True
        if mouth_style in ("neutral_smile", "soft_smile") and mouth_style in self._mouth_history:
            return True
        return False

    def register(self, eye_style: str, mouth_style: str) -> None:
        self._combos.append((eye_style, mouth_style))
        self._mouth_history.append(mouth_style)


def resolve_expression_override(
    cut: CutSpec,
    emotion_category: str,
    *,
    intensity: ExpressionStrength | None = None,
    tracker: ExpressionDiversityTracker | None = None,
) -> ExpressionOverride:
    level = intensity or load_comfyui_expression_strength()
    category = _resolve_category(emotion_category, cut)
    variants = _EMOTION_VARIANTS.get(category) or _EMOTION_VARIANTS["neutral"]
    start = max(0, int(cut.id) - 1) if str(cut.id).isdigit() else 0
    rerolled = False
    chosen = variants[start % len(variants)]

    for offset in range(len(variants)):
        spec = variants[(start + offset) % len(variants)]
        if tracker and tracker.would_duplicate(spec.eye_style, spec.mouth_style):
            rerolled = True
            continue
        chosen = spec
        if tracker:
            tracker.register(spec.eye_style, spec.mouth_style)
        break
    else:
        chosen = variants[(start + 1) % len(variants)]
        rerolled = True
        if tracker:
            tracker.register(chosen.eye_style, chosen.mouth_style)

    return ExpressionOverride(
        emotion_category=category,
        eye_style=chosen.eye_style,
        mouth_style=chosen.mouth_style,
        intensity=level,
        positive_block=_build_positive_block(chosen, level),
        effects=chosen.effects,
        rerolled=rerolled,
    )


def log_expression_override(cut_id: str, override: ExpressionOverride) -> None:
    reroll_note = " rerolled=true" if override.rerolled else ""
    print(
        f"[EXPRESSION_OVERRIDE] cut={cut_id} category={override.emotion_category} "
        f"eye_style={override.eye_style} mouth_style={override.mouth_style} "
        f"intensity={override.intensity}{reroll_note}",
        file=sys.stderr,
    )
    if override.effects:
        print(f"[EXPRESSION_OVERRIDE] cut={cut_id} effects={override.effects}", file=sys.stderr)
