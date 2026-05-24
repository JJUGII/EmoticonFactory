"""Prompt pipeline: shared CutSpec → engine-specific builders."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from services.character_profile import CharacterProfile
from services.identity_profile_analyzer import IdentityProfile
from services.directing.composition_director import CompositionDirector
from services.directing.directing_diversity import DirectingDiversityTracker
from services.directing.framing_enforcer import FramingDiversityEnforcer
from services.directing.text_separation import log_text_render_plan
from services.pose.expression_override import (
    ExpressionDiversityTracker,
    ExpressionOverride,
    load_comfyui_expression_strength,
    log_expression_override,
    resolve_expression_override,
)
from services.prompts.common_cut_spec import CutSpec
from services.prompts.entity_profile import (
    EntityProfile,
    build_entity_profile,
    humanize_item_dict,
    log_entity_resolution,
    normalize_entity_type,
)
if TYPE_CHECKING:
    from services.pose.pose_director import CutPosePlan
from services.prompts.prompt_profiles import (
    PromptPipelineSettings,
    load_prompt_settings,
    log_prompt_config,
    resolve_output_mode,
    resolve_source_mode,
)

__all__ = [
    "BuiltCutPrompt",
    "CutPosePlan",
    "CutSpec",
    "EntityProfile",
    "ExpressionDiversityTracker",
    "ExpressionOverride",
    "build_cut_prompt",
    "build_entity_profile",
    "humanize_item_dict",
    "load_prompt_settings",
    "log_entity_resolution",
    "log_prompt_config",
    "log_prompt_for_cut",
    "normalize_entity_type",
    "resolve_output_mode",
    "resolve_source_mode",
]


@dataclass(frozen=True)
class BuiltCutPrompt:
    engine: str
    source_mode: str
    output_mode: str
    entity_type: str
    cut_id: str
    instruction: str
    positive: str
    negative: str
    pose_plan: CutPosePlan | None = None
    eye_style: str = ""
    mouth_style: str = ""
    expression_intensity: str = ""
    directing_framing: str = ""
    directing_camera: str = ""
    emotion_fx: str = ""
    staging_pattern_id: str = ""
    acting_intensity: str = ""
    identity_weight: float = 0.65
    sampler_denoise: float = 0.32

    @property
    def primary_text(self) -> str:
        """OpenAI uses instruction; ComfyUI uses positive."""
        if self.engine == "comfyui":
            return self.positive
        return self.instruction


def build_cut_prompt(
    item: dict[str, Any],
    *,
    engine: str,
    entity: EntityProfile,
    profile: CharacterProfile,
    settings: PromptPipelineSettings,
    source_mode: str,
    output_mode: str,
    theme: str,
    series_name: str,
    reference_note: str,
    no_ai_text: bool = True,
    regeneration_suffix: str = "",
    expression_tracker: ExpressionDiversityTracker | None = None,
    composition_director: CompositionDirector | None = None,
    directing_tracker: DirectingDiversityTracker | None = None,
    framing_enforcer: FramingDiversityEnforcer | None = None,
) -> BuiltCutPrompt:
    row = humanize_item_dict(item, entity)
    cut = CutSpec.from_dict(row)
    src = source_mode  # type: ignore[assignment]
    out = output_mode  # type: ignore[assignment]
    eng = engine.strip().lower()

    from services.directing.acting_intensity import load_comfyui_acting_intensity
    from services.pose.pose_director import PoseDirector, log_pose_planning

    comp_dir = composition_director or CompositionDirector()
    dir_tracker = directing_tracker or DirectingDiversityTracker()
    frame_tracker = framing_enforcer or FramingDiversityEnforcer()
    acting_level = load_comfyui_acting_intensity()
    expr_intensity = load_comfyui_expression_strength()

    pose_plan = PoseDirector(composition_director=comp_dir).plan(
        cut,
        entity=entity,
        settings=settings,
        output_mode=out,
        engine=eng,
        directing_tracker=dir_tracker if out == "sticker" else None,
        framing_enforcer=frame_tracker if out == "sticker" else None,
        expression_intensity=expr_intensity,
    )
    log_pose_planning(pose_plan)
    log_text_render_plan(
        cut.id,
        text=cut.text,
        position=cut.text_position,
        enabled=no_ai_text and out == "sticker",
    )

    expression_override: ExpressionOverride | None = None
    if out == "sticker":
        tracker = expression_tracker or ExpressionDiversityTracker()
        expression_override = resolve_expression_override(
            cut,
            pose_plan.emotion_category,
            intensity=load_comfyui_expression_strength(),
            tracker=tracker,
        )
        log_expression_override(cut.id, expression_override)

    if eng == "comfyui":
        from services.prompts.comfyui_prompt_builder import build_comfyui_prompt

        cr = build_comfyui_prompt(
            cut,
            entity=entity,
            profile=profile,
            settings=settings,
            output_mode=out,
            source_mode=src,
            pose_plan=pose_plan,
            expression_override=expression_override,
            no_ai_text=no_ai_text,
        )
        return BuiltCutPrompt(
            engine=engine,
            source_mode=source_mode,
            output_mode=output_mode,
            entity_type=entity.entity_type,
            cut_id=cut.id,
            instruction="",
            positive=cr.positive,
            negative=cr.negative,
            pose_plan=pose_plan,
            eye_style=cr.eye_style,
            mouth_style=cr.mouth_style,
            expression_intensity=cr.expression_intensity,
            directing_framing=pose_plan.directing_framing if pose_plan else "",
            directing_camera=pose_plan.directing_camera if pose_plan else "",
            emotion_fx=pose_plan.emotion_fx if pose_plan else "",
            staging_pattern_id=pose_plan.staging_pattern_id if pose_plan else "",
            acting_intensity=acting_level,
            identity_weight=pose_plan.identity_weight if pose_plan else 0.65,
            sampler_denoise=pose_plan.sampler_denoise if pose_plan else 0.32,
        )

    from services.prompts.openai_prompt_builder import build_openai_prompt

    oa = build_openai_prompt(
        cut,
        entity=entity,
        profile=profile,
        settings=settings,
        theme=theme,
        series_name=series_name,
        reference_note=reference_note,
        output_mode=out,
        source_mode=src,
        no_ai_text=no_ai_text,
        regeneration_suffix=regeneration_suffix,
        pose_plan=pose_plan,
    )
    return BuiltCutPrompt(
        engine=engine,
        source_mode=source_mode,
        output_mode=output_mode,
        entity_type=entity.entity_type,
        cut_id=cut.id,
        instruction=oa.instruction,
        positive=oa.instruction,
        negative="",
        pose_plan=pose_plan,
        eye_style=expression_override.eye_style if expression_override else "",
        mouth_style=expression_override.mouth_style if expression_override else "",
        expression_intensity=expression_override.intensity if expression_override else "",
        directing_framing=pose_plan.directing_framing if pose_plan else "",
        directing_camera=pose_plan.directing_camera if pose_plan else "",
        emotion_fx=pose_plan.emotion_fx if pose_plan else "",
        staging_pattern_id=pose_plan.staging_pattern_id if pose_plan else "",
        acting_intensity=acting_level,
        identity_weight=pose_plan.identity_weight if pose_plan else 0.65,
        sampler_denoise=pose_plan.sampler_denoise if pose_plan else 0.32,
    )


def log_prompt_for_cut(built: BuiltCutPrompt) -> None:
    head = (
        f"[PROMPT] engine={built.engine} mode={built.output_mode} "
        f"source={built.source_mode} entity={built.entity_type} cut={built.cut_id}"
    )
    print(head, file=sys.stderr)
    if built.engine == "comfyui" and built.source_mode == "character":
        from services.comfyui_identity_adapter import log_identity_strategy

        log_identity_strategy(
            source_mode=built.source_mode,
            weight_override=built.identity_weight,
            cut_id=built.cut_id,
        )
    if built.eye_style:
        print(
            f"[PROMPT] eye_style={built.eye_style} mouth_style={built.mouth_style} "
            f"expression_intensity={built.expression_intensity}",
            file=sys.stderr,
        )
    if built.engine == "comfyui":
        print(f"[PROMPT] positive={built.positive[:800]}", file=sys.stderr)
        print(f"[PROMPT] negative={built.negative[:400]}", file=sys.stderr)
    else:
        print(f"[PROMPT] instruction={built.instruction[:800]}", file=sys.stderr)
