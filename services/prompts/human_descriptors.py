"""Human-only identity descriptors (separated from pet/fur palette heuristics)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image

from services.identity_profile_analyzer import EntityType, IdentityProfile, TraitLocks
from services.image_io import ImageReadError, pil_open_image

# Tokens that must never appear in human prompts / identity exports
_PET_DESCRIPTOR_TERMS: tuple[str, ...] = (
    "fur",
    "paw",
    "paws",
    "tail",
    "whisker",
    "whiskers",
    "muzzle",
    "coat",
    "markings",
    "feather",
    "snout",
    "furry",
    "animal color pattern",
    "fur patch",
    "fur tone",
    "gray-brown fur",
    "beige/cream fur",
)

_PET_TOKEN_RE = re.compile(
    r"\b(fur|paws?|tails?|whiskers?|muzzles?|snouts?|furry|feathers?|"
    r"coat\s+color|animal\s+ears?|pet\s+markings?)\b",
    re.IGNORECASE,
)

_HUMAN_ENTITY_TYPES = frozenset({"human", "baby", "couple", "family"})


def is_human_entity(entity: EntityType) -> bool:
    return entity in _HUMAN_ENTITY_TYPES


def _human_color_label(r: int, g: int, b: int) -> str:
    """Coarse RGB → human appearance phrases (never use pet/fur vocabulary)."""
    if max(r, g, b) < 45:
        return "dark hair or clothing shadow"
    if min(r, g, b) > 215:
        return "light hair highlight or pale clothing"
    if r > g + 22 and r > b + 18:
        return "warm skin tone or brown hair"
    if b > r + 18 and b > g + 12:
        return "cool-toned hair or outfit accent"
    if g > r + 18 and g > b + 12:
        return "neutral olive or khaki clothing tone"
    if abs(r - g) < 22 and abs(g - b) < 22:
        if r > 120:
            return "medium skin tone or taupe clothing"
        return "soft neutral hair or hoodie tone"
    return "mixed natural hair and outfit colors"


def extract_human_palette(path: Path, *, max_colors: int = 5) -> list[str]:
    if not path.is_file():
        return []
    try:
        im = pil_open_image(path).convert("RGB")
    except (OSError, ImageReadError):
        return []
    small = im.resize((40, 40), Image.Resampling.BOX)
    buckets: dict[tuple[int, int, int], int] = {}
    for (r, g, b) in small.getdata():
        br, bg, bb = (r // 36) * 36, (g // 36) * 36, (b // 36) * 36
        key = (br, bg, bb)
        buckets[key] = buckets.get(key, 0) + 1
    ranked = sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)
    out: list[str] = []
    for (r, g, b), _ in ranked[: max_colors * 2]:
        label = _human_color_label(int(r), int(g), int(b))
        if label not in out and not _contains_pet_tokens(label):
            out.append(label)
        if len(out) >= max_colors:
            break
    return out or ["hair and outfit colors from reference"]


def strip_pet_descriptor_tokens(text: str) -> str:
    if not text:
        return ""
    out = _PET_TOKEN_RE.sub("", text)
    out = re.sub(r"\s+", " ", out).strip(" ,;")
    return out


def sanitize_descriptor_list(items: list[str]) -> tuple[list[str], list[str]]:
    """Return (cleaned, removed_pet_phrases)."""
    cleaned: list[str] = []
    removed: list[str] = []
    for item in items:
        raw = str(item).strip()
        if not raw:
            continue
        if _contains_pet_tokens(raw):
            removed.append(raw)
            continue
        cleaned.append(raw)
    return cleaned, removed


def _contains_pet_tokens(text: str) -> bool:
    low = text.lower()
    return any(t in low for t in _PET_DESCRIPTOR_TERMS) or bool(_PET_TOKEN_RE.search(text))


def default_human_trait_locks() -> TraitLocks:
    return TraitLocks(
        species_trait_lock=[
            "same person identity",
            "same apparent age range",
            "do not turn into animal mascot",
        ],
        facial_landmark_lock=[
            "same face proportions",
            "same nose and mouth placement",
            "same cheek shape",
        ],
        hairstyle_lock=[
            "same hairstyle and bangs/fringe",
            "same hair volume and color family",
            "preserve glasses or accessories if present",
        ],
        fur_pattern_lock=[
            "skin tone and clothing colors from reference",
            "hoodie/jacket/shirt impression consistent",
        ],
        eye_geometry_lock=[
            "same eye spacing and eyelid shape",
            "same eye size relative to face",
        ],
    )


def human_identity_keywords() -> list[str]:
    return [
        "cute simplified human Kakao emoticon character",
        "recognizable same person as reference photo",
        "human facial proportions",
        "human hairstyle and outfit impression",
        "human hands and arm gestures",
        "pose and expression variation only",
        "not an animal or furry mascot",
    ]


def human_distinctive_features(
    palette: list[str],
    *,
    metrics: dict[str, float],
) -> list[str]:
    feats = [
        "hairstyle and hair color from reference",
        "face shape and eye shape from reference",
        "clothing impression (hoodie/jacket/shirt) from reference",
        "simplified human features for sticker readability",
    ]
    if palette:
        feats.append(f"palette: {', '.join(palette[:4])}")
    if metrics.get("skin_ratio", 0) > 0.28:
        feats.append("recognizable skin tone from reference")
    return feats


def refine_human_identity_profile(
    profile: IdentityProfile,
    reference_path: Path,
    *,
    metrics: dict[str, float],
    override_species: bool = True,
) -> tuple[IdentityProfile, list[str], list[str]]:
    """
    Replace pet-leaning palette/keywords with human-only descriptors.

    Returns ``(refined_profile, human_descriptors, removed_pet_descriptors)``.
    """
    path = Path(reference_path)
    raw_palette = list(profile.primary_palette)
    _, removed_from_raw = sanitize_descriptor_list(raw_palette)

    human_palette = extract_human_palette(path) if path.is_file() else []
    if not human_palette:
        human_palette = ["hair color and outfit tones from reference"]

    locks = default_human_trait_locks()
    hair_style = (
        "preserve hairstyle, hair color, bangs/fringe, and outfit colors from reference"
    )
    kw = human_identity_keywords()
    dist = human_distinctive_features(human_palette, metrics=metrics)

    human_descriptors = list(human_palette) + dist[:4]

    updates: dict[str, object] = {
        "primary_palette": human_palette,
        "hair_or_fur_pattern": hair_style,
        "identity_keywords": kw,
        "distinctive_features": dist,
        "trait_locks": locks,
        "silhouette": "preserve human body silhouette and proportions from reference",
    }
    if override_species and profile.entity_type == "human":
        updates["species"] = "human"
    refined = profile.model_copy(update=updates)
    return refined, human_descriptors, removed_from_raw


def human_character_profile_fields(identity: IdentityProfile) -> dict[str, object]:
    """Fields for ``CharacterProfile.from_identity_profile`` human branch."""
    palette = ", ".join(identity.primary_palette[:5]) if identity.primary_palette else (
        "hair, skin, and outfit tones from reference"
    )
    palette = strip_pet_descriptor_tokens(palette)
    return {
        "species": "human",
        "breed_style": "recognizable human character for Kakao messenger emoticon",
        "main_colors": palette,
        "face_mask_color": strip_pet_descriptor_tokens(identity.hair_or_fur_pattern),
        "eye_color": identity.eye_color,
        "ear_shape": "human face framing (no animal ears)",
        "expression": identity.mood,
        "personality": "friendly human sticker personality",
        "design_keywords": [
            "cute simplified human character",
            "human facial proportions",
            "human hairstyle",
            "human hands",
            "KakaoTalk human emoticon sticker",
            "readable human gesture",
            "flat pastel colors",
            "thick soft outline",
        ],
        "negative_keywords": [
            "animal ears",
            "fur texture",
            "muzzle",
            "tail",
            "paw",
            "paws",
            "whiskers",
            "furry mascot",
            "pet mascot",
            "dog",
            "cat",
            "generic animal mascot",
            "photorealistic portrait noise",
        ],
        "consistency_rules": [
            "same person identity",
            "same hairstyle and hair color",
            "same face shape and eye shape",
            "same outfit impression",
            "human hands only (no paws)",
            "no species change to animal",
            "no animal mascot redesign",
        ],
    }


def human_comfyui_positive() -> str:
    return (
        "cute simplified human character, flat 2d messenger sticker, human facial proportions, "
        "human hairstyle, human hands, simple eyes, simple mouth, minimal shading, "
        "same person identity, simplified human features, kakao talk human emoticon style, "
        "not anime illustration"
    )


def human_comfyui_negative_extra() -> str:
    return (
        "animal ears, fur texture, muzzle, tail, paw, paws, whiskers, furry mascot, "
        "pet mascot, dog, cat, rabbit, snout, coat pattern, animal color pattern, "
        "furry ears, kemono animal face"
    )


def log_entity_profile_summary(
    identity: IdentityProfile,
    *,
    human_descriptors: list[str] | None = None,
    removed_pet: list[str] | None = None,
) -> None:
    human_list = human_descriptors or []
    removed_list = removed_pet or []
    print(
        f"[ENTITY_PROFILE] entity_type={identity.entity_type} "
        f"human_descriptors={', '.join(human_list[:8])}",
        file=sys.stderr,
    )
    if removed_list:
        print(
            f"[ENTITY_PROFILE] removed pet descriptors={', '.join(removed_list[:8])}",
            file=sys.stderr,
        )
    else:
        print("[ENTITY_PROFILE] removed pet descriptors=(none)", file=sys.stderr)
