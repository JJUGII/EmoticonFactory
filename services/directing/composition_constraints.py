"""Hard composition positive/negative blocks per framing (not soft hints)."""

from __future__ import annotations

_PORTRAIT_BLOCKERS = (
    "centered portrait, passport photo, static front pose, symmetrical pose, "
    "mugshot, ID photo, floating head only, cropped at chest, bust only, "
    "shoulders square to camera, face-only sticker"
)

_FRAMING_POSITIVE: dict[str, str] = {
    "closeup": (
        "face closeup with head turned 20 degrees, expressive face acting, "
        "not centered passport, chin and hair visible"
    ),
    "upper_body": (
        "upper body waist-up, both arms visible in frame, off-center composition, "
        "clear hand gestures, not face-only crop"
    ),
    "full_body": (
        "entire body visible, legs visible, feet visible, full silhouette, "
        "full body sticker pose, not cropped portrait, head to toe in frame"
    ),
    "side_pose": (
        "body turned 35 degrees side view, profile acting line, asymmetric stance, "
        "visible arm on both sides of torso"
    ),
    "diagonal_pose": (
        "diagonal camera angle, dynamic body line, off-balance cute pose, "
        "torso twist, not straight-on"
    ),
    "action_pose": (
        "arms stretched, dynamic body line, torso twist, asymmetrical action pose, "
        "mid-motion freeze, limbs extended for readability, exaggerated acting"
    ),
    "sitting_pose": (
        "seated pose or floor pose, knees visible, legs bent, body weight low, "
        "not standing portrait"
    ),
    "leaning_pose": (
        "leaning torso forward or sideways, weight on one leg, dynamic lean, "
        "asymmetric body line"
    ),
    "lying_pose": (
        "body horizontal, lying on floor or bed, head low position, floor contact visible, "
        "full body sprawled, not standing"
    ),
    "reaction_burst": (
        "explosive reaction pose, arms out, body twist, dynamic shock acting, "
        "wide gesture, not calm portrait"
    ),
}


def composition_hard_positive(framing: str, layout_type: str = "") -> str:
    key = (framing or "").strip().lower()
    lt = (layout_type or "").strip().lower()
    if lt == "lying_pose":
        key = "lying_pose"
    elif lt == "reaction_burst" and key in ("closeup", "upper_body"):
        key = "reaction_burst"
    return _FRAMING_POSITIVE.get(key, _FRAMING_POSITIVE["upper_body"])


def composition_hard_negative() -> str:
    return _PORTRAIT_BLOCKERS
