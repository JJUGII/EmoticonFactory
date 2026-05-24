"""Automatic regeneration for cuts that failed consistency or static quality checks."""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from services.character_profile import CharacterProfile
from services.consistency_checker import CharacterConsistencyChecker
from services.identity_profile_analyzer import IdentityProfile
from services.prompts.human_descriptors import is_human_entity
from services.image_generator import BaseImageGenerator, OpenAIMissingKeyError
from services.image_processor import ImageProcessor
from services.prompt_builder import PromptBuilder


@dataclass(frozen=True)
class RegenerationContext:
    """Paths and metadata needed during regeneration batches."""

    png_dir: Path
    icon_dir: Path
    meta_dir: Path
    canonical_character_ref: Path
    theme: str
    series_name: str
    profile: CharacterProfile
    reference_note: str
    no_ai_text: bool = True
    text_pipeline: bool = False
    png_no_text_dir: Path | None = None
    final_sticker_dir: Path | None = None
    reference_type: str | None = None
    canonical_identity_mode: bool = False
    canonical_sheet_mode: bool = False
    character_art_direct_canonical: bool = False
    series_pack_coherence: bool = True
    style_intensity: float = 0.5
    pose_variation_strength: float = 1.0
    expression_strength: float = 1.0
    identity_profile: IdentityProfile | None = None
    source_mode: str = "auto"
    output_mode: str = ""
    emoticon_engine: str = "openai"


# Consistency heuristics (Korean substring match) → prompt suffix phrases
CODE_SUFFIX_CONSISTENCY: dict[str, str] = {
    "face_mask_missing": (
        "emphasize the same natural face markings and fur pattern as the canonical reference"
    ),
    "blue_eye_missing": (
        "make eyes clearly visible and consistent with the reference pet's eye style"
    ),
    "background_not_transparent": "transparent background only; no matte fill behind character",
    "too_realistic": (
        "simplify fur into flat vector shapes; no photorealistic texture "
        "(clean sticker shading only)"
    ),
    "bbox_too_small": "character should fill about 80% of the 540×540 canvas (full-body/readable)",
    "bbox_oversized": (
        "reduce character silhouette scale slightly to match standardized reference framing "
        "with comfortable margins"
    ),
    "bbox_off_center": "center the character in frame; balanced margins matching reference framing",
    "consistency_retry": (
        "re-align silhouette, proportions, palette, outline weight with the canonical "
        "reference before any embellishment"
    ),
    "drift_mismatch": (
        "match palette, silhouette density, and edge simplicity to the canonical reference sheet "
        "or character anchor — reduce drift vs reference"
    ),
    "texture_flattening_detected": (
        "restore watercolor texture, restore painterly softness, "
        "avoid flat vector rendering, preserve organic fur texture"
    ),
    "silhouette_ratio_mismatch": (
        "restore head-to-body width/height silhouette proportions to match the canonical reference"
    ),
    "eye_distance_drift": (
        "re-balance eye spacing and eye scale to match the canonical character eyes"
    ),
    "ear_angle_drift": (
        "restore ear tilt and upper-head left/right balance to match the canonical reference"
    ),
    "fur_palette_drift": (
        "re-harmonize fur and body palette families with the canonical reference (flat sticker colors)"
    ),
    "identity_drift_detected": (
        "restore exact same character identity as canonical reference; "
        "do not redesign face, eyes, species, or palette"
    ),
    "face_proportion_drift": (
        "restore face width-to-height proportions to match canonical reference"
    ),
    "eye_geometry_drift": (
        "restore eye spacing, eye scale, and eyelid shape to match canonical reference"
    ),
}

