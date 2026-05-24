"""Entity resolution and human/pet vocabulary for prompt builders."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Literal

from services.identity_profile_analyzer import EntityType, IdentityProfile
from services.prompts.common_cut_spec import CutSpec
from services.prompts.prompt_profiles import SourceMode

EntityKind = Literal["human", "pet", "character", "unknown"]

_PET_ENTITY_TYPES = frozenset(
    {"dog", "cat", "rabbit", "hamster", "bird", "pet"}
)
_HUMAN_ENTITY_TYPES = frozenset({"human", "baby", "couple", "family"})

# Longer phrases first
_PET_TERM_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("두 앞발로", "두 손으로"),
    ("앞발로", "손으로"),
    ("앞발 넓게", "양손 넓게"),
    ("앞발 까딱", "손 까딱"),
    ("앞발", "손"),
    ("귀 접힘", "고개 숙임"),
    ("귀 살짝만", "머리 살짝만"),
    ("귀", "머리"),
    ("꼬리 끝", "어깨 끝"),
    ("꼬리가", "어깨가"),
    ("꼬리", "어깨 흔들림"),
    ("강아지 눈", "큰 눈"),
    ("털 무늬", "헤어/의상 인상"),
    ("비실사", "캐릭터화"),
    ("앞머리", "앞머리"),
)

_HUMAN_ALLOWED_PARTS = (
    "hand",
    "hands",
    "arm",
    "arms",
    "face",
    "hair",
    "shoulder",
    "body gesture",
    "finger heart",
    "head tilt",
)
_PET_ALLOWED_PARTS = ("paw", "paws", "ears", "tail", "fur", "muzzle")


@dataclass(frozen=True)
class EntityProfile:
    entity_type: EntityKind
    source_style: SourceMode
    identity_lock_level: float
    emotion_strength: float
    pose_variation: float
    allowed_body_parts: tuple[str, ...] = field(default_factory=tuple)
    forbidden_terms: tuple[str, ...] = field(default_factory=tuple)
    identity_species: str = "unknown"
    reference_entity: EntityType = "unknown"

    @property
    def is_human(self) -> bool:
        return self.entity_type == "human"

    @property
    def is_pet(self) -> bool:
        return self.entity_type == "pet"

    @property
    def is_character_source(self) -> bool:
        return self.source_style == "character"


def normalize_entity_type(
    identity: IdentityProfile,
    *,
    reference_type: str | None,
    species_hint: str | None = None,
) -> EntityType:
    """Fix misclassification: photo humans should not become baby/pet."""
    rt = str(reference_type or "").strip().lower()
    et = identity.entity_type
    conf = identity.entity_type_confidence
    sh = str(species_hint or "").strip().lower()

    if sh in _PET_ENTITY_TYPES and sh not in ("unknown", "person", "human"):
        return sh  # type: ignore[return-value]

    if rt == "character_art":
        return "character_art"

    if rt == "photo":
        if et in _PET_ENTITY_TYPES and conf < 0.7:
            return "human"
        if et == "baby" and conf < 0.8 and sh != "baby":
            return "human"
        if et in ("unknown", "pet") and conf < 0.55:
            return "human"
        if et in _HUMAN_ENTITY_TYPES:
            return et
        if et in _PET_ENTITY_TYPES:
            return et
        return "human"

    if et in _HUMAN_ENTITY_TYPES:
        return et
    if et in _PET_ENTITY_TYPES:
        return et
    if et == "character_art":
        return et
    return et


def _entity_kind(entity: EntityType) -> EntityKind:
    if entity in _HUMAN_ENTITY_TYPES:
        return "human"
    if entity in _PET_ENTITY_TYPES:
        return "pet"
    if entity == "character_art":
        return "character"
    return "unknown"


def build_entity_profile(
    identity: IdentityProfile,
    *,
    reference_type: str | None,
    source_mode: SourceMode,
    emotion_strength: float,
    pose_variation: float,
    identity_lock: float,
    species_hint: str | None = None,
) -> EntityProfile:
    if source_mode == "character":
        kind: EntityKind = "character"
        ref_et = identity.entity_type
    else:
        ref_et = normalize_entity_type(
            identity,
            reference_type=reference_type,
            species_hint=species_hint,
        )
        kind = _entity_kind(ref_et)
    if kind == "human":
        allowed = _HUMAN_ALLOWED_PARTS
        forbidden = ("paw", "paws", "fur", "tail", "muzzle", "whiskers", "animal ears")
    elif kind == "pet":
        allowed = _PET_ALLOWED_PARTS
        forbidden = ("extra human", "wrong species")
    elif kind == "character":
        allowed = ("pose", "expression", "outfit", "hair", "hands")
        forbidden = ("redesign", "new mascot", "species change")
    else:
        allowed = ("face", "pose", "gesture")
        forbidden = ("generic mascot",)

    return EntityProfile(
        entity_type=kind,
        source_style=source_mode,
        identity_lock_level=identity_lock,
        emotion_strength=emotion_strength,
        pose_variation=pose_variation,
        allowed_body_parts=allowed,
        forbidden_terms=forbidden,
        identity_species=identity.species,
        reference_entity=ref_et,
    )


def humanize_cut_spec(cut: CutSpec, entity: EntityProfile) -> CutSpec:
    if entity.is_character_source or not entity.is_human:
        return cut

    def _map(s: str) -> str:
        out = s
        for old, new in _PET_TERM_REPLACEMENTS:
            if old in out:
                out = out.replace(old, new)
        return out

    return CutSpec(
        id=cut.id,
        text=cut.text,
        emotion=cut.emotion,
        facial_expression=_map(cut.facial_expression),
        body_pose=_map(cut.body_pose),
        prop=cut.prop,
        action=_map(cut.action),
        motion_hint=_map(cut.motion_hint),
        layout_type=cut.layout_type,
        text_position=cut.text_position,
        importance=cut.importance,
        risk_notes=cut.risk_notes,
    )


def humanize_item_dict(item: dict[str, Any], entity: EntityProfile) -> dict[str, Any]:
    spec = humanize_cut_spec(CutSpec.from_dict(item), entity)
    out = dict(item)
    out.update(spec.to_dict())
    return out


def log_entity_resolution(
    entity: EntityProfile,
    *,
    source_mode: SourceMode,
    output_mode: str,
) -> None:
    for line in (
        f"[ENTITY] entity_type={entity.entity_type}",
        f"[ENTITY] source_mode={source_mode}",
        f"[ENTITY] output_mode={output_mode}",
        f"[ENTITY] reference_entity={entity.reference_entity}",
    ):
        print(line, file=sys.stderr)
