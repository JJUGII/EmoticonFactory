"""Structured character bible for prompts and ``package_info`` metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from services.identity_profile_analyzer import IdentityProfile
    from services.pet_profile_analyzer import PetProfile


class CharacterProfile(BaseModel):
    """Sticker character bible (generic pet-first; no fixed breed)."""

    species: str = "pet"
    breed_style: str = "beloved companion pet from the reference photo"
    main_colors: str = "match natural fur tones and markings from the reference photo"
    face_mask_color: str = "natural face markings from the reference (do not invent a mask)"
    eye_color: str = "match eye color and impression from the reference"
    ear_shape: str = "match ear shape from the reference"
    expression: str = "calm, cute, sticker-friendly"
    personality: str = "lovable companion pet"
    design_keywords: list[str] = Field(
        default_factory=lambda: [
            "KakaoTalk big emoticon sticker",
            "hand-drawn vector-like",
            "clean outline",
            "flat pastel colors",
            "simple readable silhouette",
        ]
    )
    negative_keywords: list[str] = Field(
        default_factory=lambda: [
            "different animal or breed than the reference",
            "extra animals or humans",
            "photorealistic fur",
            "busy background",
            "watermark or logo",
        ]
    )
    consistency_rules: list[str] = Field(
        default_factory=lambda: [
            "same animal identity",
            "same main fur/body colors",
            "same face markings",
            "same ear shape",
            "same eye style",
            "same body silhouette",
            "no breed/species change",
            "no extra animals",
            "one pet only",
            "no realistic photo texture in final sticker",
        ]
    )

    @classmethod
    def from_pet_profile(cls, pet: "PetProfile") -> "CharacterProfile":
        """Build a ``CharacterProfile`` from a ``PetProfile`` (photo-first, no Siamese defaults)."""
        colors = ", ".join(pet.main_colors) if pet.main_colors else pet.breed_style
        pers = (
            "; ".join(pet.personality_keywords)
            if pet.personality_keywords
            else pet.expression_baseline
        )
        char_kw = ", ".join(pet.character_keywords) if pet.character_keywords else ""
        neg = list(pet.negative_keywords) if pet.negative_keywords else []
        rules_final: list[str] = list(pet.consistency_rules) if pet.consistency_rules else [
            "same animal identity",
            "same main fur/body colors",
            "same face markings",
            "same ear shape",
            "same eye style",
            "same body silhouette",
            "no breed/species change",
            "no extra animals",
            "one pet only",
            "no realistic photo texture in final sticker",
        ]
        return cls(
            species=pet.species,
            breed_style=pet.breed_style,
            main_colors=colors,
            face_mask_color=pet.face_pattern,
            eye_color=pet.eye_color,
            ear_shape=pet.ear_shape,
            expression=pet.expression_baseline,
            personality=pers,
            design_keywords=[
                "single pet character based on the provided real pet photo",
                "cute KakaoTalk big emoticon sticker style",
                "clean hand-drawn vector-like illustration",
                "thick soft outline",
                "flat pastel colors",
            ]
            + ([char_kw] if char_kw else []),
            negative_keywords=neg
            or [
                "different species or breed than the photo",
                "extra animals or humans",
                "photorealistic fur noise",
            ],
            consistency_rules=rules_final,
        )

    @classmethod
    def from_identity_profile(cls, identity: "IdentityProfile") -> "CharacterProfile":
        """Build profile from v0.7 universal identity (not generic mascot defaults)."""
        colors = ", ".join(identity.primary_palette) if identity.primary_palette else "from reference"
        tl = identity.trait_locks
        rules = (
            list(tl.species_trait_lock)
            + list(tl.facial_landmark_lock)
            + list(tl.fur_pattern_lock)
            + list(tl.hairstyle_lock)
            + list(tl.eye_geometry_lock)
            + [
                "same exact subject identity",
                "pose and expression variation only after canonical lock",
                "no species change",
                "no generic mascot redesign",
            ]
        )
        neg = [
            "generic cute mascot unrelated to reference",
            "different species or person than reference",
            "random palette swap",
            "corporate flat logo character",
            "extra subjects not in reference",
            "Midjourney stock mascot look",
        ]
        if identity.entity_type == "human":
            neg.append("different hairstyle, glasses, or face than reference person")
        design = [
            "KakaoTalk big emoticon — identity-preserving characterization",
            "recognizable same individual as reference",
            "hand-painted storybook sticker feel when style allows",
        ] + identity.identity_keywords[:4]
        pers = identity.mood
        breed = (
            f"{identity.entity_type} subject — preserve unique traits "
            f"(species={identity.species})"
        )
        return cls(
            species=identity.species,
            breed_style=breed,
            main_colors=colors,
            face_mask_color=identity.hair_or_fur_pattern,
            eye_color=identity.eye_color,
            ear_shape="match ear/head shape from reference",
            expression=identity.mood,
            personality=pers,
            design_keywords=design,
            negative_keywords=neg,
            consistency_rules=rules,
        )
