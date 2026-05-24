"""Body acting: emotion → concise preset keywords for ComfyUI."""

from __future__ import annotations

from dataclasses import dataclass

from services.directing.exaggerated_acting import resolve_concise_acting_preset


@dataclass(frozen=True)
class BodyActingSpec:
    gesture: str
    pattern_id: str
    pattern_hint: str
    positive_block: str


def resolve_body_acting(
    emotion_category: str,
    cut_index: int,
    *,
    cut_text: str = "",
    action: str = "",
    **_: object,
) -> BodyActingSpec:
    preset = resolve_concise_acting_preset(
        emotion_category,
        cut_index,
        cut_text,
        action,
    )
    return BodyActingSpec(
        gesture=preset.template_hint,
        pattern_id=preset.pattern_id,
        pattern_hint=preset.keywords.split(",")[0].strip(),
        positive_block=preset.keywords,
    )
