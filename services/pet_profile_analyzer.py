"""Local heuristic pet profile from a single reference photo (v1).

Replace ``PetProfileAnalyzer.analyze`` with a Vision API-backed implementation later
without changing ``PetProfile`` field names.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from PIL import Image

from services.image_io import ImageReadError, pil_open_image

SpeciesHint = Literal["cat", "dog", "rabbit", "hamster", "bird", "human", "unknown"]

# Recorded into ``package_info.json`` as ``pet_profile_source`` (stable id for tooling).
PET_PROFILE_SOURCE = "PetProfileAnalyzer.local_heuristic_v1"


class PetProfile(BaseModel):
    """Structured description of one pet for prompts and ``package_info``."""

    species: str = "unknown"
    breed_style: str = "beloved companion pet (breed not asserted)"
    main_colors: list[str] = Field(default_factory=list)
    face_pattern: str = "preserve natural face markings from the photo"
    eye_color: str = "match eye color and impression from the photo"
    ear_shape: str = "match ear shape and carriage from the photo"
    body_shape: str = "match body silhouette and proportions from the photo"
    tail_style: str = "match tail length and shape if visible"
    expression_baseline: str = "calm, neutral, sticker-friendly"
    personality_keywords: list[str] = Field(default_factory=list)
    character_keywords: list[str] = Field(
        default_factory=lambda: [
            "a single beloved pet based on the provided real photo",
            "keep the same fur color distribution, face markings, ears, eyes, body silhouette",
            "do not change into a different animal",
        ]
    )
    negative_keywords: list[str] = Field(
        default_factory=lambda: [
            "different species or breed than the photo",
            "extra animals or humans",
            "photorealistic fur noise",
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
    source_image: str = ""


class PetProfileAnalyzer:
    """v1: color sampling + optional species/personality hints."""

    _ALLOWED = frozenset({"cat", "dog", "rabbit", "hamster", "bird", "human", "unknown"})

    def analyze(
        self,
        reference_path: Path,
        *,
        species_hint: str | None = None,
        personality_hint: str | None = None,
    ) -> PetProfile:
        path = Path(reference_path)
        rel = str(path.as_posix()) if path.is_file() else ""

        species = "unknown"
        if species_hint:
            s = str(species_hint).strip().lower()
            if s in self._ALLOWED:
                species = s

        main_colors = _dominant_colors(path, max_colors=5)

        pers_kw: list[str] = []
        if personality_hint and str(personality_hint).strip():
            pers_kw = [str(personality_hint).strip()]

        expr = "calm, neutral, sticker-friendly"
        if pers_kw:
            expr = f"{expr}; personality hint: {pers_kw[0]}"

        # ── 사람 전용 프로파일 ─────────────────────────────────────────
        if species == "human":
            return PetProfile(
                species="human",
                breed_style="person from the reference photo (human character, not an animal)",
                main_colors=main_colors or ["natural skin and hair tones from the reference"],
                face_pattern="preserve face shape, features, and hairstyle from the photo",
                eye_color="match eye shape and impression from the photo",
                ear_shape="match overall head and facial structure from the photo",
                body_shape="match the person's body shape and clothing style from the photo",
                tail_style="not applicable (human character)",
                expression_baseline=expr,
                personality_keywords=pers_kw,
                character_keywords=[
                    "a single person based on the provided reference photo",
                    "keep the same hair color, hairstyle, face shape, and overall appearance",
                    "do not change into a different person, animal, or fictional creature",
                ],
                negative_keywords=[
                    "different person or animal",
                    "extra people or animals in the frame",
                    "dramatically different hair color or hairstyle",
                    "photorealistic texture",
                    "busy background",
                    "watermark or logo",
                ],
                consistency_rules=[
                    "same human identity across all cuts",
                    "same hair color and style",
                    "same face proportions",
                    "same clothing vibe",
                    "same eye style",
                    "no species change — must remain human",
                    "no extra people",
                    "one person only",
                    "no realistic photo texture in final sticker",
                ],
                source_image=rel,
            )

        # ── 반려동물 프로파일 (기존) ──────────────────────────────────
        breed_style = (
            f"companion {species} (photo-based; do not invent a rare breed name)"
            if species != "unknown"
            else "single companion pet from the reference photo (species not asserted)"
        )

        return PetProfile(
            species=species,
            breed_style=breed_style,
            main_colors=main_colors or ["soft natural tones from the reference"],
            face_pattern="preserve natural face markings and fur pattern from the photo",
            eye_color="match eye color and gaze impression from the photo",
            ear_shape="match ear shape and size from the photo",
            body_shape="match torso and limb silhouette from the photo",
            tail_style="match tail if visible; otherwise omit or keep subtle",
            expression_baseline=expr,
            personality_keywords=pers_kw,
            source_image=rel,
        )


def _dominant_colors(path: Path, *, max_colors: int = 5) -> list[str]:
    """Downsample + coarse RGB buckets → readable color phrases."""
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
        label = _color_label(int(r), int(g), int(b))
        if label not in out:
            out.append(label)
        if len(out) >= max_colors:
            break
    return out


def _color_label(r: int, g: int, b: int) -> str:
    """Human-readable coarse color name."""
    if max(r, g, b) < 40:
        return "dark coat"
    if min(r, g, b) > 210:
        return "light/white fur patch"
    if r > g + 25 and r > b + 25:
        return "warm/reddish fur"
    if b > r + 20 and b > g + 20:
        return "cool/gray-blue fur"
    if abs(r - g) < 25 and abs(g - b) < 25:
        return "neutral gray-brown fur"
    if g > r + 15 and g > b + 15:
        return "warm beige/cream fur"
    return "mixed natural fur tone"
