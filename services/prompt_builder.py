"""Backward-compatible PromptBuilder facade → services.prompts pipeline."""

from __future__ import annotations

from typing import Any, Sequence

from services.character_profile import CharacterProfile
from services.identity_profile_analyzer import IdentityProfile
from services.directing.composition_director import CompositionDirector
from services.directing.directing_diversity import DirectingDiversityTracker
from services.directing.framing_enforcer import FramingDiversityEnforcer
from services.pose.expression_override import ExpressionDiversityTracker
from services.prompts import (
    BuiltCutPrompt,
    build_cut_prompt,
    build_entity_profile,
    load_prompt_settings,
    resolve_output_mode,
    resolve_source_mode,
)
from services.prompts.entity_profile import humanize_item_dict


class PromptBuilder:
    """Delegates to engine-specific builders (OpenAI / ComfyUI)."""

    def __init__(self, *, engine: str = "openai") -> None:
        self._engine = (engine or "openai").strip().lower()
        self._settings = load_prompt_settings()
        self._expression_tracker = ExpressionDiversityTracker()
        self._composition_director = CompositionDirector()
        self._directing_tracker = DirectingDiversityTracker()
        self._framing_enforcer = FramingDiversityEnforcer()

    def build_prompt(
        self,
        item: dict[str, Any],
        theme: str,
        series_name: str,
        profile: CharacterProfile,
        reference_description: str = "",
        regeneration_suffixes: Sequence[str] | None = None,
        *,
        no_ai_text: bool = True,
        reference_type: str | None = None,
        canonical_identity_mode: bool = False,
        canonical_sheet_mode: bool = False,
        character_art_direct_canonical: bool = False,
        series_pack_coherence: bool = True,
        style_intensity: float = 0.5,
        identity_profile: IdentityProfile | None = None,
        pose_variation_strength: float = 1.0,
        expression_strength: float = 1.0,
        force_identity_lock: bool = False,
        source_mode: str | None = None,
        output_mode: str | None = None,
        engine: str | None = None,
    ) -> str:
        _ = (
            canonical_identity_mode,
            canonical_sheet_mode,
            character_art_direct_canonical,
            series_pack_coherence,
            style_intensity,
            force_identity_lock,
            pose_variation_strength,
            expression_strength,
        )
        eng = (engine or self._engine).strip().lower()
        src = resolve_source_mode(reference_type, source_mode, settings=self._settings)
        out = resolve_output_mode(output_mode, settings=self._settings, engine=eng)
        tuning = self._settings.tuning_for(eng)
        ident = identity_profile or IdentityProfile()
        entity = build_entity_profile(
            ident,
            reference_type=reference_type,
            source_mode=src,
            emotion_strength=tuning.emotion_strength,
            pose_variation=tuning.pose_variation,
            identity_lock=tuning.identity_lock,
        )
        row = humanize_item_dict(item, entity)
        suffix = ""
        if regeneration_suffixes:
            suffix = "; ".join(s.strip() for s in regeneration_suffixes if str(s).strip())
        built = build_cut_prompt(
            row,
            engine=eng,
            entity=entity,
            profile=profile,
            settings=self._settings,
            source_mode=src,
            output_mode=out,
            theme=theme,
            series_name=series_name,
            reference_note=reference_description,
            no_ai_text=no_ai_text,
            regeneration_suffix=suffix,
            expression_tracker=self._expression_tracker,
            composition_director=self._composition_director,
            directing_tracker=self._directing_tracker,
            framing_enforcer=self._framing_enforcer,
        )
        return built.primary_text

    def build_cut(
        self,
        item: dict[str, Any],
        *,
        engine: str,
        theme: str,
        series_name: str,
        profile: CharacterProfile,
        identity_profile: IdentityProfile,
        reference_description: str = "",
        reference_type: str | None = None,
        source_mode: str | None = None,
        output_mode: str | None = None,
        no_ai_text: bool = True,
        regeneration_suffix: str = "",
        pose_plan=None,
    ) -> BuiltCutPrompt:
        eng = engine.strip().lower()
        src = resolve_source_mode(reference_type, source_mode, settings=self._settings)
        out = resolve_output_mode(output_mode, settings=self._settings, engine=eng)
        tuning = self._settings.tuning_for(eng)
        entity = build_entity_profile(
            identity_profile,
            reference_type=reference_type,
            source_mode=src,
            emotion_strength=tuning.emotion_strength,
            pose_variation=tuning.pose_variation,
            identity_lock=tuning.identity_lock,
        )
        return build_cut_prompt(
            item,
            engine=eng,
            entity=entity,
            profile=profile,
            settings=self._settings,
            source_mode=src,
            output_mode=out,
            theme=theme,
            series_name=series_name,
            reference_note=reference_description,
            no_ai_text=no_ai_text,
            regeneration_suffix=regeneration_suffix,
            expression_tracker=self._expression_tracker,
            composition_director=self._composition_director,
            directing_tracker=self._directing_tracker,
            framing_enforcer=self._framing_enforcer,
        )
