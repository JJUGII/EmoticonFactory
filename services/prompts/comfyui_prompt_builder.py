"""Keyword prompts for ComfyUI / SDXL workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from services.character_profile import CharacterProfile
from services.directing.sticker_readability import (
    sticker_readability_negative,
    sticker_readability_positive,
)
from services.directing.text_separation import (
    no_text_generation_negative,
    no_text_generation_positive,
)
from services.pose.expression_override import (
    ExpressionOverride,
    dramatic_acting_priority_block,
    filter_expression_suppressing_negatives,
    resolve_expression_override,
    sticker_acting_positive_boost,
)

if TYPE_CHECKING:
    from services.pose.pose_director import CutPosePlan
from services.prompts.character_mode import (
    character_mode_acting_block,
    character_mode_identity_block,
    character_mode_negative_core,
    character_mode_positive_core,
)
from services.prompts.common_cut_spec import CutSpec
from services.prompts.comfyui_style_presets import (
    load_comfyui_style_preset,
    sticker_prompt_cores,
)
from services.prompts.entity_profile import EntityProfile
from services.prompts.openai_prompt_builder import _sticker_emotion_boost
from services.prompts.human_descriptors import human_comfyui_negative_extra, human_comfyui_positive
from services.prompts.prompt_profiles import OutputMode, PromptPipelineSettings, SourceMode

_ILLUSTRATION_POSITIVE_CORE = (
    "soft watercolor character illustration, warm storybook style, beautiful portrait, "
    "gentle lighting, detailed hair, cozy atmosphere, pastel tone, clean composition"
)

_ILLUSTRATION_NEGATIVE_CORE = (
    "harsh sticker outline, chibi deformation, photorealistic, busy background, "
    "text artifacts, blurry, low quality, different character, watermark"
)


@dataclass(frozen=True)
class ComfyUIPromptResult:
    positive: str
    negative: str
    eye_style: str = ""
    mouth_style: str = ""
    expression_intensity: str = ""


def _is_character_source(source_mode: SourceMode) -> bool:
    return source_mode == "character"


def _human_negative_extra(entity: EntityProfile, *, source_mode: SourceMode) -> str:
    if _is_character_source(source_mode):
        return ""
    if entity.is_human:
        return f", {human_comfyui_negative_extra()}"
    return ""


def _expression_face_kw(cut: CutSpec, expression: ExpressionOverride | None) -> str:
    if expression is None:
        return f"face {cut.facial_expression}"
    return (
        f"face acting {cut.facial_expression}, eye_style={expression.eye_style}, "
        f"mouth_style={expression.mouth_style}"
    )


def _apply_sticker_negatives(negative: str) -> str:
    return filter_expression_suppressing_negatives(negative)


def _resolve_expression(
    cut: CutSpec,
    pose_plan: CutPosePlan | None,
    expression_override: ExpressionOverride | None,
) -> ExpressionOverride:
    if expression_override is not None:
        return expression_override
    category = pose_plan.emotion_category if pose_plan else "neutral"
    return resolve_expression_override(cut, category)


def _sticker_directing_layers(
    pose_plan: CutPosePlan | None,
    *,
    output_mode: OutputMode,
    no_ai_text: bool,
) -> tuple[str, str]:
    """Extra positive/negative for sticker directing (body, readability, no text)."""
    if output_mode != "sticker":
        return "", ""
    pos_parts = [sticker_readability_positive()]
    if pose_plan and pose_plan.body_acting_block:
        pos_parts.append(pose_plan.body_acting_block)
    if pose_plan and pose_plan.execution_hard_positive:
        pos_parts.append(pose_plan.execution_hard_positive)
    if pose_plan and pose_plan.pose_strength_block:
        pos_parts.append(pose_plan.pose_strength_block)
    if pose_plan and pose_plan.text_safe_positive:
        pos_parts.append(pose_plan.text_safe_positive)
    if no_ai_text:
        pos_parts.append(no_text_generation_positive())
    neg_parts = [sticker_readability_negative()]
    if pose_plan and pose_plan.execution_hard_negative:
        neg_parts.append(pose_plan.execution_hard_negative)
    if pose_plan and pose_plan.text_safe_negative:
        neg_parts.append(pose_plan.text_safe_negative)
    if no_ai_text:
        neg_parts.append(no_text_generation_negative())
    return ", ".join(pos_parts), ", ".join(neg_parts)


def _sticker_acting_layers(
    cut: CutSpec,
    *,
    expression: ExpressionOverride,
    tuning_emotion: float,
) -> str:
    acting = dramatic_acting_priority_block(expression.intensity)
    boost = sticker_acting_positive_boost()
    emotion_boost = _sticker_emotion_boost(cut)
    return (
        f"{acting}, {expression.positive_block}, {boost}, {emotion_boost}, "
        f"bold expression, exaggerated body language, emotion strength {tuning_emotion:.2f}, "
    )


def _source_positive(source: SourceMode, entity: EntityProfile) -> str:
    if source == "character":
        return f"{character_mode_positive_core()}, "
    if source == "illustration":
        return (
            "preserve existing illustration style, same character design, "
            "same color palette and outfit, expression and pose change only, "
        )
    if entity.is_human:
        return f"{human_comfyui_positive()}, same person identity, "
    if entity.is_pet:
        return "same pet identity, preserve markings and ear shape, cute sticker character, "
    return "same character identity, recognizable subject, "


def _build_character_mode_prompt(
    cut: CutSpec,
    *,
    settings: PromptPipelineSettings,
    output_mode: OutputMode,
    pose_plan: CutPosePlan | None,
    expression: ExpressionOverride,
    no_ai_text: bool = True,
) -> ComfyUIPromptResult:
    tuning = settings.tuning_for("comfyui")
    style_preset = load_comfyui_style_preset(source_mode="character")
    core_pos, core_neg = sticker_prompt_cores(style_preset)

    acting_block = character_mode_acting_block(expression)
    pose_kw = pose_plan.comfyui_keywords(output_mode=output_mode) if pose_plan else (
        f"{cut.body_pose}, {cut.action}"
    )
    cut_kw = (
        f"cut {cut.id}, emotion {cut.emotion}, {_expression_face_kw(cut, expression)}, "
        f"{pose_kw}, layout {cut.layout_type}"
    )
    if cut.prop.lower() not in ("none", ""):
        cut_kw += f", prop {cut.prop}"

    dir_pos, dir_neg = _sticker_directing_layers(
        pose_plan, output_mode=output_mode, no_ai_text=no_ai_text
    )
    identity = character_mode_identity_block(tuning, pose_plan)
    positive = f"{core_pos}, {dir_pos}, {acting_block}, {identity}{cut_kw}"
    negative = _apply_sticker_negatives(
        f"{core_neg}, {character_mode_negative_core()}, {dir_neg}"
    )
    if pose_plan:
        negative = _apply_sticker_negatives(
            f"{negative}, {pose_plan.negative_extras(output_mode=output_mode)}"
        )
        if pose_plan.hand_spec:
            positive = f"{positive}, {pose_plan.hand_spec.comfyui_positive}"
    return ComfyUIPromptResult(
        positive=positive.strip(),
        negative=negative.strip(),
        eye_style=expression.eye_style,
        mouth_style=expression.mouth_style,
        expression_intensity=expression.intensity,
    )


def build_comfyui_prompt(
    cut: CutSpec,
    *,
    entity: EntityProfile,
    profile: CharacterProfile,
    settings: PromptPipelineSettings,
    output_mode: OutputMode,
    source_mode: SourceMode,
    pose_plan: CutPosePlan | None = None,
    expression_override: ExpressionOverride | None = None,
    no_ai_text: bool = True,
) -> ComfyUIPromptResult:
    if _is_character_source(source_mode) and output_mode == "sticker":
        expr = _resolve_expression(cut, pose_plan, expression_override)
        return _build_character_mode_prompt(
            cut,
            settings=settings,
            output_mode=output_mode,
            pose_plan=pose_plan,
            expression=expr,
            no_ai_text=no_ai_text,
        )

    tuning = settings.tuning_for("comfyui")

    if output_mode == "illustration":
        core_pos = _ILLUSTRATION_POSITIVE_CORE
        core_neg = _ILLUSTRATION_NEGATIVE_CORE
        deform = "expressive staging, soft scene composition, "
        expr = None
    else:
        style_preset = load_comfyui_style_preset(source_mode=source_mode)
        core_pos, core_neg = sticker_prompt_cores(style_preset)
        expr = _resolve_expression(cut, pose_plan, expression_override)
        deform = _sticker_acting_layers(
            cut, expression=expr, tuning_emotion=tuning.emotion_strength
        )

    pose_kw = pose_plan.comfyui_keywords(output_mode=output_mode) if pose_plan else (
        f"{cut.body_pose}, {cut.action}"
    )
    cut_kw = (
        f"cut {cut.id}, emotion {cut.emotion}, {_expression_face_kw(cut, expr)}, "
        f"{pose_kw}, layout {cut.layout_type}"
    )
    if cut.prop.lower() not in ("none", ""):
        cut_kw += f", prop {cut.prop}"

    if entity.is_human:
        identity = (
            f"identity lock {tuning.identity_lock:.2f}, pose variation {tuning.pose_variation:.2f}, "
            f"pose freedom {pose_plan.pose_freedom if pose_plan else 'medium'}, "
            f"hairstyle {profile.face_mask_color}, colors {profile.main_colors}, "
        )
    else:
        identity = (
            f"identity lock {tuning.identity_lock:.2f}, pose variation {tuning.pose_variation:.2f}, "
            f"pose freedom {pose_plan.pose_freedom if pose_plan else 'medium'}, "
            f"{profile.species}, {profile.main_colors}, "
        )

    dir_pos, dir_neg = _sticker_directing_layers(
        pose_plan, output_mode=output_mode, no_ai_text=no_ai_text
    )
    positive = (
        f"{core_pos}, {dir_pos}, {_source_positive(source_mode, entity)}"
        f"{deform}{identity}{cut_kw}"
    )
    negative = _apply_sticker_negatives(
        f"{core_neg}, {dir_neg}{_human_negative_extra(entity, source_mode=source_mode)}"
    )
    if pose_plan:
        negative = _apply_sticker_negatives(
            f"{negative}, {pose_plan.negative_extras(output_mode=output_mode)}"
        )
        if pose_plan.hand_spec:
            positive = f"{positive}, {pose_plan.hand_spec.comfyui_positive}"
    if entity.is_human and output_mode == "sticker":
        negative = _apply_sticker_negatives(
            f"{negative}, realistic portrait, duplicate face, anime portrait lighting"
        )

    return ComfyUIPromptResult(
        positive=positive.strip(),
        negative=negative.strip(),
        eye_style=expr.eye_style if expr else "",
        mouth_style=expr.mouth_style if expr else "",
        expression_intensity=expr.intensity if expr else "",
    )
