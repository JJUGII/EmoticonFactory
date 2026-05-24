"""Natural-language prompts for OpenAI image generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from services.character_profile import CharacterProfile

if TYPE_CHECKING:
    from services.pose.pose_director import CutPosePlan
from services.prompts.common_cut_spec import CutSpec
from services.prompts.entity_profile import EntityProfile
from services.prompts.human_descriptors import human_comfyui_positive, strip_pet_descriptor_tokens
from services.prompts.prompt_profiles import OutputMode, PromptPipelineSettings, SourceMode

_STICKER_EMOTION_CUES = (
    "big smile",
    "crying eyes",
    "angry puffed cheeks",
    "shocked wide eyes",
    "heart eyes",
    "trembling mouth",
    "hands raised",
    "finger heart",
    "hugging arms",
    "body leaning forward",
    "bouncing pose",
    "head tilt",
    "dramatic blush",
    "comic symbols",
)


@dataclass(frozen=True)
class OpenAIPromptResult:
    instruction: str


def _sticker_emotion_boost(cut: CutSpec) -> str:
    blob = f"{cut.emotion} {cut.facial_expression} {cut.action}".lower()
    picks: list[str] = []
    for cue in _STICKER_EMOTION_CUES:
        key = cue.split()[0]
        if key in blob or cue in blob:
            picks.append(cue)
    if not picks:
        picks.append(_STICKER_EMOTION_CUES[int(cut.id) % len(_STICKER_EMOTION_CUES)])
    return picks[0]


def _source_block(source: SourceMode, entity: EntityProfile) -> str:
    if source == "character":
        from services.prompts.character_mode import character_mode_reference_note

        return (
            f"{character_mode_reference_note()} "
            "Same sticker character design; change expression and pose only. "
        )
    if source == "illustration":
        return (
            "preserve the existing illustration style; do not redesign the character; "
            "change only expression and pose; keep color palette and outfit consistent. "
        )
    if entity.is_human:
        return (
            "recognizable same person as a simplified cute character; "
            "preserve hairstyle, hair color, face shape, outfit impression; "
            "allow exaggerated expression and body deformation for emoticon readability. "
        )
    if entity.is_pet:
        return (
            "recognizable same pet as a simplified cute sticker character; "
            "preserve coat colors, face markings, ear shape; "
            "allow exaggerated expression for sticker readability. "
        )
    return (
        "recognizable same subject as reference; preserve key visual identity; "
        "allow expressive deformation for sticker readability. "
    )


def _output_block(output: OutputMode) -> str:
    if output == "illustration":
        return (
            "Create a soft illustrated character artwork based on the selected character. "
            "Preserve the identity and overall appearance, but make the scene visually charming "
            "and polished like a storybook illustration. Gentle lighting, cozy atmosphere, "
            "pastel tone, clean composition. "
        )
    return (
        "Create a practical Korean messenger emoticon based on the selected character. "
        "Keep the character recognizable, but exaggerate the emotion and pose clearly. "
        "Use a simple readable sticker style with minimal background, large facial expression, "
        "clear body gesture, and space for Korean text. "
    )


def _entity_body_hint(entity: EntityProfile) -> str:
    if entity.is_human:
        return (
            "Use human gestures only: hands, arms, face, hair, shoulders — "
            "no paws, fur, tail, or animal ears. "
        )
    if entity.is_pet:
        return "Pet gestures allowed: paws, ears, tail when appropriate. "
    return ""


def _identity_block(entity: EntityProfile, output: OutputMode, pose_plan: CutPosePlan | None) -> str:
    lock = entity.identity_lock_level
    freedom = pose_plan.pose_freedom if pose_plan else "medium"
    if output == "sticker":
        if lock >= 0.75 and freedom == "low":
            return (
                "Keep recognizable identity; allow expressive face; moderate body pose change only. "
            )
        if freedom == "high":
            return (
                "Keep recognizable identity but allow strong pose, framing, and composition changes; "
                "exaggerated body language for Kakao sticker readability. "
            )
        return (
            "Maintain recognizable identity with bold pose, framing, and expression variation "
            "for chat sticker readability. "
        )
    if lock >= 0.75 and freedom == "low":
        return "Preserve identity and illustration style strongly; moderate pose change only. "
    return (
        "Preserve identity and style; allow stronger staging, camera angle, and body language "
        "for illustration composition. "
    )


def build_openai_prompt(
    cut: CutSpec,
    *,
    entity: EntityProfile,
    profile: CharacterProfile,
    settings: PromptPipelineSettings,
    theme: str,
    series_name: str,
    reference_note: str,
    output_mode: OutputMode,
    source_mode: SourceMode,
    no_ai_text: bool = True,
    regeneration_suffix: str = "",
    pose_plan: CutPosePlan | None = None,
) -> OpenAIPromptResult:
    tuning = settings.tuning_for("openai")
    layout_block = pose_plan.openai_layout_block(output_mode=output_mode) if pose_plan else ""
    emotion_boost = ""
    if output_mode == "sticker":
        emotion_boost = (
            f"Facial emphasis: {_sticker_emotion_boost(cut)}. "
            f"Expression strength {tuning.emotion_strength:.2f}, "
            f"pose variation {tuning.pose_variation:.2f}. "
        )

    typo = (
        "Do not draw any letters, captions, logos, or watermark shapes; leave caption margin. "
        if no_ai_text
        else f"Render Korean text '{cut.text}' clearly if requested. "
    )

    prop = ""
    if cut.prop.lower() not in ("none", ""):
        prop = f"Prop: {cut.prop}. "

    parts = [
        _output_block(output_mode),
        _source_block(source_mode, entity),
        _entity_body_hint(entity),
        _identity_block(entity, output_mode, pose_plan),
        layout_block,
        emotion_boost,
        f"Series: {series_name}. Theme: {theme}. Cut {cut.id}. ",
        f"Emotion: {cut.emotion}. Facial expression (secondary to hands): {cut.facial_expression}. ",
        (
            f"PRIMARY hand action ({pose_plan.hand_action_id}): {pose_plan.hand_action}. "
            f"Full body language: {pose_plan.body_language}. "
            if pose_plan
            else f"Action: {cut.action}. "
        ),
        f"Staging reference from template: {cut.body_pose}. Action: {cut.action}. "
        f"Motion: {cut.motion_hint}. Layout hint: {cut.layout_type}. {prop}",
        (
            f"Character: {human_comfyui_positive()}. "
            f"Hairstyle: {profile.face_mask_color}. "
            f"Colors: {strip_pet_descriptor_tokens(profile.main_colors)}. "
            f"Eyes: {profile.eye_color}. Not an animal or furry mascot. "
            if entity.is_human
            else (
                f"Character: {profile.species} — {profile.breed_style}. "
                f"Colors: {profile.main_colors}. Eyes: {profile.eye_color}. "
            )
        ),
        f"Reference: {reference_note.strip() or 'canonical character image'}. ",
        typo,
        f"Production notes: {cut.risk_notes}. ",
    ]
    if regeneration_suffix.strip():
        parts.append(f"[Prompt fix] {regeneration_suffix.strip()} ")

    return OpenAIPromptResult(instruction="".join(parts))
