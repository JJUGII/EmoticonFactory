"""Camera framing and composition styles for emoticon cuts."""

from __future__ import annotations

# All framing types requested
CAMERA_FRAMINGS: tuple[str, ...] = (
    "closeup",
    "upper_body",
    "medium_shot",
    "dynamic_angle",
    "side_view",
    "tilted_pose",
)

COMPOSITION_STYLES: dict[str, str] = {
    "closeup": "face-dominant emoticon framing, emotion readable in eyes and mouth",
    "upper_body": "waist-up sticker framing, hands and shoulders visible for gesture",
    "medium_shot": "knee-up or full torso visible, clear body language and pose line",
    "dynamic_angle": "slight dutch angle or diagonal energy, not flat passport pose",
    "side_view": "three-quarter or profile view, head turn breaks front-facing monotony",
    "tilted_pose": "head and shoulders tilted, playful asymmetry, off-center balance",
}

# layout_type from cut plan → preferred framing
_LAYOUT_FRAMING_MAP: dict[str, str] = {
    "face_closeup": "closeup",
    "half_body": "upper_body",
    "square_full_body": "medium_shot",
    "lying_pose": "medium_shot",
    "reaction_burst": "dynamic_angle",
}

# Rotate framing across 16 cuts for variety (used when layout is generic)
_FRAMING_ROTATION: tuple[str, ...] = (
    "upper_body",
    "closeup",
    "medium_shot",
    "dynamic_angle",
    "side_view",
    "tilted_pose",
    "upper_body",
    "medium_shot",
    "dynamic_angle",
    "closeup",
    "side_view",
    "tilted_pose",
    "upper_body",
    "medium_shot",
    "dynamic_angle",
    "closeup",
)

_STICKER_FRAMING_HINTS: dict[str, str] = {
    "closeup": "tight face closeup but NOT flat passport photo, slight head turn allowed",
    "upper_body": "upper body with visible arm gesture, off-center composition",
    "medium_shot": "full readable pose silhouette, weight shift on one leg",
    "dynamic_angle": "dynamic flat sticker angle, diagonal composition, action readable, no cinematic lighting",
    "side_view": "three-quarter side view, body turned 25-45 degrees",
    "tilted_pose": "tilted head and shoulders, cute asymmetry, not symmetrical bust shot",
}

_ILLUSTRATION_FRAMING_HINTS: dict[str, str] = {
    "closeup": "intimate portrait closeup, soft background bokeh allowed",
    "upper_body": "upper body portrait with gentle environmental hint",
    "medium_shot": "full character in scene, cozy staging, partial background",
    "dynamic_angle": "cinematic angle, storytelling composition, soft depth",
    "side_view": "profile or three-quarter portrait, atmospheric lighting",
    "tilted_pose": "artistic tilt, editorial illustration composition",
}


def framing_for_layout(layout_type: str, cut_index: int) -> str:
    lt = (layout_type or "").strip().lower()
    if lt in _LAYOUT_FRAMING_MAP:
        return _LAYOUT_FRAMING_MAP[lt]
    return _FRAMING_ROTATION[cut_index % len(_FRAMING_ROTATION)]


def composition_style_for_framing(framing: str) -> str:
    return COMPOSITION_STYLES.get(framing, COMPOSITION_STYLES["upper_body"])


def framing_prompt_hint(framing: str, *, output_mode: str) -> str:
    hints = (
        _ILLUSTRATION_FRAMING_HINTS if output_mode == "illustration" else _STICKER_FRAMING_HINTS
    )
    return hints.get(framing, hints["upper_body"])


def anti_frontal_negative() -> str:
    return (
        "static front passport portrait, symmetrical bust only, shoulders square to camera, "
        "floating head only, no body gesture, mugshot, ID photo"
    )
