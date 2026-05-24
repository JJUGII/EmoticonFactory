"""Universal living-entity identity extraction (v0.7 heuristic).

Analyzes any biological or character-art input and produces a stable identity JSON
for prompts and consistency — without collapsing into a generic cute mascot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from PIL import Image

from services.image_io import ImageReadError, pil_open_image
from services.pet_profile_analyzer import _dominant_colors

IDENTITY_PROFILE_SOURCE = "IdentityProfileAnalyzer.local_heuristic_v0.7"

EntityType = Literal[
    "human",
    "baby",
    "dog",
    "cat",
    "rabbit",
    "hamster",
    "bird",
    "couple",
    "family",
    "character_art",
    "pet",
    "unknown",
]

_SPECIES_HINT_MAP: dict[str, EntityType] = {
    "cat": "cat",
    "dog": "dog",
    "rabbit": "rabbit",
    "hamster": "hamster",
    "bird": "bird",
    "human": "human",
    "baby": "baby",
    "person": "human",
    "couple": "couple",
    "family": "family",
}


class TraitLocks(BaseModel):
    """Universal trait locks (replaces breed-only locks)."""

    species_trait_lock: list[str] = Field(default_factory=list)
    facial_landmark_lock: list[str] = Field(default_factory=list)
    fur_pattern_lock: list[str] = Field(default_factory=list)
    hairstyle_lock: list[str] = Field(default_factory=list)
    eye_geometry_lock: list[str] = Field(default_factory=list)


class IdentityProfile(BaseModel):
    """Canonical identity bible for one living subject or finished character art."""

    entity_type: EntityType = "unknown"
    species: str = "unknown"
    face_shape: str = "preserve face shape from reference"
    eye_shape: str = "preserve eye shape from reference"
    eye_color: str = "match eye color from reference"
    primary_palette: list[str] = Field(default_factory=list)
    distinctive_features: list[str] = Field(default_factory=list)
    mood: str = "warm, recognizable, sticker-friendly"
    silhouette: str = "preserve body silhouette from reference"
    hair_or_fur_pattern: str = "preserve hair or fur pattern from reference"
    identity_keywords: list[str] = Field(default_factory=list)
    trait_locks: TraitLocks = Field(default_factory=TraitLocks)
    entity_type_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    entity_type_reasons: list[str] = Field(default_factory=list)
    reference_type_hint: str | None = None
    source_image: str = ""


def _image_metrics(path: Path) -> dict[str, float]:
    try:
        im = pil_open_image(path).convert("RGBA")
    except (ImageReadError, OSError):
        return {}
    arr = np.array(im)
    h, w = arr.shape[:2]
    if h < 8 or w < 8:
        return {}
    alpha = arr[:, :, 3].astype(np.float32) / 255.0
    fg = alpha > 0.25
    if not np.any(fg):
        fg = np.ones((h, w), dtype=bool)
    ys, xs = np.where(fg)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    bh = max(y1 - y0 + 1, 1)
    bw = max(x1 - x0 + 1, 1)
    aspect = bw / float(bh)
    area_ratio = float(np.mean(fg))
    head = fg[y0 : y0 + max(1, bh // 3), x0 : x1 + 1]
    eye_band = fg[y0 + bh // 5 : y0 + bh // 2, x0 : x1 + 1]
    eye_density = float(np.mean(eye_band)) if eye_band.size else 0.0
    head_density = float(np.mean(head)) if head.size else 0.0
    rgb = arr[:, :, :3][fg].astype(np.float32)
    if rgb.size < 12:
        skin_ratio = 0.0
    else:
        r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
        skin_ratio = float(np.mean((r > 95) & (g > 70) & (b > 55) & (r > g) & (r > b)))
    return {
        "aspect": aspect,
        "area_ratio": area_ratio,
        "eye_density": eye_density,
        "head_density": head_density,
        "skin_ratio": skin_ratio,
        "height": float(h),
        "width": float(w),
    }


def _infer_entity_type(
    *,
    species_hint: str | None,
    reference_type: str | None,
    metrics: dict[str, float],
) -> tuple[EntityType, float, list[str]]:
    reasons: list[str] = []
    rt = str(reference_type or "").strip().lower()
    if rt == "character_art":
        return "character_art", 0.92, ["reference_type=character_art"]

    sh = str(species_hint or "").strip().lower()
    pet_hints = frozenset({"cat", "dog", "rabbit", "hamster", "bird"})
    if sh in _SPECIES_HINT_MAP:
        et = _SPECIES_HINT_MAP[sh]
        return et, 0.88, [f"species_hint={sh}"]

    skin = metrics.get("skin_ratio", 0.0)
    aspect = metrics.get("aspect", 1.0)
    eye_d = metrics.get("eye_density", 0.0)
    head_d = metrics.get("head_density", 0.0)

    if rt == "photo":
        if skin > 0.32 and sh not in pet_hints:
            if sh == "baby":
                reasons.append("photo + species_hint=baby")
                return "baby", 0.78, reasons
            reasons.append("reference_type=photo with human skin tones → human")
            return "human", 0.78, reasons
        if sh in pet_hints:
            reasons.append(f"photo + species_hint={sh}")
            return sh, 0.82, reasons  # type: ignore[return-value]

    if skin > 0.38 and aspect < 0.95 and sh == "baby":
        reasons.append("skin tone + baby hint → baby")
        return "baby", 0.72, reasons
    if skin > 0.38 and aspect < 0.95 and sh not in pet_hints:
        reasons.append("skin-tone dominant foreground → human")
        return "human", 0.68, reasons

    if aspect > 1.15 and eye_d < 0.35:
        reasons.append("wide aspect, moderate eye band → dog-like silhouette")
        return "dog", 0.55, reasons
    if aspect < 0.92 and head_d > 0.5:
        reasons.append("tall head proportion → cat-like silhouette")
        return "cat", 0.55, reasons
    if aspect > 1.35:
        reasons.append("very wide bbox → bird or small pet")
        return "bird", 0.45, reasons

    if rt == "photo":
        reasons.append("photo reference default → human (identity-preserving)")
        return "human", 0.52, reasons
    reasons.append("could not assert species; preserving reference identity only")
    return "unknown", 0.4, reasons


def _trait_locks_for_entity(entity: EntityType, metrics: dict[str, float]) -> TraitLocks:
    locks = TraitLocks()
    if entity == "human":
        locks.species_trait_lock = [
            "same person identity",
            "same apparent age range",
            "do not swap gender presentation unless reference is ambiguous",
        ]
        locks.facial_landmark_lock = [
            "same face proportions",
            "same nose and mouth placement",
            "same cheek shape",
        ]
        locks.hairstyle_lock = [
            "same hairstyle and bangs/fringe",
            "same hair volume and parting",
            "preserve glasses or accessories if present",
        ]
        locks.eye_geometry_lock = [
            "same eye spacing",
            "same eye size",
            "same eyelid shape",
        ]
        locks.fur_pattern_lock = [
            "skin tone from reference",
            "clothing colors and hoodie/jacket/shirt impression",
        ]
    elif entity == "baby":
        locks.species_trait_lock = ["same baby identity", "same age impression (infant/toddler)"]
        locks.facial_landmark_lock = [
            "same cheek fullness ratio",
            "same eye scale relative to face",
            "same nose and mouth scale",
        ]
        locks.eye_geometry_lock = ["large eye scale vs face — do not shrink to adult proportions"]
        locks.hairstyle_lock = ["same hair wisps or baby hair pattern"]
    elif entity == "dog":
        locks.species_trait_lock = ["same dog species impression", "same muzzle length family"]
        locks.facial_landmark_lock = ["same muzzle shape", "same nose spot if any"]
        locks.fur_pattern_lock = ["same coat colors and markings", "same ear flop or prick shape"]
        locks.eye_geometry_lock = ["same eye spacing and gaze direction baseline"]
    elif entity == "cat":
        locks.species_trait_lock = ["same cat species impression", "same face width"]
        locks.facial_landmark_lock = ["same whisker pad region", "same nose color"]
        locks.fur_pattern_lock = [
            "same fur mask or facial markings",
            "same tail length impression if visible",
        ]
        locks.eye_geometry_lock = ["same almond/round eye shape", "same eye spacing"]
    elif entity in ("rabbit", "hamster", "bird"):
        locks.species_trait_lock = [f"same {entity} identity — do not morph into cat/dog/human"]
        locks.fur_pattern_lock = ["same coat/feather colors and patterns"]
        locks.eye_geometry_lock = ["same eye scale for species"]
    elif entity in ("couple", "family"):
        locks.species_trait_lock = [
            "same number of people/characters",
            "same relative positions and scale between subjects",
            "do not merge or split subjects",
        ]
        locks.facial_landmark_lock = ["each face keeps its own landmarks"]
    elif entity == "character_art":
        locks.species_trait_lock = [
            "same illustrated character species/type",
            "do not redesign into a different mascot",
        ]
        locks.fur_pattern_lock = ["same line art and fill pattern as canonical"]
        locks.eye_geometry_lock = ["same illustrated eye style"]
    else:
        locks.species_trait_lock = [
            "same living subject as reference",
            "do not change species or subject count",
        ]
        locks.fur_pattern_lock = ["preserve markings, fur, hair, or outfit colors from reference"]
        locks.eye_geometry_lock = ["preserve eye shape and spacing from reference"]
    return locks


def _distinctive_features(
    entity: EntityType,
    colors: list[str],
    metrics: dict[str, float],
) -> list[str]:
    feats: list[str] = []
    if colors:
        feats.append(f"dominant palette: {', '.join(colors[:4])}")
    if entity == "human" and metrics.get("skin_ratio", 0) > 0.3:
        feats.append("recognizable skin tone range from reference")
    if entity == "cat" and metrics.get("aspect", 1) < 0.95:
        feats.append("compact head-heavy silhouette")
    if entity == "dog" and metrics.get("aspect", 1) > 1.0:
        feats.append("horizontal muzzle-forward silhouette")
    if entity == "character_art":
        feats.append("finished illustration style — preserve strokes and texture")
    if not feats:
        feats.append("preserve all recognizable traits from the reference image")
    return feats


class IdentityProfileAnalyzer:
    """Extract identity JSON from photo, art, or mixed family/couple inputs."""

    def analyze(
        self,
        reference_path: Path,
        *,
        species_hint: str | None = None,
        personality_hint: str | None = None,
        reference_type: str | None = None,
    ) -> IdentityProfile:
        path = Path(reference_path)
        rel = str(path.as_posix()) if path.is_file() else ""
        metrics = _image_metrics(path) if path.is_file() else {}
        entity, conf, reasons = _infer_entity_type(
            species_hint=species_hint,
            reference_type=reference_type,
            metrics=metrics,
        )
        if path.is_file():
            from services.prompts.human_descriptors import (
                extract_human_palette,
                is_human_entity,
            )

            colors = (
                extract_human_palette(path, max_colors=5)
                if is_human_entity(entity)
                else _dominant_colors(path, max_colors=5)
            )
        else:
            colors = []

        species = entity if entity not in ("character_art", "pet", "unknown", "couple", "family") else (
            str(species_hint or "unknown").strip().lower() or "unknown"
        )
        if entity == "character_art":
            species = "illustrated_character"

        mood = "calm, warm, sticker-friendly"
        if personality_hint and str(personality_hint).strip():
            mood = f"{mood}; personality: {personality_hint.strip()}"

        locks = _trait_locks_for_entity(entity, metrics)
        dist = _distinctive_features(entity, colors, metrics)

        kw = [
            "transform this exact living being into a Kakao emoticon",
            "preserve recognizable identity — not a new mascot",
            "same silhouette and face structure",
            "pose and expression variation only",
        ]
        if entity == "character_art":
            kw.append("preserve original illustration texture and line personality")

        face_shape = "triangle" if entity == "cat" else "oval"
        if entity == "human":
            face_shape = "preserve individual face shape from reference"
        elif entity == "baby":
            face_shape = "round, soft baby face proportions"

        eye_shape = "almond" if entity in ("cat", "human") else "round"
        if entity == "dog":
            eye_shape = "friendly round eyes matching reference"

        if entity == "character_art":
            hair_fur = "preserve illustrated hair, fur, or feather pattern exactly"
        elif entity in ("human", "baby", "couple", "family"):
            hair_fur = (
                "preserve hairstyle, hair color, bangs/fringe, and outfit colors from reference"
            )
        else:
            hair_fur = "preserve hair or fur pattern and face markings from reference"

        profile = IdentityProfile(
            entity_type=entity,
            species=species,
            face_shape=face_shape,
            eye_shape=eye_shape,
            eye_color="match eye color and gaze from reference",
            primary_palette=colors or ["natural tones from reference"],
            distinctive_features=dist,
            mood=mood,
            silhouette="preserve body silhouette and proportions from reference",
            hair_or_fur_pattern=hair_fur,
            identity_keywords=kw,
            trait_locks=locks,
            entity_type_confidence=conf,
            entity_type_reasons=reasons,
            reference_type_hint=reference_type,
            source_image=rel,
        )
        if entity in ("human", "baby", "couple", "family") and path.is_file():
            from services.prompts.human_descriptors import (
                is_human_entity,
                log_entity_profile_summary,
                refine_human_identity_profile,
            )

            profile, human_desc, removed = refine_human_identity_profile(
                profile,
                path,
                metrics=metrics,
                override_species=(entity == "human"),
            )
            log_entity_profile_summary(
                profile,
                human_descriptors=human_desc,
                removed_pet=removed,
            )
        return profile

    def to_pet_compatible_dict(self, profile: IdentityProfile) -> dict[str, Any]:
        """Bridge for legacy ``pet_profile`` fields in ``package_info``."""
        return {
            "species": profile.species,
            "breed_style": f"{profile.entity_type} subject (identity-locked; no generic mascot)",
            "main_colors": list(profile.primary_palette),
            "face_pattern": profile.hair_or_fur_pattern,
            "eye_color": profile.eye_color,
            "ear_shape": "match ear or head-top shape from reference",
            "body_shape": profile.silhouette,
            "expression_baseline": profile.mood,
            "personality_keywords": profile.identity_keywords[:3],
            "character_keywords": profile.identity_keywords,
            "consistency_rules": (
                profile.trait_locks.species_trait_lock
                + profile.trait_locks.facial_landmark_lock
                + profile.trait_locks.eye_geometry_lock
            ),
            "source_image": profile.source_image,
        }
