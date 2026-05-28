"""Theme-aware Kakao-chat context hints for cut planning (meta keys consumed by PromptBuilder)."""

from __future__ import annotations

from typing import Any


def _theme_bucket(theme: str) -> str:
    t = (theme or "").strip().lower()
    if any(k in t for k in ("사랑", "연애", "하트", "love", "crush")):
        return "love"
    if any(k in t for k in ("일상", "daily", "routine")):
        return "daily"
    if any(k in t for k in ("감사", "thanks", "thank")):
        return "thanks"
    if any(k in t for k in ("위로", "comfort", "힘내")):
        return "comfort"
    return "generic"


def enrich_cut_plan_item(theme: str, item: dict[str, Any]) -> None:
    """Attach ``_*`` keys for PromptBuilder; ignored by JSON export / pose schema."""
    bucket = _theme_bucket(theme)
    text = str(item.get("text", "")).strip()
    emotion = str(item.get("emotion", "")).strip()
    action = str(item.get("action", "")).strip()
    facial = str(item.get("facial_expression", "")).strip()
    body_pose = str(item.get("body_pose", "")).strip()
    prop = str(item.get("prop", "none")).strip()
    motion = str(item.get("motion_hint", "")).strip()

    intro = {
        "love": (
            "Kakao love/affection sticker pack: everyday couple chat moments "
            "(sweet, shy, playful, jealous, sleepy-goodnight) — one clear beat per sticker."
        ),
        "daily": (
            "Kakao daily-life sticker pack: small relatable chat moments — cozy, witty, low-drama."
        ),
        "thanks": (
            "Kakao gratitude sticker pack: polite, warm, sincere micro-moments."
        ),
        "comfort": (
            "Kakao comfort / cheer-up sticker pack: gentle empathy without heavy drama."
        ),
        "generic": (
            "Korean mobile messenger emoticon pack: instant emotional read at thumbnail size."
        ),
    }[bucket]

    item["_kakao_theme_moment_en"] = intro
    item["_kakao_phrase_context_en"] = (
        f"Chat moment for Korean caption idea «{text}» (do NOT paint letters): "
        f"emotion={emotion}; gesture/body={body_pose}; eyes/face={facial}; "
        f"action beat={action}; micro-motion={motion}; prop={prop}."
    )
    item["_kakao_readability_en"] = (
        "Exaggerated but cute expressions; independently usable sticker; "
        "emotionally readable silhouette; soft pastel emotional tone; "
        "Korean mobile messenger emoticon feel."
    )
