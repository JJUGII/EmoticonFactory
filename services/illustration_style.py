"""Illustration texture / rendering intensity for prompts (v0.6 anti-flat-AI)."""

from __future__ import annotations

# Per-candidate presets when count == 3: A Kakao vector, B semi-watercolor, C storybook
CANDIDATE_STYLE_INTENSITIES: tuple[float, float, float] = (0.0, 0.5, 1.0)

_ILLUSTRATION_TEXTURE_FULL = (
    "soft watercolor texture, "
    "subtle hand-drawn imperfections, "
    "organic line variation, "
    "slightly uneven brush edges, "
    "natural fur flow, "
    "storybook illustration feel, "
    "warm emotional lighting, "
    "soft shading, "
    "gentle painterly rendering, "
    "non-generic handmade feeling, "
    "premium pet illustration quality, "
    "avoid flat corporate mascot style, "
    "avoid overly clean vector symmetry, "
    "avoid emoji-like simplification"
)

_CHARACTER_ART_TEXTURE_LOCK_FULL = (
    "preserve original illustration texture, "
    "preserve original rendering depth, "
    "preserve watercolor softness, "
    "preserve line-art personality, "
    "do not flatten into flat vector mascot, "
    "do not replace with simplified cartoon geometry"
)


def clamp_style_intensity(value: float) -> float:
    """Clamp CLI ``--style-intensity`` to 0.0–1.0."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.5
    return max(0.0, min(1.0, v))


def candidate_style_intensity_for_index(index: int, count: int = 3) -> float:
    """1-based candidate index → style intensity (3-pack uses fixed A/B/C presets)."""
    i = max(1, int(index))
    n = max(1, int(count))
    if n == 3 and 1 <= i <= 3:
        return CANDIDATE_STYLE_INTENSITIES[i - 1]
    if n <= 1:
        return 0.5
    return clamp_style_intensity((i - 1) / float(n - 1))


def candidate_style_label(intensity: float) -> str:
    v = clamp_style_intensity(intensity)
    if v < 0.2:
        return "kakao_sticker_vector"
    if v < 0.75:
        return "semi_watercolor"
    return "storybook_illustration"


def _blend_phrase(low: str, high: str, t: float) -> str:
    """Linear blend: at t=0 prefer low, at t=1 prefer high, mid mixes both."""
    t = clamp_style_intensity(t)
    if t <= 0.08:
        return low
    if t >= 0.92:
        return high
    if t < 0.45:
        return f"{low} {high}"
    if t > 0.55:
        return f"{high} {low}"
    return f"{low} {high}"


def illustration_texture_fragment(style_intensity: float) -> str:
    """``[Illustration texture style]`` block scaled by intensity."""
    t = clamp_style_intensity(style_intensity)
    low = (
        "clean KakaoTalk sticker vector look, flat pastel fills, thick soft outline, "
        "readable at small size, minimal texture noise"
    )
    high = _ILLUSTRATION_TEXTURE_FULL
    body = _blend_phrase(low, high, t)
    return f"[Illustration texture style] {body}. "


def character_art_texture_lock_fragment(
    style_intensity: float, *, direct_canonical: bool
) -> str:
    if not direct_canonical:
        return ""
    t = clamp_style_intensity(style_intensity)
    if t < 0.15:
        return ""
    low = "preserve line-art personality; avoid emoji-like simplification"
    body = _blend_phrase(low, _CHARACTER_ART_TEXTURE_LOCK_FULL, t)
    return f"[Character-art texture lock] {body}. "


def sheet_illustration_reference_prompt_fragment(style_intensity: float) -> str:
    """Illustration reference sheet (not flat turnaround vector)."""
    t = clamp_style_intensity(style_intensity)
    base = (
        "professional illustrated character reference sheet, "
        "storybook pet mascot sheet, "
        "same exact character identity, "
        "same fur pattern, same eyes, same face mask, same rendering style, "
        "not flat vector art, not corporate mascot style, "
        "white clean background, no text, no watermark"
    )
    if t < 0.25:
        return (
            f"{base}; clean Kakao emoticon turnaround panels, simplified flat sticker colors"
        )
    if t < 0.75:
        return f"{base}; soft watercolor illustration, gentle painterly shading"
    return (
        f"{base}; soft watercolor illustration, high detail emotional mascot, "
        "subtle hand-drawn imperfections, organic line variation, premium pet illustration"
    )


def candidate_prompt_style_fragment(style_intensity: float) -> str:
    t = clamp_style_intensity(style_intensity)
    label = candidate_style_label(t)
    if t < 0.2:
        return (
            f"[Candidate style {label}] KakaoTalk big-emoticon sticker vector style: "
            "thick soft outline, flat pastel fills, high small-size readability. "
        )
    if t < 0.75:
        return (
            f"[Candidate style {label}] Semi-watercolor emoticon character: "
            "soft shading, gentle brush edges, warm pastel palette, handmade sticker feel. "
        )
    return (
        f"[Candidate style {label}] Storybook premium pet illustration: "
        "watercolor softness, organic fur flow, emotional lighting, "
        "avoid stock mascot / Midjourney generic look. "
    )
