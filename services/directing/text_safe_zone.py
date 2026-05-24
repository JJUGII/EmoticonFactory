"""Reserve bottom 20–25% for caption overlay — no face/hands in text band."""

from __future__ import annotations


def text_safe_zone_positive(*, text_position: str = "bottom") -> str:
    pos = (text_position or "bottom").strip().lower()
    if pos == "top":
        return (
            "keep top 22 percent of frame empty for caption overlay, "
            "no face or hands in top caption band, character placed lower in frame"
        )
    if pos in ("left", "right"):
        return (
            "keep side caption margin clear, no hands crossing outer 18 percent of frame"
        )
    return (
        "keep bottom 25 percent of frame empty for caption overlay, "
        "no face hands or critical body in bottom text safe zone, "
        "character placed upper-center, feet and hands above caption band, "
        "composition leaves lower quarter blank"
    )


def text_safe_zone_negative() -> str:
    return (
        "face in bottom quarter, hands in bottom caption area, "
        "important gesture blocked by text zone, character centered in lower half only"
    )
