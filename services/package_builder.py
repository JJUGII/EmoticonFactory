"""Create output folders and ``package_info.json`` for a big-emoticon set."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from config import (
    EMOTICON_SIZE,
    ICON_SIZE,
    MAX_EMOTICON_BYTES,
    MAX_ICON_BYTES,
    MAX_SHARE_BYTES,
    OUTPUT_DIR,
    SHARE_SIZE,
)


class PackageItem(BaseModel):
    """One cut in the exported package."""

    id: str
    text: str
    emotion: str
    action: str
    motion_hint: str
    importance: str
    png: str
    icon: str
    prompt: str


class PackageSpec(BaseModel):
    """Size and byte budgets recorded into metadata."""

    emoticon_size: list[int]
    icon_size: list[int]
    share_size: list[int]
    max_emoticon_bytes: int
    max_icon_bytes: int
    max_share_bytes: int


class PackageInfo(BaseModel):
    """Top-level ``package_info.json`` schema.

    ``test_mode`` / ``generated_count`` / ``selected_cut_ids`` are set for partial runs
    (``--test-one`` or ``--test-ids``).
    """

    series_name: str
    theme: str
    type: str = "big_emoticon"
    created_at: str
    items: list[PackageItem]
    representative_item_id: str = "01"
    spec: PackageSpec
    animated_items: list[dict[str, Any]] | None = None
    reference_character: str | None = None
    character_base: str | None = None
    character_base_white: str | None = None
    standardized_character: str | None = None
    character_profile: dict[str, Any] | None = None
    pet_profile: dict[str, Any] | None = None
    test_mode: bool | None = None
    generated_count: int | None = None
    selected_cut_ids: list[str] | None = None
    no_ai_text: bool | None = None
    text_overlay_applied: bool | None = None
    stylizer_backend: str | None = None
    generator_backend: str | None = None
    canonical_reference_used: str | None = None
    canonical_reference_policy: str | None = None
    pet_profile_source: str | None = None
    reference_type: str | None = None
    reference_type_confidence: float | None = None
    reference_type_reasons: list[str] | None = None
    reference_classifier_metrics: dict[str, Any] | None = None
    canonical_character_used: bool | None = None
    canonical_character_path: str | None = None
    canonical_character_policy: str | None = None
    canonical_sheet_used: bool | None = None
    canonical_sheet_path: str | None = None
    canonical_sheet_policy: str | None = None
    character_sheet_generator_backend: str | None = None
    character_sheet_generation_mode: str | None = None
    character_sheet_reference_type: str | None = None
    character_sheet_model: str | None = None
    sheet_mock: bool | None = None
    character_art_direct_canonical: bool | None = None
    forced_character_sheet_on_character_art: bool | None = None
    policy: str | None = None
    style_intensity: float | None = None


class PackageBuilder:
    """Creates directory layout and writes ``package_info.json``."""

    def __init__(self, output_root: Path | None = None) -> None:
        self.output_root = Path(output_root) if output_root else Path(OUTPUT_DIR)

    def ensure_package_dirs(self, package_dir: Path) -> None:
        """Create png/icon/share/meta/character folders under ``package_dir``."""
        for name in (
            "png",
            "icon",
            "share",
            "meta",
            "character",
            "character_candidates",
            "generated_raw",
            "png_no_text",
        ):
            (package_dir / name).mkdir(parents=True, exist_ok=True)

    def write_package_info(
        self,
        package_dir: Path,
        *,
        series_name: str,
        theme: str,
        items: list[dict[str, Any]],
        representative_item_id: str = "01",
        reference_relative: str | None = None,
        character_base_relative: str | None = None,
        character_base_white_relative: str | None = None,
        standardized_character_relative: str | None = None,
        character_profile: dict[str, Any] | None = None,
        pet_profile: dict[str, Any] | None = None,
        animated_items: list[dict[str, Any]] | None = None,
        test_mode: bool = False,
        generated_count: int | None = None,
        selected_cut_ids: list[str] | None = None,
        no_ai_text: bool | None = None,
        text_overlay_applied: bool | None = None,
        stylizer_backend: str | None = None,
        generator_backend: str | None = None,
        canonical_reference_used: str | None = None,
        canonical_reference_policy: str | None = None,
        pet_profile_source: str | None = None,
        reference_type: str | None = None,
        reference_type_confidence: float | None = None,
        reference_type_reasons: list[str] | None = None,
        reference_classifier_metrics: dict[str, Any] | None = None,
        canonical_character_used: bool | None = None,
        canonical_character_path: str | None = None,
        canonical_character_policy: str | None = None,
        canonical_sheet_used: bool | None = None,
        canonical_sheet_path: str | None = None,
        canonical_sheet_policy: str | None = None,
        character_sheet_generator_backend: str | None = None,
        character_sheet_generation_mode: str | None = None,
        character_sheet_reference_type: str | None = None,
        character_sheet_model: str | None = None,
        sheet_mock: bool | None = None,
        character_art_direct_canonical: bool | None = None,
        forced_character_sheet_on_character_art: bool | None = None,
        policy: str | None = None,
        style_intensity: float | None = None,
    ) -> Path:
        """Serialize ``PackageInfo`` to ``meta/package_info.json``."""
        spec = PackageSpec(
            emoticon_size=list(EMOTICON_SIZE),
            icon_size=list(ICON_SIZE),
            share_size=list(SHARE_SIZE),
            max_emoticon_bytes=MAX_EMOTICON_BYTES,
            max_icon_bytes=MAX_ICON_BYTES,
            max_share_bytes=MAX_SHARE_BYTES,
        )
        models: list[PackageItem] = []
        for row in items:
            models.append(
                PackageItem(
                    id=str(row["id"]),
                    text=str(row["text"]),
                    emotion=str(row.get("emotion", "")),
                    action=str(row.get("action", "")),
                    motion_hint=str(row.get("motion_hint", "")),
                    importance=str(row.get("importance", "")),
                    png=str(row["png"]),
                    icon=str(row["icon"]),
                    prompt=str(row.get("prompt", "")),
                )
            )

        gc = int(generated_count) if generated_count is not None else len(models)
        info = PackageInfo(
            series_name=series_name,
            theme=theme,
            created_at=datetime.now(timezone.utc).isoformat(),
            items=models,
            representative_item_id=representative_item_id,
            spec=spec,
            animated_items=animated_items if animated_items else None,
            reference_character=reference_relative,
            character_base=character_base_relative,
            character_base_white=character_base_white_relative,
            standardized_character=standardized_character_relative,
            character_profile=character_profile,
            pet_profile=pet_profile,
            test_mode=True if test_mode else None,
            generated_count=gc if test_mode else None,
            selected_cut_ids=list(selected_cut_ids) if (test_mode and selected_cut_ids) else None,
            no_ai_text=no_ai_text,
            text_overlay_applied=text_overlay_applied,
            stylizer_backend=stylizer_backend,
            generator_backend=generator_backend,
            canonical_reference_used=canonical_reference_used,
            canonical_reference_policy=canonical_reference_policy,
            pet_profile_source=pet_profile_source,
            reference_type=reference_type,
            reference_type_confidence=reference_type_confidence,
            reference_type_reasons=reference_type_reasons,
            reference_classifier_metrics=reference_classifier_metrics,
            canonical_character_used=canonical_character_used,
            canonical_character_path=canonical_character_path,
            canonical_character_policy=canonical_character_policy,
            canonical_sheet_used=canonical_sheet_used,
            canonical_sheet_path=canonical_sheet_path,
            canonical_sheet_policy=canonical_sheet_policy,
            character_sheet_generator_backend=character_sheet_generator_backend,
            character_sheet_generation_mode=character_sheet_generation_mode,
            character_sheet_reference_type=character_sheet_reference_type,
            character_sheet_model=character_sheet_model,
            sheet_mock=sheet_mock,
            character_art_direct_canonical=character_art_direct_canonical,
            forced_character_sheet_on_character_art=forced_character_sheet_on_character_art,
            policy=policy,
            style_intensity=style_intensity,
        )

        meta_dir = package_dir / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        out = meta_dir / "package_info.json"
        payload = info.model_dump(exclude_none=True)
        if payload.get("animated_items") is None:
            payload.pop("animated_items", None)
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return out


def merge_package_info_sheet_fields(
    package_dir: Path,
    *,
    series_name: str,
    theme: str,
    pet_profile: dict[str, Any] | None,
    character_profile: dict[str, Any] | None,
    reference_type: str | None,
    sheet_log: dict[str, Any],
    pet_profile_source: str | None = None,
) -> Path:
    """Merge character-sheet metadata into ``meta/package_info.json`` (sheet-only or full run)."""
    from config import (
        EMOTICON_SIZE,
        ICON_SIZE,
        MAX_EMOTICON_BYTES,
        MAX_ICON_BYTES,
        MAX_SHARE_BYTES,
        SHARE_SIZE,
    )

    path = package_dir / "meta" / "package_info.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = {}
    doc.setdefault("series_name", series_name)
    doc.setdefault("theme", theme)
    doc.setdefault("type", "big_emoticon")
    doc.setdefault("representative_item_id", "01")
    if "items" not in doc:
        doc["items"] = []
    if "spec" not in doc:
        doc["spec"] = {
            "emoticon_size": list(EMOTICON_SIZE),
            "icon_size": list(ICON_SIZE),
            "share_size": list(SHARE_SIZE),
            "max_emoticon_bytes": MAX_EMOTICON_BYTES,
            "max_icon_bytes": MAX_ICON_BYTES,
            "max_share_bytes": MAX_SHARE_BYTES,
        }
    if pet_profile is not None:
        doc["pet_profile"] = pet_profile
    if character_profile is not None:
        doc["character_profile"] = character_profile
    if reference_type is not None:
        doc["reference_type"] = reference_type
    if pet_profile_source:
        doc["pet_profile_source"] = pet_profile_source
    backend = sheet_log.get("character_sheet_generator_backend") or sheet_log.get("backend")
    if backend is not None:
        doc["character_sheet_generator_backend"] = str(backend)
    mode = sheet_log.get("character_sheet_generation_mode") or sheet_log.get("sheet_generation_mode")
    if mode is not None:
        doc["character_sheet_generation_mode"] = str(mode)
    rtype = sheet_log.get("character_sheet_reference_type") or sheet_log.get("sheet_reference_type")
    if rtype is not None:
        doc["character_sheet_reference_type"] = str(rtype)
    model = sheet_log.get("character_sheet_model") or sheet_log.get("model")
    if model is not None:
        doc["character_sheet_model"] = str(model)
    if "sheet_mock" in sheet_log and sheet_log["sheet_mock"] is not None:
        doc["sheet_mock"] = bool(sheet_log["sheet_mock"])
    if sheet_log.get("forced_character_sheet_on_character_art"):
        doc["forced_character_sheet_on_character_art"] = True
        doc["character_art_direct_canonical"] = False
        doc.pop("policy", None)
    elif "character_art_direct_canonical" in sheet_log and sheet_log["character_art_direct_canonical"] is not None:
        doc["character_art_direct_canonical"] = bool(sheet_log["character_art_direct_canonical"])
    if isinstance(sheet_log.get("policy"), str) and str(sheet_log["policy"]).strip():
        doc["policy"] = str(sheet_log["policy"]).strip()
    out = str(sheet_log.get("output") or "")
    if out.endswith("canonical_sheet.png") and not sheet_log.get("skipped_sheet_generation"):
        doc.pop("character_art_direct_canonical", None)
        if not sheet_log.get("forced_character_sheet_on_character_art"):
            doc.pop("policy", None)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def merge_package_info_character_art_direct_canonical(
    package_dir: Path,
    *,
    series_name: str,
    theme: str,
    pet_profile: dict[str, Any] | None,
    character_profile: dict[str, Any] | None,
    reference_type: str | None,
    policy_ko: str,
    pet_profile_source: str | None = None,
) -> Path:
    """Merge metadata when ``--make-character-sheet`` skips AI sheet for finished character art."""
    from config import (
        EMOTICON_SIZE,
        ICON_SIZE,
        MAX_EMOTICON_BYTES,
        MAX_ICON_BYTES,
        MAX_SHARE_BYTES,
        SHARE_SIZE,
    )

    path = package_dir / "meta" / "package_info.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = {}
    doc.setdefault("series_name", series_name)
    doc.setdefault("theme", theme)
    doc.setdefault("type", "big_emoticon")
    doc.setdefault("representative_item_id", "01")
    if "items" not in doc:
        doc["items"] = []
    if "spec" not in doc:
        doc["spec"] = {
            "emoticon_size": list(EMOTICON_SIZE),
            "icon_size": list(ICON_SIZE),
            "share_size": list(SHARE_SIZE),
            "max_emoticon_bytes": MAX_EMOTICON_BYTES,
            "max_icon_bytes": MAX_ICON_BYTES,
            "max_share_bytes": MAX_SHARE_BYTES,
        }
    if pet_profile is not None:
        doc["pet_profile"] = pet_profile
    if character_profile is not None:
        doc["character_profile"] = character_profile
    if reference_type is not None:
        doc["reference_type"] = reference_type
    if pet_profile_source:
        doc["pet_profile_source"] = pet_profile_source
    doc["character_art_direct_canonical"] = True
    doc["canonical_character_used"] = True
    doc["canonical_character_path"] = "character/canonical_character.png"
    doc["canonical_sheet_used"] = False
    doc.pop("canonical_sheet_path", None)
    doc.pop("canonical_sheet_policy", None)
    doc["forced_character_sheet_on_character_art"] = False
    doc["policy"] = policy_ko
    doc["character_sheet_generation_mode"] = "character_art_direct_canonical"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def merge_generation_log_sheet_fields(meta_dir: Path, sheet_log: dict[str, Any]) -> Path:
    """Merge sheet run fields into ``meta/generation_log.json``."""
    meta_dir.mkdir(parents=True, exist_ok=True)
    path = meta_dir / "generation_log.json"
    doc: dict[str, Any] = {}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = {}
    doc["sheet_only_run"] = True
    for key in (
        "sheet_generation_mode",
        "sheet_reference_type",
        "used_image_reference",
        "text_only_fallback",
        "drift_risk_warning",
        "sheet_openai_mode",
        "character_art_direct_canonical",
        "skipped_sheet_generation",
        "policy",
        "forced_character_sheet_on_character_art",
        "canonical_sheet_used",
        "canonical_character_used",
    ):
        if key in sheet_log:
            doc[key] = sheet_log[key]
    if sheet_log.get("character_sheet_model"):
        doc["character_sheet_model"] = sheet_log["character_sheet_model"]
    elif sheet_log.get("model"):
        doc["character_sheet_model"] = sheet_log["model"]
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
