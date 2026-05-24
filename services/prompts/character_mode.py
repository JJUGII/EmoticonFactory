"""ComfyUI prompts for ``EMOTICON_SOURCE_MODE=character`` (canonical sticker acting)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.pose.expression_override import (
    ExpressionOverride,
    dramatic_acting_priority_block,
    sticker_acting_positive_boost,
)
from services.prompts.prompt_profiles import EnginePromptTuning

if TYPE_CHECKING:
    from services.pose.pose_director import CutPosePlan


def character_mode_positive_core() -> str:
    """Identity outline only — eye/mouth shape vary per cut via expression override."""
    return (
        "same sticker character, same mascot character, same hairstyle shape, "
        "same outfit color block, same chibi proportions, same thick outline style, "
        "same flat 2d sticker design, preserve canonical character design, "
        "sticker character acting, not a new character design"
    )


def character_mode_negative_core() -> str:
    return (
        "realistic portrait, photo rendering, skin texture, detailed hair strands, "
        "anime illustration, pixiv style, vtuber, cinematic lighting, red rim light, "
        "complex shading, different character design, redesigned face, changed hairstyle, "
        "changed outfit, same person photo, photorealistic face, "
        "detailed skin pores, portrait photography, identity drift, new mascot, "
        "boring neutral face, subtle expression, passport photo calm face"
    )


def character_mode_identity_block(
    tuning: EnginePromptTuning,
    pose_plan: CutPosePlan | None,
) -> str:
    freedom = pose_plan.pose_freedom if pose_plan else "medium"
    return (
        f"canonical sticker lock {tuning.identity_lock:.2f}, "
        f"pose variation {tuning.pose_variation:.2f}, "
        f"pose freedom {freedom}, "
        "same character silhouette and outfit colors, "
    )


def character_mode_acting_block(expression: ExpressionOverride) -> str:
    return (
        f"{dramatic_acting_priority_block(expression.intensity)}, "
        f"{expression.positive_block}, "
        f"{sticker_acting_positive_boost()}, "
        f"facial_expression from template: {expression.emotion_category}"
    )


def character_mode_reference_note() -> str:
    return (
        "Reference: canonical_character.png — fixed sticker identity; "
        "extreme expression and pose acting per cut."
    )