# Human photo subjects — no fur/paw/muzzle vocabulary in regen suffixes
HUMAN_CODE_SUFFIX_CONSISTENCY: dict[str, str] = {
    "face_mask_missing": (
        "emphasize the same hairstyle, face shape, and skin tone as the canonical human reference"
    ),
    "fur_palette_drift": (
        "re-harmonize hair, skin, and outfit palette with the canonical human reference (flat sticker colors)"
    ),
    "too_realistic": (
        "simplify skin and clothing into flat vector shapes; no photorealistic portrait texture"
    ),
    "texture_flattening_detected": (
        "restore soft illustrated skin and hair texture; avoid flat logo mascot rendering"
    ),
    "consistency_retry": (
        "re-align human silhouette, face proportions, hairstyle, and palette with the canonical reference"
    ),
    "drift_mismatch": (
        "match hairstyle, outfit impression, silhouette, and edge simplicity to the canonical human reference"
    ),
}
_PET_ONLY_CONSISTENCY_CODES = frozenset(
    {"face_mask_missing", "blue_eye_missing", "fur_palette_drift", "texture_flattening_detected"}
)

CODE_SUFFIX_QUALITY: dict[str, str] = {
    "bytes_budget": (
        "simplify shapes and colors for a lightweight PNG sticker: flat fills, fewer gradients "
        "(under size budget)"
    ),
    "wrong_dimensions": (
        "output must be scalable to exactly 540×540 RGB big emoticon with correct sticker margins"
    ),
    "not_rgba_png": "full RGBA with transparent backdrop; opaque rectangle backgrounds avoided",
}


