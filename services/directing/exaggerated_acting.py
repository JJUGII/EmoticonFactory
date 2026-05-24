"""Concise Kakao sticker acting presets (emotion → short SDXL keywords)."""

from __future__ import annotations

from dataclasses import dataclass

# emotion → rotating short pose lines (one core action each)
CONCISE_ACTING_PRESETS: dict[str, tuple[str, ...]] = {
    "love": (
        "finger heart",
        "big heart pose, arms forward",
        "hands on cheeks",
        "hug arms open",
    ),
    "happy": (
        "arms up cheer",
        "big wave",
        "happy jump",
        "clap hands",
    ),
    "cheering": (
        "victory arms up",
        "jump cheer",
        "fist pump",
        "big clap",
    ),
    "angry": (
        "angry stomp",
        "fist forward",
        "hands on hips",
        "point finger",
    ),
    "sad": (
        "hug knees",
        "wipe tears",
        "slump shoulders",
        "curl on floor",
    ),
    "sleepy": (
        "yawn hand",
        "lying sleepy",
        "rub eyes",
        "nod off",
    ),
    "embarrassed": (
        "hide face hands",
        "blush peek",
        "nervous scratch",
        "small awkward wave",
    ),
    "surprised": (
        "hands on cheeks",
        "jump back",
        "wide eyes gasp",
        "arms out shock",
    ),
    "awkward": (
        "scratch head",
        "finger touch nervous",
        "tiny wave",
        "sideways shrug",
    ),
    "hungry": (
        "hold empty bowl",
        "rub belly",
        "drool cute",
        "ready to eat",
    ),
    "neutral": (
        "small wave",
        "thinking chin",
        "shrug shoulders",
        "idle stand",
    ),
}

# Short staging accent (one phrase) — paired with preset, not stacked sentences
KAKAO_ACTING_PATTERNS: dict[str, str] = {
    "side_sway": "side sway",
    "floor_sprawl": "lying down",
    "jump": "mid jump",
    "float": "light float",
    "head_bonk": "head bonk",
    "wave_arms": "wave arms",
    "bounce": "small bounce",
    "punch_air": "air punch",
    "bow": "deep bow",
    "finger_heart": "finger heart",
    "cheer_jump": "cheer jump",
    "curl_up": "curl up",
    "head_tilt": "head tilt",
    "spin": "dizzy spin",
    "peek": "peek shy",
    "stomp": "foot stomp",
}

_EMOTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "love": ("finger_heart", "head_tilt", "wave_arms", "bounce"),
    "happy": ("cheer_jump", "wave_arms", "jump", "bounce"),
    "cheering": ("cheer_jump", "jump", "wave_arms", "bounce"),
    "angry": ("stomp", "punch_air", "side_sway", "head_bonk"),
    "sad": ("floor_sprawl", "curl_up", "bow", "head_bonk"),
    "surprised": ("jump", "spin", "peek", "float"),
    "embarrassed": ("peek", "head_tilt", "curl_up", "side_sway"),
    "sleepy": ("floor_sprawl", "curl_up", "float", "head_tilt"),
    "awkward": ("side_sway", "peek", "head_bonk", "spin"),
    "hungry": ("bow", "head_tilt", "bounce", "wave_arms"),
    "neutral": ("head_tilt", "side_sway", "wave_arms", "bow"),
}

# Internal pose categories → preset bucket
_CATEGORY_ALIASES: dict[str, str] = {
    "tired": "sleepy",
    "shy": "embarrassed",
    "surprise": "surprised",
}

_STICKER_CORE = "big gesture, clear silhouette"


@dataclass(frozen=True)
class ConciseActingPreset:
    emotion: str
    pattern_id: str
    keywords: str
    template_hint: str


def normalize_acting_emotion(emotion_category: str, *text_parts: str) -> str:
    cat = (emotion_category or "neutral").strip().lower()
    blob = " ".join([cat, *(p for p in text_parts if p)]).lower()
    if any(k in blob for k in ("배고", "hungry", "먹고", "밥")):
        return "hungry"
    if any(k in blob for k in ("응원", "cheer", "fighting", "파이팅", "화이팅")):
        return "cheering"
    cat = _CATEGORY_ALIASES.get(cat, cat)
    if cat in CONCISE_ACTING_PRESETS:
        return cat
    return "neutral"


def concise_acting_for_cut(
    emotion_category: str,
    cut_index: int,
    *text_parts: str,
) -> str:
    cat = normalize_acting_emotion(emotion_category, *text_parts)
    presets = CONCISE_ACTING_PRESETS.get(cat) or CONCISE_ACTING_PRESETS["neutral"]
    return presets[cut_index % len(presets)]


def pattern_for_cut(emotion_category: str, cut_index: int, *text_parts: str) -> tuple[str, str]:
    cat = normalize_acting_emotion(emotion_category, *text_parts)
    ids = _EMOTION_PATTERNS.get(cat) or _EMOTION_PATTERNS["neutral"]
    pid = ids[cut_index % len(ids)]
    return pid, KAKAO_ACTING_PATTERNS.get(pid, KAKAO_ACTING_PATTERNS["head_tilt"])


def concise_template_hint_for_cut(
    emotion_category: str,
    cut_index: int,
    *text_parts: str,
) -> str:
    """Max ~1 short line for layout logs / OpenAI (no long template JSON prose)."""
    preset = resolve_concise_acting_preset(emotion_category, cut_index, *text_parts)
    return preset.template_hint


def resolve_concise_acting_preset(
    emotion_category: str,
    cut_index: int,
    *text_parts: str,
) -> ConciseActingPreset:
    cat = normalize_acting_emotion(emotion_category, *text_parts)
    keywords = concise_acting_for_cut(cat, cut_index)
    pattern_id, pattern_kw = pattern_for_cut(cat, cut_index)
    # Single comma line: preset + one accent (avoid duplicate if same idea)
    if pattern_kw.lower() in keywords.lower():
        line = f"{keywords}, {_STICKER_CORE}"
    else:
        line = f"{keywords}, {pattern_kw}, {_STICKER_CORE}"
    return ConciseActingPreset(
        emotion=cat,
        pattern_id=pattern_id,
        keywords=line,
        template_hint=keywords,
    )