def _dedupe_preserve(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


_AREA_RATIO_RE = re.compile(
    r"컷\s*area_ratio\D*([\d.]+).*참조\D*([\d.]+)",
    re.M,
)


def failure_codes_consistency(issues: list[Any]) -> list[str]:
    """Map consistency ``issues`` strings to stable failure codes."""
    codes: list[str] = []
    for raw in issues or []:
        issue = str(raw)
        low = issue
        if "드리프트 판정" in issue or "drift_similarity" in low:
            codes.append("drift_mismatch")

        if "임계값" in low and ("미만" in low or "threshold" in low.lower()):
            codes.append("consistency_retry")

        if "어두운(마스크)" in low or ("마스크" in low and "참조 대비 너무 낮음" in low):
            codes.append("face_mask_missing")
        if "파란 눈" in low:
            codes.append("blue_eye_missing")
        if "투명 배경 비율" in low or "참조보다 낮음" in low:
            codes.append("background_not_transparent")
        if ("실사" in low and "텍스처" in low) or ("고주파 텍스처" in low):
            codes.append("too_realistic")
        elif "에지 밀도" in low:
            codes.append("too_realistic")

        if "바운딩 박스 위치" in low or "Δcx=" in low or "Δcy=" in low:
            codes.append("bbox_off_center")

        if "상대 크기" in low and "참조" in low:
            m = _AREA_RATIO_RE.search(issue)
            if m:
                try:
                    ca = float(m.group(1))
                    ra = float(m.group(2))
                    if ra > 1e-6:
                        rel = ca / ra
                        if rel < 0.88:
                            codes.append("bbox_too_small")
                        elif rel > 1.14:
                            codes.append("bbox_oversized")
                        else:
                            codes.append("bbox_off_center")
                except ValueError:
                    codes.append("bbox_off_center")
            else:
                codes.append("bbox_too_small")

        if "실루엣 가로세로 비율" in low:
            codes.append("silhouette_ratio_mismatch")
        if "눈 주변 가로 분포" in low:
            codes.append("eye_distance_drift")
        if "귀·상부 좌우" in low or "귀/상부 좌우" in low:
            codes.append("ear_angle_drift")
        if "hue histogram" in low or "팔레트(색상 분포)" in low:
            codes.append("fur_palette_drift")
        if "texture_flattening_detected" in low:
            codes.append("texture_flattening_detected")
        if "identity_drift_detected" in low:
            codes.append("identity_drift_detected")
        if "눈 주변 가로 분포" in low or "eye-span" in low.lower():
            codes.append("eye_geometry_drift")
        if "실루엣 가로세로" in low or "silhouette" in low.lower():
            codes.append("face_proportion_drift")

        if "주요 영역 평균 색상" in low or "BGR L2" in low:
            codes.append("consistency_retry")

    out = _dedupe_preserve(codes)
    if not out:
        out = ["consistency_retry"]
    return out


def failure_codes_quality(issues: list[Any]) -> list[str]:
    """Map QualityChecker PNG/icon error strings to codes."""
    codes: list[str] = []
    for raw in issues or []:
        s = str(raw)
        if "용량 초과" in s or "bytes" in s.lower():
            codes.append("bytes_budget")
        if "해상도 불일치" in s:
            codes.append("wrong_dimensions")
        if "RGBA가 아님" in s or "RGBA 아님" in s:
            codes.append("not_rgba_png")
    out = _dedupe_preserve(codes)
    if not out:
        out = ["wrong_dimensions"]
    return out


def prompt_suffix_for_codes(
    codes: list[str],
    failure_source: str,
    *,
    identity: IdentityProfile | None = None,
) -> list[str]:
    tbl = CODE_SUFFIX_QUALITY if failure_source == "quality" else CODE_SUFFIX_CONSISTENCY
    human = identity is not None and is_human_entity(identity.entity_type)
    out = []
    for c in codes:
        if human and c in HUMAN_CODE_SUFFIX_CONSISTENCY:
            out.append(HUMAN_CODE_SUFFIX_CONSISTENCY[c])
            continue
        if human and c in _PET_ONLY_CONSISTENCY_CODES:
            continue
        if c in tbl:
            out.append(tbl[c])
    if not out and failure_source == "consistency":
        out = [CODE_SUFFIX_CONSISTENCY["consistency_retry"]]
    if not out and failure_source == "quality":
        out = [CODE_SUFFIX_QUALITY["wrong_dimensions"]]
    return out


def _expected_png_paths(png_dir: Path) -> list[Path]:
    return [png_dir / f"{i:02d}.png" for i in range(1, 17)]


class RegenerationManager:
    """Implements capped regeneration batches with prompt tweaks (Vision-ready split)."""

    def __init__(self, generator_kind: str = "mock") -> None:
        self.generator_kind = generator_kind

    def regenerate_failed_items(
        self,
        ctx: RegenerationContext,
        failed_items: list[dict[str, Any]],
        items_by_id: dict[str, dict[str, Any]],
        *,
        generator: BaseImageGenerator,
        prompt_builder: PromptBuilder,
        processor: ImageProcessor,
        checker: CharacterConsistencyChecker,
        max_attempts: int,
        failure_source: str = "consistency",
        prompts_records: list[dict[str, Any]] | None = None,
        package_rows: list[dict[str, Any]] | None = None,
        prompts_json_writer: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Run up to ``max_attempts`` batches; each batch redraws current failures.

        Saves attempt snapshots under ``meta/regeneration_attempts/<id>/`` before overwriting.
        After each batch, runs a **full** ``checker.check()`` on every cut.
        """

        batches: list[dict[str, Any]] = []

        skipped_reference = {"_reference"}

        cur_failed: list[dict[str, Any]] = [
            dict(x)
            for x in failed_items
            if str(x.get("id", "")) not in skipped_reference and str(x.get("id"))
        ]

        png_paths = _expected_png_paths(ctx.png_dir)

        caps = max(0, int(max_attempts))

        if not cur_failed:
            lr = checker.check(ctx.canonical_character_ref, png_paths, ctx.profile)
            return self._idle_result(ctx, lr, caps, failure_source)

        batches_used = 0
        last_report: dict[str, Any] | None = None

        for batch_idx in range(caps):
            if not cur_failed:
                break

            round_entry: dict[str, Any] = {
                "batch_index": batch_idx,
                "failure_source": failure_source,
                "cut_entries": [],
            }

            for fail in cur_failed:
                cut_id = str(fail.get("id", "")).strip()
                if not cut_id or cut_id in skipped_reference:
                    continue

                item = items_by_id.get(cut_id)
                if item is None:
                    round_entry["cut_entries"].append(
                        {"id": cut_id, "skip": True, "reason": "item not found in planner map"}
                    )
                    continue

                issues = fail.get("issues") or []
                codes = (
                    failure_codes_quality(issues)
                    if failure_source == "quality"
                    else failure_codes_consistency(issues)
                )
                suffixes = prompt_suffix_for_codes(
                    codes,
                    failure_source=failure_source,
                    identity=ctx.identity_profile,
                )
                reg_suffix = "; ".join(s.strip() for s in suffixes if str(s).strip())
                neg_prompt: str | None = None
                if ctx.identity_profile is not None:
                    built = prompt_builder.build_cut(
                        item,
                        engine=ctx.emoticon_engine,
                        theme=ctx.theme,
                        series_name=ctx.series_name,
                        profile=ctx.profile,
                        identity_profile=ctx.identity_profile,
                        reference_description=ctx.reference_note,
                        reference_type=ctx.reference_type,
                        source_mode=ctx.source_mode,
                        output_mode=ctx.output_mode,
                        no_ai_text=ctx.no_ai_text,
                        regeneration_suffix=reg_suffix,
                    )
                    prompt = built.primary_text
                    neg_prompt = built.negative or None
                else:
                    prompt = prompt_builder.build_prompt(
                        item,
                        theme=ctx.theme,
                        series_name=ctx.series_name,
                        profile=ctx.profile,
                        reference_description=ctx.reference_note,
                        regeneration_suffixes=suffixes,
                        no_ai_text=ctx.no_ai_text,
                        reference_type=ctx.reference_type,
                        canonical_identity_mode=ctx.canonical_identity_mode,
                        canonical_sheet_mode=ctx.canonical_sheet_mode,
                        character_art_direct_canonical=ctx.character_art_direct_canonical,
                        series_pack_coherence=ctx.series_pack_coherence,
                        style_intensity=ctx.style_intensity,
                        pose_variation_strength=ctx.pose_variation_strength,
                        expression_strength=ctx.expression_strength,
                        force_identity_lock=True,
                        engine=ctx.emoticon_engine,
                        source_mode=ctx.source_mode,
                        output_mode=ctx.output_mode,
                    )
                txt = str(item.get("text", ""))

                raw_png = ctx.png_dir / f"{cut_id}.png"

                attempts_root = ctx.meta_dir / "regeneration_attempts" / cut_id
                attempts_root.mkdir(parents=True, exist_ok=True)
                backup_name = attempts_root / f"batch{batch_idx}_before.png"
                try:
                    if raw_png.is_file():
                        shutil.copy2(raw_png, backup_name)
                except OSError:
                    pass

                reg_meta = attempts_root / f"batch{batch_idx}_prompt_meta.json"
                reg_meta.write_text(
                    json.dumps(
                        {"issue_codes": codes, "prompt_suffix_lines": suffixes},
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )

                detail: dict[str, Any] = {
                    "id": cut_id,
                    "issue_codes": codes,
                    "prompt_suffix_lines": suffixes,
                    "batch_index": batch_idx,
                }

                gen_t = time.perf_counter()
                try:
                    gen_kw: dict[str, object] = {
                        "reference_path": ctx.canonical_character_ref,
                        "item": {**item, "_no_ai_text": ctx.no_ai_text},
                    }
                    if neg_prompt:
                        gen_kw["negative_prompt"] = neg_prompt
                    generator.generate(
                        prompt,
                        raw_png,
                        text=txt,
                        item_id=cut_id,
                        **gen_kw,
                    )
                    if (
                        ctx.text_pipeline
                        and ctx.png_no_text_dir is not None
                        and ctx.final_sticker_dir is not None
                    ):
                        nt = ctx.png_no_text_dir / f"{cut_id}.png"
                        processor.normalize_emoticon_to(raw_png, nt)
                        tpos = str(item.get("text_position", "bottom"))
                        fin = ctx.final_sticker_dir / f"{cut_id}.png"
                        processor.add_text_overlay(nt, fin, txt, tpos)
                        processor.create_icon(fin, ctx.icon_dir / f"{cut_id}.png")
                    else:
                        processor.normalize_emoticon(raw_png)
                        processor.create_icon(raw_png, ctx.icon_dir / f"{cut_id}.png")

                    detail["wall_seconds"] = round(time.perf_counter() - gen_t, 4)
                    detail["attempt_logs"] = list(
                        getattr(generator, "last_attempt_logs", []) or []
                    )
                    detail["ok"] = True

                    if prompts_records is not None:
                        for prow in prompts_records:
                            if str(prow.get("id")) == cut_id:
                                prow["prompt"] = prompt
                                reg_hist = prow.get("prompt_regeneration_history")
                                if not isinstance(reg_hist, list):
                                    reg_hist = []
                                reg_hist.append(
                                    {
                                        "batch_index": batch_idx,
                                        "failure_source": failure_source,
                                        "issue_codes": codes,
                                        "suffixes": suffixes,
                                    }
                                )
                                prow["prompt_regeneration_history"] = reg_hist
                                break

                    if package_rows is not None:
                        for row in package_rows:
                            if str(row.get("id")) == cut_id:
                                row["prompt"] = prompt
                                rh = row.get("regeneration_history")
                                if not isinstance(rh, list):
                                    rh = []
                                rh.append(
                                    {
                                        "batch": batch_idx,
                                        "failure_source": failure_source,
                                        "codes": codes,
                                    }
                                )
                                row["regeneration_history"] = rh
                                break

                except OpenAIMissingKeyError:
                    raise
                except Exception as exc:
                    detail["wall_seconds"] = round(time.perf_counter() - gen_t, 4)
                    detail["error"] = repr(exc)
                    detail["ok"] = False

                round_entry["cut_entries"].append(detail)

            if prompts_json_writer:
                prompts_json_writer()

            last_report = checker.check(ctx.canonical_character_ref, png_paths, ctx.profile)
            round_entry["consistency_snapshot"] = {
                "ok": last_report.get("ok"),
                "failed_count": len(last_report.get("failed") or []),
            }

            batches.append(round_entry)
            batches_used += 1

            cur_failed = [
                dict(x)
                for x in (last_report.get("failed") or [])
                if str(x.get("id")) not in skipped_reference
            ]
            if bool(last_report.get("ok")) or not cur_failed:
                break

        assert last_report is not None

        return {
            "generator_kind": self.generator_kind,
            "failure_source": failure_source,
            "max_attempts": caps,
            "batches_used": batches_used,
            "batches": batches,
            "final_consistency_report": last_report,
            "mock_effect_note": (
                "mock generator 재생성은 프롬프트가 달라도 합성 로직상 결과가 크게 안 바뀔 수 있습니다. "
                "자동 교정은 주로 `--generator openai` 에서 활용합니다."
                if self.generator_kind == "mock"
                else None
            ),
        }

    def _idle_result(
        self,
        ctx: RegenerationContext,
        lr: dict[str, Any],
        caps: int,
        failure_source: str,
    ) -> dict[str, Any]:
        return {
            "generator_kind": self.generator_kind,
            "failure_source": failure_source,
            "max_attempts": caps,
            "batches_used": 0,
            "batches": [],
            "final_consistency_report": lr,
            "mock_effect_note": (
                "mock generator 재생성은 프롬프트가 달라도 합성 로직상 결과가 크게 안 바뀔 수 있습니다. "
                "자동 교정은 주로 `--generator openai` 에서 활용합니다."
                if self.generator_kind == "mock"
                else None
            ),
        }
