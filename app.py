"""CLI entry for Kakao-style big emoticon prototype generation."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from config import OUTPUT_DIR, PROJECT_ROOT
from services.character_profile import CharacterProfile
from services.pet_profile_analyzer import PET_PROFILE_SOURCE, PetProfileAnalyzer
from services.consistency_checker import CharacterConsistencyChecker, copy_failed_consistency
from services.concept_planner import ConceptPlanner
from services.image_generator import OpenAIMissingKeyError, create_image_generator
from services.image_processor import ImageProcessor
from services.package_builder import (
    PackageBuilder,
    merge_generation_log_sheet_fields,
    merge_package_info_character_art_direct_canonical,
    merge_package_info_sheet_fields,
)
from services.prompt_builder import PromptBuilder
from services.quality_checker import QualityChecker
from services.reference_classifier import ReferenceClassification, ReferenceClassifier
from services.reference_processor import ReferenceProcessor
from services.humanize_postprocessor import HumanizePostProcessor
from services.regeneration_manager import RegenerationContext, RegenerationManager
from services.style_standardizer import (
    create_stylizer,
    style_prompt_document,
)
from services.base_character_prompt import CANONICAL_BASE_POLICY_KO
from services.canonical_character_manager import (
    CanonicalCharacterManager,
    SELECTED_BASE_CANDIDATE_TYPE,
)
from services.illustration_style import clamp_style_intensity
from services.identity_lock import clamp_strength
from services.identity_profile_analyzer import (
    IDENTITY_PROFILE_SOURCE,
    IdentityProfileAnalyzer,
)
from services.candidate_feedback import write_candidate_feedback
from services.character_candidate_generator import create_character_candidate_generator
from services.character_sheet_generator import create_character_sheet_generator

def safe_folder_name(series_name: str) -> str:
    """Turn a display series name into a Windows-safe single folder segment."""
    s = series_name.strip().replace(" ", "_")
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    s = s.strip("._") or "package"
    return s[:200]


def _package_sheet_path(package_dir: Path) -> Path:
    return Path(package_dir) / "character" / "canonical_sheet.png"


CHARACTER_ART_DIRECT_POLICY_KO = (
    "이미 완성된 캐릭터 원본이므로 새 시트 생성 없이 canonical_character로 고정"
)


def _read_character_art_direct_meta(package_dir: Path) -> tuple[bool, bool, str | None]:
    """Detect finished-art direct-canonical mode and forced sheet-on-art flag."""
    cad = False
    forced = False
    pol: str | None = None
    src = package_dir / "character" / "canonical_character_source.json"
    if src.is_file():
        try:
            j = json.loads(src.read_text(encoding="utf-8"))
            if str(j.get("source_type") or "").strip() == "character_art_direct":
                cad = True
                p = j.get("policy")
                if isinstance(p, str) and p.strip():
                    pol = p.strip()
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    meta_pkg = package_dir / "meta" / "package_info.json"
    if meta_pkg.is_file():
        try:
            j = json.loads(meta_pkg.read_text(encoding="utf-8"))
            if j.get("character_art_direct_canonical"):
                cad = True
            if j.get("forced_character_sheet_on_character_art"):
                forced = True
            if cad:
                p = j.get("policy")
                if isinstance(p, str) and p.strip():
                    pol = p.strip()
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    slog = package_dir / "character" / "canonical_sheet_log.json"
    if slog.is_file():
        try:
            j = json.loads(slog.read_text(encoding="utf-8"))
            if j.get("forced_character_sheet_on_character_art"):
                forced = True
            if j.get("character_sheet_generation_mode") == "character_art_direct_canonical":
                cad = True
                p = j.get("policy")
                if isinstance(p, str) and p.strip():
                    pol = p.strip()
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    if not cad:
        pol = None
    return cad, forced, pol


def _resolve_candidate_identity_source(
    package_dir: Path, args: argparse.Namespace
) -> tuple[Path, bool, str]:
    """Base candidate source: input reference.png (sheet only with --use-character-sheet)."""
    use_sheet = bool(getattr(args, "use_character_sheet", False))
    if use_sheet:
        cs_cli = getattr(args, "character_sheet", None)
        if cs_cli and Path(cs_cli).is_file():
            return Path(cs_cli).resolve(), True, str(Path(cs_cli).resolve())
        sheet_pkg = _package_sheet_path(package_dir)
        if sheet_pkg.is_file():
            return sheet_pkg, True, str(sheet_pkg.resolve())
    refp = Path(package_dir) / "character" / "reference.png"
    if refp.is_file():
        return refp, False, str(refp.resolve())
    raise FileNotFoundError(
        "character/reference.png 가 필요합니다. "
        "베이스 후보는 입력 이미지 1장 기준으로 생성합니다."
    )


def _warn_cut_generation_reference(
    package_dir: Path,
    *,
    generation_reference_kind: str,
    generation_reference_path: Path,
) -> None:
    """컷 생성 전 참조·캐논 상태 경고 (드리프트 예방)."""
    mgr = CanonicalCharacterManager()
    canon = mgr.get_canonical_path(package_dir)
    cand_dir = package_dir / "character_candidates"
    has_cands = cand_dir.is_dir() and any(cand_dir.glob("candidate_*.png"))

    if has_cands and canon is None:
        print(
            "[경고] 베이스 후보 PNG는 있으나 character/canonical_character.png 가 없습니다. "
            "먼저 --select-candidate N 으로 마음에 드는 후보 1장을 캐논에 고정한 뒤 컷을 생성하세요.",
            file=sys.stderr,
        )
    if generation_reference_kind != "canonical_character":
        print(
            f"[경고] 컷 생성 참조가 캐논 캐릭터가 아닙니다 (kind={generation_reference_kind}, "
            f"file={generation_reference_path.name}). "
            "후보에서 만든 시암 고양이 등을 쓰려면 --select-candidate 후 canonical_character.png 가 "
            "기준이어야 합니다.",
            file=sys.stderr,
        )


def _resolve_stylizer_none_generation_reference(
    package_dir: Path,
    packaged_original_ref: Path,
    character_path: Path,
    args: argparse.Namespace,
    *,
    had_canonical_cli: bool,
    had_sheet_cli: bool,
    require_canonical: bool = False,
) -> tuple[Path, str] | None:
    """``stylizer none`` 컷 생성 기준: CLI 캐논 → package canonical → (선택) sheet → 없으면 오류."""
    _ = had_canonical_cli, had_sheet_cli, packaged_original_ref, character_path
    cc_arg = getattr(args, "canonical_character", None)
    if cc_arg:
        cpp = Path(cc_arg)
        if cpp.is_file():
            return cpp.resolve(), "canonical_character"

    mgr = CanonicalCharacterManager()
    canon = mgr.get_canonical_path(package_dir)
    sheet = _package_sheet_path(package_dir)
    use_sheet = bool(getattr(args, "use_character_sheet", False))

    if canon is not None and canon.is_file() and not use_sheet:
        return canon.resolve(), "canonical_character"
    if use_sheet and sheet.is_file():
        return sheet.resolve(), "canonical_sheet"
    if canon is not None and canon.is_file():
        return canon.resolve(), "canonical_character"

    if require_canonical:
        print(
            "[오류] character/canonical_character.png 가 없습니다. "
            "--select-candidate N 또는 --canonical-character PATH 를 먼저 사용하세요.",
            file=sys.stderr,
        )
        return None

    if packaged_original_ref.is_file():
        return packaged_original_ref.resolve(), "reference"
    return Path(character_path).resolve(), "reference"


def _merge_canonical_policy_with_reference_type(
    base_policy: str,
    *,
    reference_priority: str,
    stylizer_backend: str,
    ref_class: ReferenceClassification,
) -> str:
    """Adjust ``canonical_reference_policy`` for photo / character_art / unknown."""
    t = str(ref_class.reference_type).strip().lower()
    conf = float(ref_class.confidence)
    if t == "character_art" and reference_priority == "original_reference_photo":
        return "이미 캐릭터화된 입력이므로 원본 캐릭터를 직접 기준으로 사용"
    parts: list[str] = [base_policy.strip()]
    if t == "character_art" and reference_priority != "original_reference_photo":
        parts.append(
            "입력은 캐릭터 아트로 분류됨: openai/mock 표준 시트를 쓰면 원본 아트와 달라질 수 있음."
        )
    if t == "photo":
        parts.append(
            "입력은 실사로 분류됨: 캐릭터화 품질은 generator·stylizer(API) 성능에 좌우됨."
        )
        if str(stylizer_backend).strip().lower() == "openai":
            parts.append("stylizer=openai: 실사→캐릭터 원본 생성 실험 모드.")
    if t == "unknown":
        parts.append(
            "입력 타입: unknown(자동 판별 불확실). 필요 시 --reference-type 으로 photo/character_art/unknown 을 지정."
        )
    elif conf < 0.42 and t != "photo" and t != "character_art":
        parts.append(
            "입력 타입 자동 판별 신뢰도가 낮음 — 필요 시 --reference-type 으로 수동 지정 권장."
        )
    return " ".join(p for p in parts if p)


def _visual_anchor_reference_note(stylizer: str) -> str:
    """Default prompt hint: which raster anchors generation (matches ``--stylizer`` policy)."""
    s = str(stylizer).strip().lower()
    if s == "openai":
        return (
            "Primary visual anchor: OpenAI standardized_character.png (sticker-style master sheet). "
            "Match its silhouette, palette, and markings across cuts."
        )
    if s == "mock":
        return (
            "Primary visual anchor: development mock standardized_character_mock.png only "
            "(not photo-accurate)."
        )
    return (
        "Primary visual anchor: the packaged original pet photo (character/reference.png) "
        "plus the PetProfile consistency block — same animal identity, markings, ears, eyes, and silhouette; "
        "only pose, props, and framing change per cut."
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Build CLI arguments."""
    p = argparse.ArgumentParser(
        description=(
            "Kakao big emoticon prototype generator (mock images + package layout).\n"
            "통합 모드: --full-pipeline ⇒ mock 스타일·생성, 후처리, 일관성 검사·자동 재생성, WebP, HTML 미리보기까지 한 번에."
        )
    )
    p.add_argument(
        "--character",
        required=True,
        type=Path,
        help="Reference character PNG path (used for metadata copy in this prototype).",
    )
    p.add_argument("--series", required=True, help="Series display name.")
    p.add_argument("--theme", required=True, help="Theme keyword, e.g. love / daily.")
    p.add_argument(
        "--cut-templates",
        type=Path,
        default=None,
        help="16컷 템플릿 JSON 경로(Web UI 감정 문구 오버라이드).",
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help=f"Override output root (default: {OUTPUT_DIR} under project).",
    )
    p.add_argument(
        "--reference-note",
        default="",
        help="Optional short description of the reference image (vision model output can be pasted here later).",
    )
    p.add_argument(
        "--full-pipeline",
        action="store_true",
        help=(
            "통합 실행: --stylizer mock --generator mock --postprocess "
            "--check-consistency --auto-regenerate --make-webp 를 함께 적용합니다. "
            "OpenAI 없이 전체 파이프라인을 돌릴 때 사용합니다."
        ),
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "기존 시리즈 폴더에 덮어쓰기: 생성 결과(png·meta 로그·preview 등)만 초기화. "
            "character_candidates·canonical_character·canonical_sheet·identity_profile 은 기본 유지."
        ),
    )
    p.add_argument(
        "--reset-candidates",
        action="store_true",
        help="--overwrite 와 함께 character_candidates/ 전체 삭제.",
    )
    p.add_argument(
        "--reset-canonical",
        action="store_true",
        help="--overwrite 와 함께 character/canonical_character.png 및 source.json 삭제.",
    )
    p.add_argument(
        "--full-reset",
        action="store_true",
        help="outputs/<series> 폴더 전체 삭제 후 처음부터 (--overwrite 이전 동작).",
    )
    p.add_argument(
        "--reset-only",
        action="store_true",
        help="출력 정책(overwrite/full-reset 등)만 적용하고 종료(GUI 전체 초기화용).",
    )
    p.add_argument(
        "--stylizer",
        choices=("none", "mock", "openai"),
        default="none",
        help=(
            "스타일 표준화(기능 유지·정책): none=실무 기본(원본 실사+PetProfile로 생성; 표준 시트 비사용), "
            "openai=실험(표준 캐릭터를 생성 기준으로 사용·드리프트 가능), "
            "mock=개발 테스트용 목업(품질 판단 금지)."
        ),
    )
    p.add_argument(
        "--generator",
        choices=("mock", "openai"),
        default="mock",
        help="이미지 백엔드: mock(Pillow 목업), openai(GPT Image API).",
    )
    p.add_argument(
        "--openai-model",
        default="gpt-image-1",
        help="OpenAI Images 모델 (--generator openai일 때).",
    )
    p.add_argument(
        "--image-size",
        default="1024x1024",
        help="OpenAI 생성/편집 요청 크기 (예: 1024x1024).",
    )
    p.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="컷별 OpenAI API 재시도 횟수(편집+생성 사이클).",
    )
    p.add_argument(
        "--openai-mode",
        choices=("auto", "generate", "edit"),
        default="auto",
        help="컷 OpenAI: auto=참조 이미지 images.edit 우선, 실패 시 generate 폴백. edit|generate 로 고정 가능.",
    )
    p.add_argument(
        "--grid-mode",
        action="store_true",
        help=(
            "[OpenAI 전용] 16컷을 4×4 그리드 1장으로 생성 후 셀 크롭 — API 호출 1회로 비용 절감. "
            "--generator openai 와 함께 사용. --test-one / --test-ids 와는 병용 불가."
        ),
    )
    p.add_argument(
        "--no-text-overlay",
        action="store_true",
        dest="no_text_overlay",
        help="최종 PNG에 감정 텍스트 오버레이를 넣지 않음 (순수 캐릭터 이미지만 출력).",
    )
    p.add_argument(
        "--art-style",
        choices=("illustration", "realistic"),
        default="illustration",
        help=(
            "생성 스타일: illustration=치비·수채화 카툰(기본), "
            "realistic=한국 웹툰 세미-리얼리스틱."
        ),
    )
    p.add_argument(
        "--ai-text",
        action="store_true",
        help="AI가 캔버스에 한글 문구까지 그리도록 허용(기본은 Pillow 오버레이만).",
    )
    p.add_argument(
        "--species-hint",
        default=None,
        type=str,
        help="반려동물 종 힌트: cat, dog, rabbit, hamster, bird, unknown (미지정 시 unknown 처리).",
    )
    p.add_argument(
        "--personality-hint",
        default="",
        help="성격/무드 힌트(한 줄, 프롬프트에만 반영).",
    )
    p.add_argument(
        "--reference-type",
        choices=("auto", "photo", "character_art", "unknown"),
        default="auto",
        help="reference 분류: auto=휴리스틱 판별, 나머지=강제.",
    )
    p.add_argument(
        "--continue-on-error",
        action="store_true",
        help="컷 생성 실패 시 다음 컷 진행(QC 실패 가능; 기본은 즉시 중단).",
    )
    p.add_argument(
        "--check-consistency",
        dest="check_consistency",
        action="store_true",
        default=True,
        help="생성 후 캐릭터 일관성 휴리스틱 검사(meta/consistency_report.json). 기본 활성화.",
    )
    p.add_argument(
        "--no-check-consistency",
        dest="check_consistency",
        action="store_false",
        help="일관성 검사 생략.",
    )
    p.add_argument(
        "--consistency-threshold",
        type=float,
        default=0.72,
        help="일관성 점수 통과 기준 (0–1).",
    )
    p.add_argument(
        "--strict-consistency",
        action="store_true",
        help="일관성 검사 미통과 컷이 있으면 QC 결과와 무관하게 비정상 종료.",
    )
    p.add_argument(
        "--auto-regenerate",
        action="store_true",
        help="일관성·정적 QC(컷 단위 실패 시) 재생성; meta/regeneration_log.json 에 기록.",
    )
    p.add_argument(
        "--max-regenerate-attempts",
        type=int,
        default=2,
        help="재생성 배치 최대 횟수(남은 할당량이 소진될 때까지 일관성·품질 단계에서 공유).",
    )
    p.add_argument(
        "--postprocess",
        action="store_true",
        help=(
            "'사람 손 거친 듯한' 보수적 후처리: png_raw 에 정규화 원본 저장 후 processed/ 에 출력."
        ),
    )
    p.add_argument(
        "--postprocess-strength",
        type=float,
        default=0.45,
        help="후처리 강도 0–1 (--postprocess 시). 과도하게 올리면 디테일·자막이 손상될 수 있음.",
    )
    p.add_argument(
        "--use-processed-for-package",
        dest="use_processed_for_package",
        action="store_true",
        default=True,
        help="후처리본(processed/)을 패키지·아이콘·QC 대상 스티커 경로로 쓸지(기본 true).",
    )
    p.add_argument(
        "--no-use-processed-for-package",
        dest="use_processed_for_package",
        action="store_false",
        help="후처리는 processed/ 에만 두고 패키지·QC는 png_raw 정규화본 기준으로 사용.",
    )
    p.add_argument(
        "--make-webp",
        action="store_true",
        help="기본 3컷(01·03·10) WebP 애니메이션을 webp/ 에 생성(프로토타입).",
    )
    p.add_argument(
        "--webp-count",
        type=int,
        default=3,
        help="WebP로 내보낼 컷 수(기본 3, 최대 4: blink=04).",
    )
    p.add_argument(
        "--make-preview",
        action="store_true",
        help="브라우저용 preview.html 을 패키지 루트에 생성(QC·일관성·generation_log 반영).",
    )
    p.add_argument(
        "--webp-quality",
        type=int,
        default=85,
        help="WebP 품질 시작값(1MB 맞춤 시 자동 하향·프레임 듬).",
    )
    p.add_argument(
        "--test-one",
        action="store_true",
        help="컷 01 한 장만 생성·QC는 생성된 컷만 검사(OpenAI·mock 공통 스모크 테스트).",
    )
    p.add_argument(
        "--test-ids",
        default="",
        metavar="IDS",
        help='지정 컷만 생성(예: "01,02,03"). --test-one 보다 우선.',
    )
    p.add_argument(
        "--canonical-character",
        type=Path,
        default=None,
        help="PNG를 character/canonical_character.png 로 복사·고정(생성 기준, stylizer=none 일 때 우선).",
    )
    p.add_argument(
        "--make-candidates",
        action="store_true",
        help="character_candidates/ 에 캐릭터 후보만 생성하고 종료합니다.",
    )
    p.add_argument(
        "--candidate-count",
        type=int,
        default=3,
        help="--make-candidates 시 후보 수(기본 3, 최대 8).",
    )
    p.add_argument(
        "--select-candidate",
        type=int,
        default=None,
        metavar="N",
        help=(
            "1회성: character_candidates/candidate_NN.png → canonical_character.png 고정. "
            "이후 컷 생성은 캐논만 필요(후보 폴더 불필요)."
        ),
    )
    p.add_argument(
        "--make-character-sheet",
        action="store_true",
        help=(
            "character/canonical_sheet.png + canonical_sheet_log.json 생성 후 종료. "
            "reference_type=character_art 일 때는 기본적으로 AI 시트를 만들지 않고 "
            "canonical_character만 고정합니다(--force-character-sheet 필요)."
        ),
    )
    p.add_argument(
        "--force-character-sheet",
        action="store_true",
        help=(
            "reference_type=character_art 인데도 --make-character-sheet 로 "
            "AI 시트를 강제 생성합니다(캐릭터 드리프트 위험)."
        ),
    )
    p.add_argument(
        "--sheet-generator",
        choices=("mock", "openai"),
        default="mock",
        help="--make-character-sheet 시 사용할 백엔드.",
    )
    p.add_argument(
        "--sheet-openai-model",
        default="gpt-image-1",
        help="--sheet-generator openai 일 때 Images 모델 (기본 gpt-image-1).",
    )
    p.add_argument(
        "--sheet-openai-mode",
        choices=("auto", "generate", "edit"),
        default="auto",
        help=(
            "시트 OpenAI 호출 정책: auto|generate 는 images.generate 기준. "
            "edit 는 시트 경로에서 지원하지 않으며 명시적 오류로 안내합니다."
        ),
    )
    p.add_argument(
        "--candidate-openai-model",
        default="gpt-image-1",
        help="--make-candidates + --generator openai 일 때 Images 모델 (기본 gpt-image-1).",
    )
    p.add_argument(
        "--candidate-openai-mode",
        choices=("auto", "generate", "edit"),
        default="auto",
        help=(
            "후보 OpenAI: auto=입력 이미지 images.edit 우선, 실패 시 generate 폴백(경고). "
            "edit=이미지 참조만(폴백 없음). generate=텍스트-only(명시 선택 시만)."
        ),
    )
    p.add_argument(
        "--use-character-sheet",
        action="store_true",
        help="(고급) canonical_sheet.png 를 생성·일관성 기준으로 사용. 기본 흐름은 canonical_character.png.",
    )
    p.add_argument(
        "--character-sheet",
        type=Path,
        default=None,
        help="외부 시트 PNG를 character/canonical_sheet.png 로 복사해 사용합니다.",
    )
    p.add_argument(
        "--drift-threshold",
        type=float,
        default=0.68,
        help="v0.5 drift_similarity 통과 기준(0–1, 기본 0.68).",
    )
    p.add_argument(
        "--strict-drift",
        action="store_true",
        help="drift 경고(warn)도 실패로 처리합니다.",
    )
    p.add_argument(
        "--style-intensity",
        type=float,
        default=0.5,
        help=(
            "일러스트 질감 강도 0.0–1.0 (0=카카오 벡터풍, 0.5=기본, 1.0=수채화/동화책 고급 일러스트). "
            "후보 3장은 A/B/C로 0.0/0.5/1.0 고정."
        ),
    )
    p.add_argument(
        "--pose-variation-strength",
        type=float,
        default=1.0,
        help="포즈 변화 허용 강도 0.0–1.0 (정체성 고정, 포즈만 조절).",
    )
    p.add_argument(
        "--expression-strength",
        type=float,
        default=1.0,
        help="표정/감정 표현 강도 0.0–1.0 (얼굴 구조·눈 형태는 유지).",
    )
    p.add_argument(
        "--require-character-sheet",
        action="store_true",
        help="실사(photo) 입력 시 canonical_sheet.png 없으면 컷 생성을 중단합니다.",
    )
    p.add_argument(
        "--make-canonical-candidates",
        action="store_true",
        help="canonical 고정용 후보 3장 생성(--make-candidates 와 동일).",
    )
    ns = p.parse_args(argv)
    if getattr(ns, "make_canonical_candidates", False):
        ns.make_candidates = True
    if ns.full_pipeline:
        ns.stylizer = "mock"
        ns.generator = "mock"
        ns.postprocess = True
        ns.check_consistency = True
        ns.auto_regenerate = True
        ns.make_webp = True
        ns.make_preview = True
    return ns


def _count_png_files(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for p in directory.glob("*.png") if p.is_file())


def _safe_remove_series_output(out_root: Path, package_dir: Path) -> None:
    """Delete ``package_dir`` only when it is a strict subdirectory of ``out_root``."""
    out_r = Path(out_root).resolve()
    pkg_r = Path(package_dir).resolve()
    try:
        pkg_r.relative_to(out_r)
    except ValueError as exc:
        raise ValueError(
            f"출력 삭제 거부: 패키지 경로가 출력 루트 밖입니다.\n  package_dir={pkg_r}\n  out_root={out_r}"
        ) from exc
    if pkg_r == out_r:
        raise ValueError("출력 삭제 거부: package_dir 가 출력 루트와 동일합니다.")
    if pkg_r.is_dir():
        shutil.rmtree(pkg_r)


_GENERATION_OUTPUT_DIRS = (
    "png",
    "generated_raw",
    "png_no_text",
    "processed",
    "failed_consistency",
    "failed_quality",
    "webp",
)

_META_GENERATED_FILES = (
    "generation_log.json",
    "prompts.json",
    "cut_plan.json",
    "package_info.json",
    "consistency_report.json",
    "regeneration_log.json",
    "style_log.json",
    "style_prompt.txt",
    "webp_report.json",
)


def _remove_path_quiet(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.is_file():
        path.unlink()


def _clear_generation_outputs(
    package_dir: Path,
    *,
    reset_candidates: bool = False,
    reset_canonical: bool = False,
) -> None:
    """컷·QC·미리보기 등 생성 산출물만 제거 (캐논·후보·identity_profile 기본 유지)."""
    pkg = Path(package_dir)
    for name in _GENERATION_OUTPUT_DIRS:
        _remove_path_quiet(pkg / name)
    preview = pkg / "preview.html"
    if preview.is_file():
        preview.unlink()
    meta = pkg / "meta"
    if meta.is_dir():
        for fname in _META_GENERATED_FILES:
            p = meta / fname
            if p.is_file():
                p.unlink()
    if reset_candidates:
        _remove_path_quiet(pkg / "character_candidates")
    if reset_canonical:
        char = pkg / "character"
        for fname in ("canonical_character.png", "canonical_character_source.json"):
            p = char / fname
            if p.is_file():
                p.unlink()


def _apply_package_output_policy(
    out_root: Path,
    package_dir: Path,
    args: argparse.Namespace,
) -> dict[str, bool]:
    """``--full-reset`` / ``--overwrite`` / 선택적 reset 플래그 적용. 보존 여부 반환."""
    full = bool(getattr(args, "full_reset", False))
    overwrite = bool(getattr(args, "overwrite", False))
    reset_cand = bool(getattr(args, "reset_candidates", False))
    reset_canon = bool(getattr(args, "reset_canonical", False))

    if full and package_dir.exists():
        _safe_remove_series_output(out_root, package_dir)
        return {"candidates_preserved": False, "canonical_preserved": False}

    candidates_preserved = True
    canonical_preserved = True

    if not package_dir.exists():
        return {
            "candidates_preserved": candidates_preserved,
            "canonical_preserved": canonical_preserved,
        }

    if overwrite:
        _clear_generation_outputs(
            package_dir,
            reset_candidates=reset_cand,
            reset_canonical=reset_canon,
        )
        if reset_cand:
            candidates_preserved = False
        if reset_canon:
            canonical_preserved = False
    else:
        if reset_cand:
            _remove_path_quiet(package_dir / "character_candidates")
            candidates_preserved = False
        if reset_canon:
            char = package_dir / "character"
            for fname in ("canonical_character.png", "canonical_character_source.json"):
                p = char / fname
                if p.is_file():
                    p.unlink()
            canonical_preserved = False

    return {
        "candidates_preserved": candidates_preserved,
        "canonical_preserved": canonical_preserved,
    }


def _share_sticker_sources(package_rows: list[dict], sticker_dir: Path) -> list[Path]:
    """Sticker PNG paths for share banner: only ``package_rows`` cut ids (no 01–16 folder scan)."""
    ids: list[str] = []
    for prow in package_rows:
        if not isinstance(prow, dict) or prow.get("id") is None:
            continue
        cid = str(prow["id"]).strip().zfill(2)
        if len(cid) == 2 and cid.isdigit():
            ids.append(cid)
    out: list[Path] = []
    for cid in sorted(set(ids), key=lambda x: int(x)):
        p = sticker_dir / f"{cid}.png"
        if p.is_file():
            out.append(p)
    return out


def _regeneration_batch_total(regeneration_log_body: dict[str, object] | None) -> int:
    if not regeneration_log_body:
        return 0
    total = 0
    for key in ("consistency_phase", "quality_phase"):
        phase = regeneration_log_body.get(key)
        if isinstance(phase, dict) and isinstance(phase.get("batches_used"), int):
            total += int(phase["batches_used"])
    return total


def _is_emoticon_cut_id(cut_id: str) -> bool:
    """True for numbered sticker cuts ``01``..``16`` (exclude checker pseudo-rows)."""
    return len(cut_id) == 2 and cut_id.isdigit() and 1 <= int(cut_id) <= 16


def _parse_test_ids_csv(raw: str) -> list[str] | None:
    """Parse ``--test-ids`` like ``01,02, 3`` → ``['01','02','03']`` (unique, sorted, validated)."""
    if not raw or not str(raw).strip():
        return None
    seen: set[str] = set()
    out: list[str] = []
    for part in str(raw).replace(";", ",").split(","):
        tok = str(part).strip()
        if not tok:
            continue
        sid = tok.zfill(2) if tok.isdigit() else tok
        if not _is_emoticon_cut_id(sid):
            return None
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    if not out:
        return None
    return sorted(out, key=lambda x: int(x))


def _failed_cut_ids_union(
    *,
    consistency_report: dict[str, object] | None,
    qc_report: dict[str, object],
    generation_log: dict[str, object] | None,
) -> list[str]:
    ids: set[str] = set()
    if consistency_report:
        for row in consistency_report.get("failed") or []:
            if isinstance(row, dict) and row.get("id") is not None:
                sid = str(row["id"])
                if _is_emoticon_cut_id(sid):
                    ids.add(sid)
    png_e = qc_report.get("per_cut_png_errors") or {}
    icon_e = qc_report.get("per_cut_icon_errors") or {}
    ids |= set(map(str, png_e.keys()))
    ids |= set(map(str, icon_e.keys()))
    if generation_log:
        for cut in generation_log.get("cuts") or []:
            if isinstance(cut, dict) and not cut.get("success") and cut.get("id") is not None:
                ids.add(str(cut["id"]))
    return sorted(ids, key=lambda x: int(x) if x.isdigit() else 0)


def _read_meta_json(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _meta_first(*values: object, default: str = "—") -> str:
    for v in values:
        if v is None:
            continue
        if isinstance(v, bool):
            return "true" if v else "false"
        s = str(v).strip()
        if s:
            return s
    return default


def _canonical_identity_score_avg(consistency_report: dict[str, object] | None) -> str:
    if not consistency_report:
        return "—"
    scores: list[float] = []
    for row in consistency_report.get("items") or []:
        if not isinstance(row, dict):
            continue
        raw = row.get("canonical_identity_score")
        if raw is None:
            continue
        try:
            scores.append(float(raw))
        except (TypeError, ValueError):
            pass
    if not scores:
        return "—"
    return f"{sum(scores) / len(scores):.4f} (n={len(scores)})"


def _print_run_summary(
    *,
    package_dir: Path,
    raw_out_dir: Path,
    processed_dir: Path,
    sticker_dir: Path,
    webp_dir: Path,
    icon_dir: Path,
    share_png: Path,
    postprocess: bool,
    make_webp: bool,
    qc_report: dict[str, object],
    consistency_report: dict[str, object] | None,
    check_consistency_ran: bool,
    regeneration_log_body: dict[str, object] | None,
    generation_log: dict[str, object] | None,
    test_one: bool = False,
    logical_emoticon_n: int | None = None,
    selected_cut_ids: list[str] | None = None,
    preservation_policy: dict[str, bool] | None = None,
) -> None:
    """Print v0.7 end-of-run summary (stdout; GUI PipelineRunner shows this as-is)."""
    meta_dir = package_dir / "meta"
    pkg_info = _read_meta_json(meta_dir / "package_info.json") or {}
    gen_log_disk = _read_meta_json(meta_dir / "generation_log.json")
    gen_log = generation_log if generation_log else gen_log_disk or {}
    identity_doc = _read_meta_json(meta_dir / "identity_profile.json") or {}
    sheet_log = _read_meta_json(package_dir / "character" / "canonical_sheet_log.json") or {}
    cons_disk = _read_meta_json(meta_dir / "consistency_report.json")
    cons = consistency_report if consistency_report is not None else cons_disk
    regen_disk = _read_meta_json(meta_dir / "regeneration_log.json")
    regen = regeneration_log_body if regeneration_log_body else regen_disk

    if logical_emoticon_n is not None and logical_emoticon_n >= 0:
        gen_n = sticker_n = int(logical_emoticon_n)
        proc_n = int(logical_emoticon_n) if postprocess else 0
    else:
        gen_n = _count_png_files(raw_out_dir)
        proc_n = _count_png_files(processed_dir) if postprocess else 0
        sticker_n = _count_png_files(sticker_dir)

    checks_obj = qc_report.get("checks") or {}
    if make_webp and isinstance(checks_obj, dict):
        aw = checks_obj.get("animated_webp")
        webp_n = len(aw) if isinstance(aw, list) else _count_webp_files(webp_dir)
    elif make_webp:
        webp_n = _count_webp_files(webp_dir)
    else:
        webp_n = 0

    qc_ok = bool(qc_report.get("ok"))
    qc_errs = qc_report.get("errors") or []
    qc_warns = qc_report.get("warnings") or []
    qc_line = "통과" if qc_ok else f"실패 (오류 {len(qc_errs)}건)"
    if qc_warns:
        qc_line += f", 경고 {len(qc_warns)}건"

    if not check_consistency_ran:
        cons_line = (
            "미실행 (부분 컷: --test-ids / --test-one)"
            if selected_cut_ids or test_one
            else "미실행 (--no-check-consistency 등)"
        )
    elif cons is None:
        cons_line = "없음"
    elif bool(cons.get("ok")):
        cons_line = "통과"
    else:
        failed = cons.get("failed") or []
        fids = [
            str(x.get("id"))
            for x in failed
            if isinstance(x, dict)
            and x.get("id") is not None
            and _is_emoticon_cut_id(str(x.get("id")))
        ]
        n_cut_fails = len(fids)
        n_other = len(failed) - n_cut_fails
        extras = f" 기타 {n_other}건" if n_other else ""
        cons_line = (
            f"실패 (컷 {n_cut_fails}건){extras}: {', '.join(fids) if fids else '(없음)'}"
        )

    regen_batches = _regeneration_batch_total(regen)
    failed_ids = _failed_cut_ids_union(
        consistency_report=cons,
        qc_report=qc_report,
        generation_log=gen_log,
    )
    failed_line = ", ".join(failed_ids) if failed_ids else "(없음)"

    ref_type = _meta_first(
        gen_log.get("reference_type"),
        pkg_info.get("reference_type"),
    )
    entity_type = _meta_first(
        gen_log.get("entity_type"),
        identity_doc.get("entity_type"),
    )
    species_hint = _meta_first(
        identity_doc.get("species"),
        (gen_log.get("pet_profile") or {}).get("species")
        if isinstance(gen_log.get("pet_profile"), dict)
        else None,
        (pkg_info.get("pet_profile") or {}).get("species")
        if isinstance(pkg_info.get("pet_profile"), dict)
        else None,
    )
    id_prof_path = meta_dir / "identity_profile.json"
    id_prof_line = str(id_prof_path.relative_to(package_dir)) if id_prof_path.is_file() else "—"

    gen_ref_kind = _meta_first(
        gen_log.get("generation_reference_kind"),
    )
    canon_char_used = bool(
        gen_log.get("canonical_character_used")
        if gen_log.get("canonical_character_used") is not None
        else pkg_info.get("canonical_character_used")
    )
    canon_char_path = _meta_first(
        gen_log.get("canonical_character_path"),
        pkg_info.get("canonical_character_path"),
    )
    canon_sheet_used = bool(
        gen_log.get("canonical_sheet_used")
        if gen_log.get("canonical_sheet_used") is not None
        else pkg_info.get("canonical_sheet_used")
    )
    canon_sheet_path = _meta_first(
        gen_log.get("canonical_sheet_path"),
        pkg_info.get("canonical_sheet_path"),
        "character/canonical_sheet.png"
        if (package_dir / "character" / "canonical_sheet.png").is_file()
        else None,
    )
    gen_ref_path = _meta_first(
        gen_log.get("reference_image_used"),
        gen_log.get("packaged_original_reference"),
        cons.get("reference_path") if cons else None,
    )

    generator_backend = _meta_first(
        gen_log.get("generator_backend"),
        gen_log.get("generator"),
        pkg_info.get("generator_backend"),
    )
    sheet_gen_backend = _meta_first(
        sheet_log.get("character_sheet_generator_backend"),
        sheet_log.get("backend"),
        pkg_info.get("character_sheet_generator_backend"),
    )
    stylizer_backend = _meta_first(
        gen_log.get("stylizer_backend"),
        pkg_info.get("stylizer_backend"),
    )
    openai_model = _meta_first(gen_log.get("openai_model"), default="—")
    sheet_openai_model = _meta_first(
        sheet_log.get("openai_model"),
        sheet_log.get("model"),
        default="—",
    )

    no_ai_text = gen_log.get("no_ai_text")
    if no_ai_text is None:
        no_ai_text = pkg_info.get("no_ai_text")
    if no_ai_text is True or no_ai_text is None:
        text_overlay = "Pillow (no_ai_text 기본)"
    elif no_ai_text is False:
        text_overlay = "AI (프롬프트 내 문구)"
    else:
        text_overlay = "none"

    try:
        style_si = float(gen_log.get("style_intensity", 0.5))
    except (TypeError, ValueError):
        style_si = 0.5
    anti_flat = "on" if style_si >= 0.35 else "low/off"

    try:
        pose_si = float(gen_log.get("pose_variation_strength", 1.0))
    except (TypeError, ValueError):
        pose_si = 1.0
    try:
        expr_si = float(gen_log.get("expression_strength", 1.0))
    except (TypeError, ValueError):
        expr_si = 1.0

    canonical_identity_mode = bool(
        canon_char_used
        and gen_ref_kind == "canonical_character"
        and stylizer_backend == "none"
    ) or bool(canon_sheet_used and gen_ref_kind == "canonical_sheet")

    heatmap = cons.get("identity_drift_heatmap") if cons else None
    if isinstance(heatmap, list) and heatmap:
        heatmap_line = f"있음 ({len(heatmap)}컷, consistency_report.json)"
    else:
        heatmap_line = "—"

    preview_path = package_dir / "preview.html"
    pkg_info_path = meta_dir / "package_info.json"

    sel_ids = selected_cut_ids or gen_log.get("selected_cut_ids")
    if isinstance(sel_ids, list):
        sel_ids_list = [str(x) for x in sel_ids]
    else:
        sel_ids_list = []

    text_only_fallback = bool(
        sheet_log.get("text_only_fallback")
        or gen_log.get("text_only_fallback")
    )

    print("\n========== 실행 요약 ==========")
    if preservation_policy is not None:
        print("[보존 정책]")
        print(
            f"- candidates preserved: "
            f"{str(preservation_policy.get('candidates_preserved', True)).lower()}"
        )
        print(
            f"- canonical preserved: "
            f"{str(preservation_policy.get('canonical_preserved', True)).lower()}"
        )
    print("[입력/정체성]")
    print(f"- 입력 타입(reference_type): {ref_type}")
    print(f"- 생물체 타입(entity_type): {entity_type}")
    print(f"- species_hint: {species_hint}")
    if identity_doc:
        id_kw = identity_doc.get("identity_keywords")
        id_kw_s = id_kw[0] if isinstance(id_kw, list) and id_kw else "—"
        print(f"- identity_profile: {id_kw_s} (meta/identity_profile.json)")
    else:
        print("- identity_profile: —")
    print(f"- canonical_identity_mode: {canonical_identity_mode}")
    print(f"- identity_profile_path: {id_prof_line}")

    print("[기준 이미지] (기본: canonical_character)")
    print(f"- canonical_character_used: {canon_char_used}")
    print(f"- canonical_character_path: {canon_char_path}")
    print(f"- generation_reference_kind: {gen_ref_kind}")
    print(f"- generation_reference_path: {gen_ref_path}")
    if canon_sheet_used or (package_dir / "character" / "canonical_sheet.png").is_file():
        print(f"- (고급) canonical_sheet_used: {canon_sheet_used}")
        print(f"- (고급) canonical_sheet_path: {canon_sheet_path}")
    else:
        print("- (고급) canonical_sheet: 미사용")

    print("[AI/생성 백엔드]")
    print(f"- generator_backend: {generator_backend}")
    print(f"- sheet_generator_backend: {sheet_gen_backend}")
    print(f"- stylizer_backend: {stylizer_backend}")
    print(f"- openai_model: {openai_model}")
    print(f"- sheet_openai_model: {sheet_openai_model}")
    print(f"- text_overlay: {text_overlay}")

    print("[스타일]")
    print(f"- style_intensity: {style_si}")
    print(f"- pose_variation_strength: {pose_si}")
    print(f"- expression_strength: {expr_si}")
    print(f"- anti_flat_texture: {anti_flat}")
    print(f"- no_ai_text: {no_ai_text}")

    print("[산출물]")
    print(f"- 패키지 경로: {package_dir.resolve()}")
    print(f"- 생성 PNG 개수: {gen_n}  ({raw_out_dir.resolve()})")
    print(f"- 최종 스티커 PNG 개수: {sticker_n}  ({sticker_dir.resolve()})")
    if postprocess:
        print(f"- 후처리 PNG 개수: {proc_n}  ({processed_dir.resolve()})")
    if make_webp:
        print(f"- WebP 개수: {webp_n}  ({webp_dir.resolve()})")
    else:
        print("- WebP 개수: — (--make-webp 미사용)")
    print(
        f"- preview.html: {preview_path.resolve() if preview_path.is_file() else '—'}"
    )
    print(
        f"- package_info.json: {pkg_info_path.resolve() if pkg_info_path.is_file() else '—'}"
    )
    print(f"- 아이콘: {icon_dir.resolve()}")
    print(f"- 공유 이미지: {share_png.resolve()}")

    print("[품질/드리프트]")
    print(f"- QualityChecker: {qc_line}")
    print(f"- ConsistencyChecker: {cons_line}")
    print(f"- canonical_identity_score avg: {_canonical_identity_score_avg(cons)}")
    print(f"- identity_drift_heatmap: {heatmap_line}")
    print(f"- failed cuts: {failed_line}")
    print(f"- regeneration batches: {regen_batches}")
    if sel_ids_list:
        print(f"- selected_cut_ids: {', '.join(sel_ids_list)}")

    cand_dir = package_dir / "character_candidates"
    has_base_candidates = (cand_dir / "candidates.json").is_file() or any(
        cand_dir.glob("candidate_*.png")
    )

    print("[다음 추천 작업]")
    tips: list[str] = []
    if has_base_candidates and not canon_char_used:
        tips.append(
            "베이스 후보 3장이 준비되었습니다. 3장 중 하나를 --select-candidate N 으로 선택하세요."
        )
    if not canon_char_used and not has_base_candidates:
        tips.append(
            "먼저 --make-candidates 로 베이스 캐릭터 후보 3장을 만들고 1장을 선택하세요."
        )
    if canon_char_used and sel_ids_list and sticker_n <= max(len(sel_ids_list), 3):
        tips.append(
            "3컷 테스트가 끝났습니다. 품질과 정체성이 괜찮으면 --select-candidate 를 유지한 채 16컷 전체를 생성하세요."
        )
    if generator_backend == "mock":
        tips.append(
            "Mock은 흐름 확인용입니다. 실제 품질 확인은 --generator openai 로 테스트하세요."
        )
    if generator_backend == "openai" and sel_ids_list and sticker_n > 3:
        tips.append(
            "부분 컷 테스트 완료. 정체성 유지가 괜찮으면 selected_cut_ids 없이 전체 16컷을 생성하세요."
        )
    if (
        generator_backend == "openai"
        and check_consistency_ran
        and cons is not None
        and not bool(cons.get("ok"))
    ):
        tips.append(
            "드리프트 실패 컷이 있습니다. --auto-regenerate 또는 canonical 후보 재선택을 권장합니다."
        )
    if not canon_char_used and not has_base_candidates:
        tips.append(
            "16컷 생성 전에 반드시 베이스 후보 3장 → 1장 선택 → canonical_character.png 고정 순서를 따르세요."
        )
    if text_only_fallback:
        tips.append(
            "이미지 참조 없이 텍스트 기반 생성으로 폴백되어 캐릭터 드리프트 가능성이 있습니다."
        )
    if not qc_ok:
        tips.append(
            "품질 검사 오류를 수정한 뒤 --overwrite 로 재실행하거나 failed 컷만 --test-ids 로 재생성하세요."
        )
    if make_webp:
        tips.append(
            "카카오 제출 전 webp/*.webp 를 공식 도구·가이드로 최종 검수·재인코딩하세요."
        )
    if not tips:
        tips.append("preview.html 과 consistency_report.json 을 검토한 뒤 전체 16컷 생성을 진행하세요.")
    for t in tips:
        print(f"  · {t}")
    print("==============================\n")


def _count_webp_files(webp_dir: Path) -> int:
    if not webp_dir.is_dir():
        return 0
    return sum(1 for p in webp_dir.glob("*.webp") if p.is_file())


def _package_emoticon_subdir(postprocess: bool, use_processed_for_package: bool) -> str:
    if not postprocess:
        return "png"
    return "processed" if use_processed_for_package else "png_raw"


def _humanize_after_generate(
    postprocess: bool,
    *,
    strength: float,
    raw_out_dir: Path,
    processed_dir: Path,
) -> None:
    if not postprocess:
        return
    hp = HumanizePostProcessor(strength)
    inputs = sorted(raw_out_dir.glob("*.png"), key=lambda x: x.stem)
    if not inputs:
        return
    hp.process_batch(inputs, processed_dir)


def _rebuild_icons_after_sticker_touch(
    package_rows: list[dict],
    sticker_dir: Path,
    icon_dir: Path,
    processor: ImageProcessor,
) -> None:
    for prow in package_rows:
        cid = str(prow.get("id", ""))
        src = sticker_dir / f"{cid}.png"
        if src.is_file():
            processor.create_icon(src, icon_dir / f"{cid}.png")


def _summarize_regeneration_phase(res: dict | None) -> dict | None:
    if res is None or not isinstance(res, dict):
        return res
    out = dict(res)
    full = out.pop("final_consistency_report", None)
    if isinstance(full, dict):
        out["final_consistency_ok"] = full.get("ok")
        out["final_failed_ids"] = [
            str(x.get("id"))
            for x in (full.get("failed") or [])
            if isinstance(x, dict) and x.get("id") is not None
        ]

    batches = out.pop("batches", None)
    if isinstance(batches, list):
        out["batch_summaries"] = []
        for b in batches:
            if not isinstance(b, dict):
                continue
            cuts = []
            for c in b.get("cut_entries") or []:
                if isinstance(c, dict):
                    cuts.append(
                        {
                            "id": c.get("id"),
                            "batch_index": c.get("batch_index"),
                            "issue_codes": c.get("issue_codes"),
                            "ok": c.get("ok"),
                            "error": c.get("error"),
                            "wall_seconds": c.get("wall_seconds"),
                            "prompt_suffix_lines": c.get("prompt_suffix_lines"),
                        }
                    )
            out["batch_summaries"].append(
                {
                    "batch_index": b.get("batch_index"),
                    "failure_source": b.get("failure_source"),
                    "cuts": cuts,
                    "consistency_snapshot": b.get("consistency_snapshot"),
                }
            )
    return out


def _print_consistency_report_block(
    consistency_report: dict[str, object], threshold: float
) -> None:
    print("\n=== 캐릭터 일관성 검사(v0.3 휴리스틱) ===")
    for row in consistency_report.get("items", []):
        if not isinstance(row, dict):
            continue
        rid = row.get("id", "?")
        score = row.get("score", 0)
        status = row.get("status", "?")
        print(f"  컷 {rid}: score={score}  {status}")
    fails = consistency_report.get("failed") or []
    if fails:
        print(
            f"\n[일관성] 임계값 {threshold} 미만 또는 분석 실패: "
            f"{len(fails)}건 → failed_consistency/ 및 meta/consistency_report.json 참고",
            file=sys.stderr,
        )
    else:
        print("\n[일관성] 전 컷 통과.")


def main(argv: list[str] | None = None) -> int:
    """Run the full generation and QA pipeline."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    load_dotenv()
    args = parse_args(argv)
    had_canonical_cli = getattr(args, "canonical_character", None) is not None
    had_sheet_cli = bool(getattr(args, "use_character_sheet", False)) and (
        getattr(args, "character_sheet", None) is not None
    )

    sc_sel = getattr(args, "select_candidate", None)
    if sc_sel is not None and (int(sc_sel) < 1 or int(sc_sel) > 8):
        print("[오류] --select-candidate 는 1–8 범위의 정수여야 합니다.", file=sys.stderr)
        return 2

    test_one_cli = bool(getattr(args, "test_one", False))
    raw_test_ids = str(getattr(args, "test_ids", "") or "").strip()
    selected_cut_ids: list[str] | None = None
    if raw_test_ids:
        selected_cut_ids = _parse_test_ids_csv(raw_test_ids)
        if selected_cut_ids is None:
            print(
                "[오류] --test-ids 는 01–16 범위의 컷 id만 쉼표로 나열하세요. 예: --test-ids \"01,02,03\"",
                file=sys.stderr,
            )
            return 2
        if test_one_cli:
            print(
                "[경고] --test-one 과 --test-ids 가 함께 지정됨: --test-ids 가 우선합니다.",
                file=sys.stderr,
            )
    elif test_one_cli:
        selected_cut_ids = ["01"]

    partial_generation = selected_cut_ids is not None
    test_one = bool(test_one_cli and not raw_test_ids)

    effective_make_webp = bool(args.make_webp) and not partial_generation
    effective_check_consistency = bool(args.check_consistency) and not partial_generation
    effective_auto_regenerate = bool(args.auto_regenerate) and not partial_generation

    qc_expected_ids: list[str] | None = (
        list(selected_cut_ids) if partial_generation and selected_cut_ids else None
    )

    character_path: Path = args.character
    if not character_path.is_file():
        print(f"[오류] 캐릭터 이미지를 찾을 수 없습니다: {character_path}", file=sys.stderr)
        return 2

    series_name: str = args.series
    theme: str = args.theme
    folder = safe_folder_name(series_name)
    out_root = Path(args.output_root) if args.output_root else PROJECT_ROOT / OUTPUT_DIR
    package_dir = out_root / folder

    allow_existing_write = bool(
        getattr(args, "overwrite", False)
        or getattr(args, "full_reset", False)
        or getattr(args, "reset_candidates", False)
        or getattr(args, "reset_canonical", False)
    )
    if package_dir.exists() and any(package_dir.iterdir()) and not allow_existing_write:
        print(
            f"[오류] 출력 폴더가 이미 있습니다: {package_dir}\n"
            f"       생성 결과만 갱신: --overwrite · 전체 삭제: --full-reset",
            file=sys.stderr,
        )
        return 3

    preservation_policy = _apply_package_output_policy(out_root, package_dir, args)

    if bool(getattr(args, "reset_only", False)):
        summary = {
            "reset_only": True,
            "package_dir": str(package_dir.resolve()) if package_dir.exists() else None,
            "full_reset": bool(getattr(args, "full_reset", False)),
            "overwrite": bool(getattr(args, "overwrite", False)),
            "preservation_policy": preservation_policy,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("[보존 정책]")
        print(
            f"- candidates preserved: "
            f"{str(preservation_policy.get('candidates_preserved', True)).lower()}"
        )
        print(
            f"- canonical preserved: "
            f"{str(preservation_policy.get('canonical_preserved', True)).lower()}"
        )
        return 0

    try:
        canonical_character_used_for_pkg = False
        canonical_character_path_for_pkg: str | None = None
        canonical_character_policy_for_pkg: str | None = None
        canonical_identity_mode = False
        canonical_sheet_mode = False
        canonical_sheet_used_for_pkg = False
        canonical_sheet_path_for_pkg: str | None = None
        canonical_sheet_policy_for_pkg: str | None = None
        generation_reference_kind = "reference"

        pkg = PackageBuilder(out_root)
        pkg.ensure_package_dirs(package_dir)
        style_si = clamp_style_intensity(getattr(args, "style_intensity", 0.5))
        pose_si = clamp_strength(getattr(args, "pose_variation_strength", 1.0))
        expr_si = clamp_strength(getattr(args, "expression_strength", 1.0))
        art_style = str(getattr(args, "art_style", "illustration")).strip().lower()

        character_dir = package_dir / "character"
        character_dir.mkdir(parents=True, exist_ok=True)

        meta_dir = package_dir / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)

        ref_proc = ReferenceProcessor()
        ref_result = ref_proc.process(character_path, character_dir)
        for warn in ref_result.get("warnings", []):
            print(f"[경고] {warn}", file=sys.stderr)

        standardized_ref: Path = character_path
        base_abs = ref_result.get("character_base_absolute")
        if isinstance(base_abs, Path) and base_abs.is_file():
            standardized_ref = base_abs

        packaged_original_ref = character_dir / "reference.png"
        try:
            # shutil.copy2 대신 PIL로 변환저장 — exFAT에서 shutil.copy2가
            # AppleDouble 메타데이터만 쓰는 버그 회피 + 정식 PNG 보장
            from PIL import Image as _PILImage
            _ref_img = _PILImage.open(Path(character_path)).convert("RGBA")
            _ref_img.save(packaged_original_ref, format="PNG")
        except Exception as exc:
            print(
                f"[경고] character/reference.png 로 원본을 복사하지 못했습니다: {exc}",
                file=sys.stderr,
            )

        stylizer_input = (
            packaged_original_ref
            if packaged_original_ref.is_file()
            else Path(character_path).resolve()
        )

        rt_arg = str(getattr(args, "reference_type", "auto")).strip().lower()
        if rt_arg not in {"auto", "photo", "character_art", "unknown"}:
            rt_arg = "auto"
        if rt_arg == "auto":
            ref_class = ReferenceClassifier().analyze(stylizer_input)
        else:
            ref_class = ReferenceClassification(
                reference_type=rt_arg,
                confidence=1.0,
                reasons=[f"--reference-type 으로 '{rt_arg}'(으)로 고정"],
                metrics={"cli_forced": True, "cli_value": rt_arg},
            )

        _id_src = (
            packaged_original_ref
            if packaged_original_ref.is_file()
            else character_path
        )
        identity_profile = IdentityProfileAnalyzer().analyze(
            Path(_id_src),
            species_hint=getattr(args, "species_hint", None),
            personality_hint=(args.personality_hint or None) or None,
            reference_type=ref_class.reference_type,
        )
        pet = PetProfileAnalyzer().analyze(
            Path(_id_src),
            species_hint=getattr(args, "species_hint", None),
            personality_hint=(args.personality_hint or None) or None,
        )
        profile = CharacterProfile.from_identity_profile(identity_profile)
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "identity_profile.json").write_text(
            json.dumps(identity_profile.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        cs_cli = getattr(args, "character_sheet", None)
        if cs_cli:
            spp = Path(cs_cli)
            if not spp.is_file():
                print(f"[오류] --character-sheet 파일을 찾을 수 없습니다: {spp}", file=sys.stderr)
                return 2
            _package_sheet_path(package_dir).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(spp, _package_sheet_path(package_dir))

        if bool(getattr(args, "make_character_sheet", False)):
            sheet_src = (
                packaged_original_ref
                if packaged_original_ref.is_file()
                else Path(character_path).resolve()
            )
            rt_lower = str(ref_class.reference_type).strip().lower()
            force_sheet = bool(getattr(args, "force_character_sheet", False))
            policy_ko = CHARACTER_ART_DIRECT_POLICY_KO

            if rt_lower == "character_art" and not force_sheet:
                sp = _package_sheet_path(package_dir)
                if sp.is_file():
                    try:
                        sp.unlink()
                    except OSError:
                        pass
                CanonicalCharacterManager.set_from_existing_image(
                    Path(sheet_src),
                    package_dir,
                    "character_art_direct",
                    {
                        "original_reference": (
                            "character/reference.png"
                            if packaged_original_ref.is_file()
                            else str(Path(character_path).name)
                        ),
                        "policy": policy_ko,
                    },
                )
                log = {
                    "make_character_sheet": True,
                    "character_art_direct_canonical": True,
                    "skipped_sheet_generation": True,
                    "character_sheet_generation_mode": "character_art_direct_canonical",
                    "reference_type": ref_class.reference_type,
                    "canonical_character_used": True,
                    "canonical_sheet_used": False,
                    "policy": policy_ko,
                    "text_only_fallback": False,
                    "drift_risk_warning": False,
                }
                log_path = package_dir / "character" / "canonical_sheet_log.json"
                log_path.write_text(
                    json.dumps(log, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                merge_package_info_character_art_direct_canonical(
                    package_dir,
                    series_name=series_name,
                    theme=theme,
                    pet_profile=pet.model_dump(),
                    character_profile=profile.model_dump(),
                    reference_type=ref_class.reference_type,
                    policy_ko=policy_ko,
                    pet_profile_source=PET_PROFILE_SOURCE,
                )
                merge_generation_log_sheet_fields(meta_dir, log)
                print(json.dumps({"make_character_sheet": True, "log": log}, ensure_ascii=False, indent=2))
                return 0

            try:
                sgen = create_character_sheet_generator(
                    getattr(args, "sheet_generator", "mock"),
                    openai_model=str(getattr(args, "sheet_openai_model", "gpt-image-1")),
                    openai_mode=str(getattr(args, "sheet_openai_mode", "auto")),
                    openai_size=str(args.image_size),
                    openai_retries=max(1, min(5, int(args.max_retries))),
                )
                log = sgen.generate(
                    photo_path=Path(sheet_src),
                    package_dir=package_dir,
                    series_name=series_name,
                    profile=profile,
                    reference_type=ref_class.reference_type,
                    forced_character_sheet_on_character_art=(
                        rt_lower == "character_art" and force_sheet
                    ),
                    style_intensity=style_si,
                )
            except OpenAIMissingKeyError as mk:
                print(str(mk), file=sys.stderr)
                return 7
            except Exception as exc:
                print(f"[오류] character sheet: {exc}", file=sys.stderr)
                return 6
            merge_package_info_sheet_fields(
                package_dir,
                series_name=series_name,
                theme=theme,
                pet_profile=pet.model_dump(),
                character_profile=profile.model_dump(),
                reference_type=ref_class.reference_type,
                sheet_log=log,
                pet_profile_source=PET_PROFILE_SOURCE,
            )
            merge_generation_log_sheet_fields(meta_dir, log)
            if rt_lower == "character_art" and force_sheet:
                src_j = package_dir / "character" / "canonical_character_source.json"
                if src_j.is_file():
                    try:
                        docj = json.loads(src_j.read_text(encoding="utf-8"))
                        docj["source_type"] = "character_art_after_forced_sheet"
                        docj["forced_character_sheet_on_character_art"] = True
                        CanonicalCharacterManager.write_source_metadata(package_dir, docj)
                    except (OSError, json.JSONDecodeError, TypeError):
                        pass
            print(json.dumps({"make_character_sheet": True, "log": log}, ensure_ascii=False, indent=2))
            return 0

        stylizer_backend = str(args.stylizer).strip().lower()
        styled_mock_path = character_dir / "standardized_character_mock.png"
        styled_openai_path = character_dir / "standardized_character.png"
        standardized_relative_out: str | None = None
        style_log: dict[str, object] = {"backend": stylizer_backend, "phases": []}

        try:
            if stylizer_backend == "mock":
                create_stylizer("mock").standardize(
                    stylizer_input, styled_mock_path, profile
                )
                standardized_relative_out = "character/standardized_character_mock.png"
            elif stylizer_backend == "openai":
                stz = create_stylizer(
                    "openai",
                    openai_model=args.openai_model,
                    openai_size=args.image_size,
                )
                stz.standardize(stylizer_input, styled_openai_path, profile)
                standardized_relative_out = "character/standardized_character.png"
                phases = getattr(stz, "_last_phases", None)
                if isinstance(phases, list):
                    style_log["phases"] = phases
        except (NotImplementedError, RuntimeError) as exc:
            print(f"[오류] stylizer ({stylizer_backend}): {exc}", file=sys.stderr)
            return 5

        style_log["reference_classification"] = ref_class.model_dump()

        (meta_dir / "style_log.json").write_text(
            json.dumps(style_log, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        style_txt = meta_dir / "style_prompt.txt"
        style_txt.write_text(
            style_prompt_document(profile, stylizer_backend),
            encoding="utf-8",
        )

        if stylizer_backend == "openai" and styled_openai_path.is_file():
            generation_reference_path = styled_openai_path
            canonical_reference_used = "character/standardized_character.png"
            canonical_reference_policy = (
                "실험 옵션(--stylizer openai): OpenAI 표준 캐릭터(standardized_character.png)가 "
                "이미지 생성·일관성 검사의 시각적 기준입니다. 원본 대비 캐릭터 드리프트가 생길 수 있습니다."
            )
            reference_priority = "openai_standardized_character"
            stylizer_used_for_generation = True
        elif stylizer_backend == "mock" and styled_mock_path.is_file():
            generation_reference_path = styled_mock_path
            canonical_reference_used = "character/standardized_character_mock.png"
            canonical_reference_policy = (
                "개발 테스트(--stylizer mock): 목업 표준 이미지가 생성 기준입니다. "
                "실제 납품·품질·정체성 판단에 사용하지 마세요."
            )
            reference_priority = "mock_standardized_character"
            stylizer_used_for_generation = True
        elif stylizer_backend == "openai" and not styled_openai_path.is_file():
            generation_reference_path = (
                packaged_original_ref
                if packaged_original_ref.is_file()
                else Path(character_path).resolve()
            )
            canonical_reference_used = (
                "character/reference.png"
                if packaged_original_ref.is_file()
                else str(Path(character_path).name)
            )
            canonical_reference_policy = (
                "경고: --stylizer openai 옵션이었으나 standardized_character.png 가 없어 "
                "원본 실사(reference)를 생성 기준으로 폴백했습니다."
            )
            reference_priority = "original_reference_photo_fallback_from_failed_openai_stylizer"
            stylizer_used_for_generation = False
        else:
            generation_reference_path = (
                packaged_original_ref
                if packaged_original_ref.is_file()
                else Path(character_path).resolve()
            )
            canonical_reference_used = (
                "character/reference.png"
                if packaged_original_ref.is_file()
                else "input_character"
            )
            canonical_reference_policy = (
                "실무 기본(--stylizer none): 패키지 내 원본 실사(character/reference.png)와 "
                "PetProfile 텍스트를 우선합니다. standardized_character.png 는 이 실행에서 "
                "이미지 생성 기준으로 사용하지 않습니다."
            )
            reference_priority = "original_reference_photo"
            stylizer_used_for_generation = False

        canonical_reference_policy = _merge_canonical_policy_with_reference_type(
            canonical_reference_policy,
            reference_priority=reference_priority,
            stylizer_backend=stylizer_backend,
            ref_class=ref_class,
        )

        mgr = CanonicalCharacterManager()

        if bool(getattr(args, "make_candidates", False)):
            cand_dir = package_dir / "character_candidates"
            cand_dir.mkdir(parents=True, exist_ok=True)
            cand_n = max(1, min(8, int(getattr(args, "candidate_count", 3) or 3)))
            try:
                id_src, used_sh, src_label = _resolve_candidate_identity_source(package_dir, args)
            except FileNotFoundError as fnf:
                print(f"[오류] {fnf}", file=sys.stderr)
                return 2
            try:
                cgen = create_character_candidate_generator(
                    args.generator,
                    openai_model=str(
                        getattr(args, "candidate_openai_model", None) or "gpt-image-1"
                    ).strip(),
                    openai_mode=str(getattr(args, "candidate_openai_mode", "auto")).strip().lower(),
                    openai_size=str(args.image_size),
                    openai_retries=max(1, min(5, int(args.max_retries))),
                )
                res = cgen.generate(
                    original_photo_path=Path(id_src),
                    series_name=series_name,
                    species_hint=str(args.species_hint).strip() if args.species_hint else "",
                    personality_hint=str(args.personality_hint or ""),
                    count=cand_n,
                    output_dir=cand_dir,
                    used_character_sheet=used_sh,
                    source_reference=src_label,
                    art_style=art_style,
                )
            except OpenAIMissingKeyError as mk:
                print(str(mk), file=sys.stderr)
                return 7
            # 자동감지 결과를 args에 반영 → 이후 파이프라인(감정 컷)에서도 동일 species 사용
            if res.detected_species and not (args.species_hint or "").strip():
                args.species_hint = res.detected_species
                print(f"[자동감지] 이후 파이프라인에 species_hint={res.detected_species} 적용", file=sys.stderr)
            summary = {
                "make_candidates": True,
                "purpose": "base_character_candidates",
                "success": res.success,
                "paths": [str(p.resolve()) for p in res.paths],
                "manifest": str(res.manifest_path.resolve()) if res.manifest_path else None,
                "errors": res.errors,
                "used_character_sheet": used_sh,
                "source_reference": src_label,
                "used_image_reference": res.used_image_reference,
                "text_only_fallback": res.text_only_fallback,
                "drift_risk_warning": res.drift_risk_warning,
                "fallback_warning": res.fallback_warning,
                "detected_species": res.detected_species or None,
                "next_step": "3장 중 1장을 --select-candidate N 으로 canonical_character.png 에 고정하세요.",
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            print("[보존 정책]")
            print(
                f"- candidates preserved: "
                f"{str(preservation_policy.get('candidates_preserved', True)).lower()}"
            )
            print(
                f"- canonical preserved: "
                f"{str(preservation_policy.get('canonical_preserved', True)).lower()}"
            )
            if res.fallback_warning:
                print(res.fallback_warning, file=sys.stderr)
            for ent in res.entries:
                if ent.get("success"):
                    print(
                        f"  후보 {ent.get('index')}: {ent.get('path')} "
                        f"| 이미지참조={ent.get('used_image_reference')} "
                        f"| 폴백={ent.get('text_only_fallback')} "
                        f"| drift경고={ent.get('drift_risk_warning')}"
                    )
            if not res.success:
                return 6
            return 0

        if (
            ref_class.reference_type == "character_art"
            and stylizer_backend == "none"
            and packaged_original_ref.is_file()
            and mgr.get_canonical_path(package_dir) is None
        ):
            mgr.set_from_existing_image(
                packaged_original_ref,
                package_dir,
                "package_character_art_reference",
                {"original_reference": "character/reference.png"},
            )

        sc_arg = getattr(args, "select_candidate", None)
        if sc_arg is not None:
            sel = int(sc_arg)
            cand_path = package_dir / "character_candidates" / f"candidate_{sel:02d}.png"
            if not cand_path.is_file():
                print(
                    f"[오류] 후보 이미지가 없습니다: {cand_path}\n"
                    "       --make-candidates 로 후보를 만든 뒤 --select-candidate 를 실행하세요.\n"
                    "       이미 character/canonical_character.png 가 있다면 "
                    "--select-candidate 없이 컷 생성만 실행하면 됩니다.",
                    file=sys.stderr,
                )
                return 2
            mgr.set_from_existing_image(
                cand_path,
                package_dir,
                SELECTED_BASE_CANDIDATE_TYPE,
                {
                    "original_reference": str(cand_path.resolve()),
                    "candidate_index": sel,
                    "policy": CANONICAL_BASE_POLICY_KO,
                },
            )
            cand_n_fb = max(1, min(8, int(getattr(args, "candidate_count", 3) or 3)))
            manp = package_dir / "character_candidates" / "candidates.json"
            if manp.is_file():
                try:
                    cdoc = json.loads(manp.read_text(encoding="utf-8"))
                    cand_n_fb = max(cand_n_fb, int(cdoc.get("count") or cand_n_fb))
                except (OSError, json.JSONDecodeError, ValueError, TypeError):
                    pass
                write_candidate_feedback(
                    package_dir,
                    selected_candidate=sel,
                    candidate_count=cand_n_fb,
                    source_reference=str(cand_path.resolve()),
                    canonical_sheet_used=_package_sheet_path(package_dir).is_file(),
                )

        cc_arg = getattr(args, "canonical_character", None)
        if cc_arg:
            cpp = Path(cc_arg)
            if not cpp.is_file():
                print(f"[오류] --canonical-character 파일을 찾을 수 없습니다: {cpp}", file=sys.stderr)
                return 2
            mgr.set_from_existing_image(
                cpp,
                package_dir,
                "cli_canonical_character_path",
                {"original_reference": str(cpp.resolve())},
            )

        canon_abs = mgr.get_canonical_path(package_dir)
        canonical_character_used_for_pkg = bool(canon_abs)
        canonical_character_path_for_pkg = (
            "character/canonical_character.png" if canon_abs else None
        )
        canonical_character_policy_for_pkg = None

        generation_reference_kind = "reference"
        canonical_sheet_mode = False
        canonical_sheet_used_for_pkg = False
        canonical_sheet_path_for_pkg = None
        canonical_sheet_policy_for_pkg = None

        if stylizer_used_for_generation:
            generation_reference_kind = "reference"
        elif stylizer_backend == "none":
            resolved_ref = _resolve_stylizer_none_generation_reference(
                package_dir,
                packaged_original_ref,
                character_path,
                args,
                had_canonical_cli=had_canonical_cli,
                had_sheet_cli=had_sheet_cli,
                require_canonical=not bool(getattr(args, "make_candidates", False)),
            )
            if resolved_ref is None:
                return 2
            gen_p, gen_kind = resolved_ref
            generation_reference_path = gen_p
            generation_reference_kind = gen_kind
            if gen_kind == "canonical_character":
                canonical_character_policy_for_pkg = (
                    "Canonical character image is fixed as the sole visual identity for sticker generation."
                )
                canonical_reference_used = "character/canonical_character.png"
                canonical_reference_policy = (
                    f"{canonical_character_policy_for_pkg} {canonical_reference_policy}"
                ).strip()
            elif gen_kind == "canonical_sheet":
                canonical_sheet_used_for_pkg = True
                canonical_sheet_path_for_pkg = "character/canonical_sheet.png"
                canonical_sheet_policy_for_pkg = (
                    "Canonical character sheet is the design bible for all emoticon cuts."
                )
                canonical_sheet_mode = True
                canonical_reference_used = "character/canonical_sheet.png"
                canonical_reference_policy = (
                    f"{canonical_sheet_policy_for_pkg} {canonical_reference_policy}"
                ).strip()
        else:
            generation_reference_kind = "reference"

        canon_ref = mgr.get_canonical_path(package_dir)
        canonical_identity_mode = bool(
            stylizer_backend == "none"
            and (
                canonical_sheet_mode
                or (
                    canon_ref
                    and generation_reference_kind == "canonical_character"
                    and generation_reference_path.resolve() == canon_ref.resolve()
                )
            )
        )

        cad_direct, _cad_forced_meta, _cad_pol_meta = _read_character_art_direct_meta(package_dir)
        cad_for_prompt = bool(cad_direct and canonical_identity_mode and not canonical_sheet_mode)

        if bool(getattr(args, "require_character_sheet", False)):
            rt_req = str(ref_class.reference_type).strip().lower()
            sheet_req = _package_sheet_path(package_dir)
            if rt_req == "photo" and not sheet_req.is_file():
                print(
                    "[오류] --require-character-sheet: 실사 입력에는 "
                    "character/canonical_sheet.png 가 필요합니다. "
                    "먼저 --make-character-sheet 를 실행하세요.",
                    file=sys.stderr,
                )
                return 2

        visual_anchor_note = (args.reference_note or "").strip()
        if not visual_anchor_note:
            if canonical_sheet_mode:
                visual_anchor_note = (
                    "Primary visual anchor: character/canonical_sheet.png — canonical turnaround sheet; "
                    "every cut must match the same character identity from the sheet."
                )
            elif canonical_identity_mode and cad_for_prompt:
                visual_anchor_note = (
                    "Primary visual anchor: character/canonical_character.png — finished character art "
                    "(direct canonical; AI sheet generation skipped); match this image exactly across cuts "
                    "(pose, action, props, and emotion may change)."
                )
            elif canonical_identity_mode:
                visual_anchor_note = (
                    "Primary visual anchor: character/canonical_character.png — fixed sticker identity; "
                    "match this image exactly across cuts (pose, action, props, and emotion may change)."
                )
            else:
                visual_anchor_note = _visual_anchor_reference_note(stylizer_backend)

        no_ai_text = not bool(getattr(args, "ai_text", False))
        no_text_overlay = bool(getattr(args, "no_text_overlay", False))
        effective_postprocess = bool(args.postprocess) and not no_ai_text
        if bool(args.postprocess) and no_ai_text:
            print(
                "[경고] 기본(한글 비AI) 모드에서는 --postprocess 를 적용하지 않습니다.",
                file=sys.stderr,
            )

        ct_path = getattr(args, "cut_templates", None)
        planner = ConceptPlanner(
            templates_path=Path(ct_path) if ct_path and Path(ct_path).is_file() else None
        )
        items = planner.plan(
            theme=theme,
            series_name=series_name,
            entity_type=getattr(identity_profile, "entity_type", "") or "",
        )
        items_by_id: dict[str, dict[str, object]] = {
            str(it["id"]).strip().zfill(2): it for it in items
        }

        if partial_generation and selected_cut_ids is not None:
            missing = [cid for cid in selected_cut_ids if cid not in items_by_id]
            if missing:
                print(
                    f"[오류] --test-ids 에 템플릿에 없는 컷이 있습니다: {', '.join(missing)}",
                    file=sys.stderr,
                )
                return 2
            items_for_plan = [items_by_id[cid] for cid in selected_cut_ids]
        else:
            items_for_plan = list(items)

        rep_item_id = (
            sorted(selected_cut_ids, key=lambda x: int(x))[0]
            if partial_generation and selected_cut_ids
            else "01"
        )

        cut_plan_path = package_dir / "meta" / "cut_plan.json"
        cut_plan_path.write_text(
            json.dumps(
                ConceptPlanner.cut_plan_document(theme, series_name, items_for_plan),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        png_dir = package_dir / "png"
        png_raw_dir = package_dir / "png_raw"
        processed_dir = package_dir / "processed"
        generated_raw_dir = package_dir / "generated_raw"
        png_no_text_dir = package_dir / "png_no_text"
        generated_raw_dir.mkdir(parents=True, exist_ok=True)
        png_no_text_dir.mkdir(parents=True, exist_ok=True)

        if no_ai_text:
            raw_out_dir = generated_raw_dir
            emoticon_subdir = "png"
            sticker_dir = png_dir
        else:
            raw_out_dir = png_raw_dir if effective_postprocess else png_dir
            emoticon_subdir = _package_emoticon_subdir(
                effective_postprocess, args.use_processed_for_package
            )
            sticker_dir = package_dir / emoticon_subdir
        if effective_postprocess:
            png_raw_dir.mkdir(parents=True, exist_ok=True)
            processed_dir.mkdir(parents=True, exist_ok=True)

        icon_dir = package_dir / "icon"
        share_dir = package_dir / "share"
        failed_dir = package_dir / "failed"
        failed_dir.mkdir(parents=True, exist_ok=True)

        char_paths = ref_result.get("paths") or {}

        prompt_builder = PromptBuilder()
        cut_payloads: list[dict[str, object]] = []
        for item in items_for_plan:
            ptxt = prompt_builder.build_prompt(
                item,
                theme=theme,
                series_name=series_name,
                profile=profile,
                reference_description=visual_anchor_note,
                no_ai_text=no_ai_text,
                reference_type=ref_class.reference_type,
                canonical_identity_mode=canonical_identity_mode,
                canonical_sheet_mode=canonical_sheet_mode,
                character_art_direct_canonical=cad_for_prompt,
                series_pack_coherence=True,
                style_intensity=style_si,
                identity_profile=identity_profile,
                pose_variation_strength=pose_si,
                expression_strength=expr_si,
                force_identity_lock=bool(canon_ref or canonical_sheet_mode),
                art_style=art_style,
            )
            cut_payloads.append({"item": item, "prompt": str(ptxt)})

        prompts_records: list[dict] = []
        for row in cut_payloads:
            it = dict(row)["item"]
            assert isinstance(it, dict)
            pr = dict(row)["prompt"]
            assert isinstance(pr, str)
            cut_id_s = str(it["id"])
            prompts_records.append(
                {
                    "id": cut_id_s,
                    "text": str(it.get("text", "")),
                    "emotion": str(it.get("emotion", "")),
                    "facial_expression": str(it.get("facial_expression", "")),
                    "body_pose": str(it.get("body_pose", "")),
                    "prop": str(it.get("prop", "")),
                    "action": str(it.get("action", "")),
                    "motion_hint": str(it.get("motion_hint", "")),
                    "layout_type": str(it.get("layout_type", "")),
                    "text_position": str(it.get("text_position", "")),
                    "importance": str(it.get("importance", "")),
                    "risk_notes": str(it.get("risk_notes", "")),
                    "prompt": pr,
                }
            )
        (meta_dir / "prompts.json").write_text(
            json.dumps(
                {"no_ai_text": no_ai_text, "cuts": prompts_records},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        if args.generator == "openai" and not (os.environ.get("OPENAI_API_KEY") or "").strip():
            print(
                "[오류] --generator openai 는 OPENAI_API_KEY 가 필요합니다.\n"
                "       · 프로젝트 루트(`KakaoEmoticonFactory/`)에 `.env`를 두고 키를 넣으세요(.env.example 참고).\n"
                "       · 또는 시스템 환경 변수 `OPENAI_API_KEY` 를 설정하세요.\n"
                "       · API 없이 로컬에서 끝까지 돌리려면 `--generator mock` 또는 `--full-pipeline` 을 사용하세요.",
                file=sys.stderr,
            )
            return 7

        generator = create_image_generator(
            args.generator,
            openai_model=args.openai_model,
            openai_size=args.image_size,
            openai_retries=args.max_retries,
            openai_mode=args.openai_mode,
            no_ai_text=no_ai_text,
        )
        if args.generator == "openai":
            _warn_cut_generation_reference(
                package_dir,
                generation_reference_kind=generation_reference_kind,
                generation_reference_path=generation_reference_path,
            )
        processor = ImageProcessor()

        pipeline_t0 = time.perf_counter()
        generation_started = datetime.now(timezone.utc).isoformat()
        generation_log: dict[str, object] = {
            "generator": args.generator,
            "generator_backend": args.generator,
            "openai_model": args.openai_model if args.generator == "openai" else None,
            "openai_request_size": args.image_size if args.generator == "openai" else None,
            "openai_mode": args.openai_mode if args.generator == "openai" else None,
            "max_retries_per_cycle": args.max_retries if args.generator == "openai" else None,
            "continue_on_error": bool(args.continue_on_error),
            "grid_mode": bool(getattr(args, "grid_mode", False)) and args.generator == "openai",
            "test_one": test_one,
            "test_one_cli": bool(test_one_cli),
            "partial_generation": bool(partial_generation),
            "selected_cut_ids": list(selected_cut_ids) if selected_cut_ids else None,
            "no_ai_text": no_ai_text,
            "stylizer_backend": stylizer_backend,
            "pet_profile": pet.model_dump(),
            "reference_image_policy": (
                f"stylizer={stylizer_backend}; priority={reference_priority}; "
                f"file={generation_reference_path.name}"
            ),
            "reference_image_used": str(generation_reference_path.resolve()),
            "reference_priority": reference_priority,
            "stylizer_used_for_generation": stylizer_used_for_generation,
            "reference_type": ref_class.reference_type,
            "style_intensity": style_si,
            "art_style": art_style,
            "pose_variation_strength": pose_si,
            "expression_strength": expr_si,
            "identity_profile_source": IDENTITY_PROFILE_SOURCE,
            "entity_type": identity_profile.entity_type,
            "entity_type_confidence": identity_profile.entity_type_confidence,
            "canonical_character_used": bool(canonical_character_used_for_pkg),
            "canonical_character_path": canonical_character_path_for_pkg,
            "canonical_character_policy": canonical_character_policy_for_pkg,
            "canonical_sheet_used": bool(canonical_sheet_used_for_pkg),
            "canonical_sheet_path": canonical_sheet_path_for_pkg,
            "canonical_sheet_policy": canonical_sheet_policy_for_pkg,
            "generation_reference_kind": generation_reference_kind,
            "reference_type_confidence": ref_class.confidence,
            "packaged_original_reference": (
                str(packaged_original_ref.resolve())
                if packaged_original_ref.is_file()
                else None
            ),
            "started_at_utc": generation_started,
            "postprocess_enabled": effective_postprocess,
            "postprocess_strength": (
                args.postprocess_strength if effective_postprocess else None
            ),
            "use_processed_for_package": (
                bool(args.use_processed_for_package) if effective_postprocess else None
            ),
            "package_sticker_subdir": emoticon_subdir,
            "raw_normalized_dir": str(raw_out_dir.resolve()),
            "generated_raw_dir": str(generated_raw_dir.resolve()) if no_ai_text else None,
            "png_no_text_dir": str(png_no_text_dir.resolve()) if no_ai_text else None,
            "processed_dir": str(processed_dir.resolve()) if effective_postprocess else None,
            "cuts": [],
        }

        meta_paths: list[Path] = []
        package_rows: list[dict] = []
        gen_aborted_exc: BaseException | None = None
        generation_stopped = False
        cuts_log_ref = generation_log["cuts"]
        assert isinstance(cuts_log_ref, list)

        # ── 그리드 모드: API 1회 호출로 16컷 일괄 생성 ──────────────────
        _grid_pre_generated: set[str] = set()
        _grid_enabled = (
            args.generator == "openai"
            and bool(getattr(args, "grid_mode", False))
            and not test_one
            and not partial_generation
            and hasattr(generator, "generate_grid")
        )
        if _grid_enabled:
            print(
                f"[그리드] 4×4 단일 API 호출 시작 ({len(cut_payloads)}컷)…",
                file=sys.stderr,
            )
            _grid_t0 = time.perf_counter()
            try:
                _grid_succeeded, _grid_failed = generator.generate_grid(
                    cut_payloads,
                    raw_out_dir,
                    reference_path=generation_reference_path,
                )
                _grid_wall = round(time.perf_counter() - _grid_t0, 4)
                _grid_pre_generated = set(_grid_succeeded.keys())
                generation_log["grid_call"] = {
                    "mode": "grid",
                    "wall_seconds": _grid_wall,
                    "succeeded_cut_ids": list(_grid_succeeded.keys()),
                    "failed_cut_ids": _grid_failed,
                    "attempt_logs": [
                        dict(x)
                        for x in getattr(generator, "last_attempt_logs", []) or []
                    ],
                }
                print(
                    f"[그리드] 완료: {len(_grid_succeeded)}성공, {len(_grid_failed)}실패 "
                    f"({_grid_wall}s). 실패 컷은 개별 fallback.",
                    file=sys.stderr,
                )
            except Exception as _grid_exc:
                _grid_wall = round(time.perf_counter() - _grid_t0, 4)
                generation_log["grid_call"] = {
                    "mode": "grid",
                    "wall_seconds": _grid_wall,
                    "error": repr(_grid_exc),
                }
                print(
                    f"[그리드] 전체 실패: {_grid_exc!r} — 개별 생성 모드로 폴백",
                    file=sys.stderr,
                )
                _grid_enabled = False

        try:
            for row in cut_payloads:
                item = dict(row)["item"]
                assert isinstance(item, dict)
                prompt = dict(row)["prompt"]
                assert isinstance(prompt, str)
                cut_id = str(item["id"])
                text = str(item["text"])
                raw_png = raw_out_dir / f"{cut_id}.png"

                gen_t0 = time.perf_counter()
                attempts_snapshot: list[dict] = []
                try:
                    # 그리드 모드: 이미 크롭된 raw_png가 있으면 API 호출 생략
                    _use_grid_cell = (
                        _grid_enabled
                        and cut_id in _grid_pre_generated
                        and raw_png.exists()
                    )
                    if _use_grid_cell:
                        print(
                            f"[그리드] 컷 {cut_id}: 그리드 셀 재사용 (API 호출 생략)",
                            file=sys.stderr,
                        )
                        wall_s = 0.0
                        attempts_snapshot = []
                    else:
                        item_run = {**item, "_no_ai_text": no_ai_text}
                        generator.generate(
                            prompt,
                            raw_png,
                            text=text,
                            item_id=cut_id,
                            reference_path=generation_reference_path,
                            item=item_run,
                        )
                        wall_s = round(time.perf_counter() - gen_t0, 4)
                        attempts_snapshot = [
                            dict(x) for x in getattr(generator, "last_attempt_logs", []) or []
                        ]
                    if no_ai_text:
                        nt = png_no_text_dir / f"{cut_id}.png"
                        processor.normalize_emoticon_to(raw_png, nt)
                        out_final = sticker_dir / f"{cut_id}.png"
                        tpos = str(item.get("text_position", "bottom"))
                        overlay_text = "" if no_text_overlay else text
                        processor.add_text_overlay(nt, out_final, overlay_text, tpos)
                    else:
                        processor.normalize_emoticon(raw_png)

                    prow = {
                        **{k: v for k, v in item.items() if not str(k).startswith("_")},
                        "png": f"{emoticon_subdir}/{cut_id}.png",
                        "icon": f"icon/{cut_id}.png",
                        "prompt": prompt,
                    }
                    package_rows.append(prow)
                    meta_paths.append(sticker_dir / f"{cut_id}.png")
                    cuts_log_ref.append(
                        {
                            "id": cut_id,
                            "success": True,
                            "wall_seconds": wall_s,
                            "prompt": prompt,
                            "attempt_logs": attempts_snapshot,
                        }
                    )
                except OpenAIMissingKeyError as missing:
                    gen_aborted_exc = missing
                    wall_s = round(time.perf_counter() - gen_t0, 4)
                    attempts_snapshot = [
                        dict(x)
                        for x in getattr(generator, "last_attempt_logs", []) or []
                    ]
                    cuts_log_ref.append(
                        {
                            "id": cut_id,
                            "success": False,
                            "wall_seconds": wall_s,
                            "prompt": prompt,
                            "error": repr(missing),
                            "attempt_logs": attempts_snapshot,
                        }
                    )
                    print(f"[오류] {missing}", file=sys.stderr)
                    generation_stopped = True
                    break
                except Exception as exc:
                    wall_s = round(time.perf_counter() - gen_t0, 4)
                    attempts_snapshot = [
                        dict(x) for x in getattr(generator, "last_attempt_logs", []) or []
                    ]
                    tb = traceback.format_exc()
                    if raw_png.exists():
                        try:
                            raw_png.unlink()
                        except OSError:
                            pass

                    err_payload = {
                        "id": cut_id,
                        "error": repr(exc),
                        "traceback": tb,
                        "wall_seconds": wall_s,
                        "attempt_logs": attempts_snapshot,
                        "prompt_excerpt": prompt[:500],
                    }
                    (failed_dir / f"{cut_id}_error.json").write_text(
                        json.dumps(err_payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    print(
                        f"[실패] 컷 {cut_id} 이미지 생성 실패 → failed/{cut_id}_error.json\n{tb}",
                        file=sys.stderr,
                    )

                    cuts_log_ref.append(
                        {
                            "id": cut_id,
                            "success": False,
                            "wall_seconds": wall_s,
                            "prompt": prompt,
                            "error": repr(exc),
                            "attempt_logs": attempts_snapshot,
                        }
                    )

                    if not args.continue_on_error:
                        gen_aborted_exc = exc
                        generation_stopped = True
                        break

        finally:
            generation_log["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
            generation_log["total_pipeline_wall_seconds"] = round(
                time.perf_counter() - pipeline_t0, 4
            )
            (meta_dir / "generation_log.json").write_text(
                json.dumps(generation_log, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        if not generation_stopped and package_rows:
            _humanize_after_generate(
                effective_postprocess,
                strength=args.postprocess_strength,
                raw_out_dir=raw_out_dir,
                processed_dir=processed_dir,
            )
            _rebuild_icons_after_sticker_touch(package_rows, sticker_dir, icon_dir, processor)

        if generation_stopped:
            qc = QualityChecker()
            partial = qc.check_big_emoticon_package(
                package_dir,
                emoticon_subdir=emoticon_subdir,
                expected_cut_ids=qc_expected_ids,
            )
            print(json.dumps(partial, ensure_ascii=False, indent=2))
            if isinstance(gen_aborted_exc, OpenAIMissingKeyError):
                return 7
            print(
                f"[오류] 생성 중단: {gen_aborted_exc}",
                file=sys.stderr,
            )
            return 8

        c_checker: CharacterConsistencyChecker | None = None
        if effective_check_consistency or effective_auto_regenerate:
            c_checker = CharacterConsistencyChecker(
                threshold=args.consistency_threshold,
                drift_threshold=float(getattr(args, "drift_threshold", 0.68)),
                strict_drift=bool(getattr(args, "strict_drift", False)),
            )

        consistency_report: dict[str, object] | None = None
        waves_left = max(0, int(args.max_regenerate_attempts))
        regeneration_log_body: dict[str, object] = {
            "generator": args.generator,
            "test_one": test_one,
            "partial_generation": bool(partial_generation),
            "selected_cut_ids": list(selected_cut_ids) if selected_cut_ids else None,
            "auto_regenerate": bool(effective_auto_regenerate),
            "max_regenerate_attempts": args.max_regenerate_attempts,
            "waves_budget": args.max_regenerate_attempts,
            "waves_remaining_after_run": args.max_regenerate_attempts,
            "consistency_phase": None,
            "quality_phase": None,
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        def write_prompts_json() -> None:
            (meta_dir / "prompts.json").write_text(
                json.dumps(
                    {"no_ai_text": no_ai_text, "cuts": prompts_records},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        regeneration_ctx = RegenerationContext(
            png_dir=generated_raw_dir if no_ai_text else raw_out_dir,
            icon_dir=icon_dir,
            meta_dir=meta_dir,
            canonical_character_ref=generation_reference_path,
            theme=theme,
            series_name=series_name,
            profile=profile,
            reference_note=visual_anchor_note,
            no_ai_text=no_ai_text,
            text_pipeline=no_ai_text,
            png_no_text_dir=png_no_text_dir if no_ai_text else None,
            final_sticker_dir=sticker_dir if no_ai_text else None,
            reference_type=ref_class.reference_type,
            canonical_identity_mode=canonical_identity_mode,
            canonical_sheet_mode=canonical_sheet_mode,
            character_art_direct_canonical=cad_for_prompt,
            series_pack_coherence=True,
            style_intensity=style_si,
            pose_variation_strength=pose_si,
            expression_strength=expr_si,
        )

        if partial_generation and selected_cut_ids:
            expected_png_paths = [
                sticker_dir / f"{cid}.png" for cid in sorted(selected_cut_ids, key=int)
            ]
        else:
            expected_png_paths = [sticker_dir / f"{i:02d}.png" for i in range(1, 17)]

        if effective_check_consistency and c_checker is not None:
            consistency_report = c_checker.check(
                generation_reference_path, expected_png_paths, profile
            )
            fc_dir = package_dir / "failed_consistency"
            fc_dir.mkdir(parents=True, exist_ok=True)
            copy_failed_consistency(package_dir, consistency_report)
            (meta_dir / "consistency_report.json").write_text(
                json.dumps(consistency_report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            fails = consistency_report.get("failed") or []
            cons_res: dict | None = None
            if fails and effective_auto_regenerate and waves_left > 0:
                mgr = RegenerationManager(args.generator)
                try:
                    cons_res = mgr.regenerate_failed_items(
                        regeneration_ctx,
                        fails,
                        items_by_id,
                        generator=generator,
                        prompt_builder=prompt_builder,
                        processor=processor,
                        checker=c_checker,
                        max_attempts=waves_left,
                        failure_source="consistency",
                        prompts_records=prompts_records,
                        package_rows=package_rows,
                        prompts_json_writer=write_prompts_json,
                    )
                except OpenAIMissingKeyError as mk:
                    print(f"[오류] 재생성 중 {mk}", file=sys.stderr)
                    return 7

                if cons_res is not None:
                    regeneration_log_body["consistency_phase"] = _summarize_regeneration_phase(
                        cons_res
                    )
                    waves_left -= int(cons_res.get("batches_used") or 0)
                    consistency_report = cons_res["final_consistency_report"]
                    (meta_dir / "consistency_report.json").write_text(
                        json.dumps(consistency_report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    fc_dir.mkdir(parents=True, exist_ok=True)
                    copy_failed_consistency(package_dir, consistency_report)

                    if effective_postprocess:
                        _humanize_after_generate(
                            True,
                            strength=args.postprocess_strength,
                            raw_out_dir=raw_out_dir,
                            processed_dir=processed_dir,
                        )
                    _rebuild_icons_after_sticker_touch(
                        package_rows, sticker_dir, icon_dir, processor
                    )
            elif fails and effective_auto_regenerate:
                regeneration_log_body["consistency_phase"] = {
                    "skipped": True,
                    "reason": "no_regenerate_waves_remaining",
                    "failed_count": len(fails),
                }
            elif effective_auto_regenerate and not fails:
                regeneration_log_body["consistency_phase"] = {
                    "skipped": True,
                    "reason": "no_consistency_failures",
                }

            assert consistency_report is not None
            _print_consistency_report_block(consistency_report, args.consistency_threshold)

        share_sources = _share_sticker_sources(package_rows, sticker_dir)
        processor.create_share_image(series_name, share_sources, share_dir / "share.png")

        ref_dest = meta_dir / "reference.png"
        try:
            from PIL import Image as _PILImage
            _PILImage.open(Path(character_path)).convert("RGBA").save(ref_dest, format="PNG")
        except Exception:
            shutil.copy2(character_path, ref_dest)

        animated_for_package: list[dict[str, object]] | None = None
        if effective_make_webp:
            from services.webp_animator import build_default_webp_pack

            wcount = max(1, min(4, int(args.webp_count)))
            webp_dir = package_dir / "webp"
            webp_report_doc = build_default_webp_pack(
                items_by_id=items_by_id,
                sticker_dir=sticker_dir,
                webp_dir=webp_dir,
                webp_count=wcount,
                loops=4,
                quality=max(30, min(100, int(args.webp_quality))),
            )
            webp_report_doc["note"] = (
                "프로토타입 WebP. 카카오 제출 전 전용 WebPAnimator/공식 가이드로 "
                "최종 변환·검수하는 것을 권장합니다."
            )
            webp_report_doc["created_at_utc"] = datetime.now(timezone.utc).isoformat()
            (meta_dir / "webp_report.json").write_text(
                json.dumps(webp_report_doc, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            ok_rows = [
                r
                for r in webp_report_doc.get("items", [])
                if isinstance(r, dict) and r.get("ok") and r.get("relative_path")
            ]
            if ok_rows:
                animated_for_package = [
                    {
                        "id": r["id"],
                        "text": r.get("text", ""),
                        "webp": str(r["relative_path"]),
                        "animation": str(r.get("animation", "")),
                        "loops": 4,
                        "frame_count": int(r.get("frame_count") or 0),
                        "bytes": int(r.get("bytes") or 0),
                    }
                    for r in ok_rows
                ]

        std_rel = standardized_relative_out
        _cad_pi, _forced_pi, _pol_pi = _read_character_art_direct_meta(package_dir)
        pkg.write_package_info(
            package_dir,
            series_name=series_name,
            theme=theme,
            items=package_rows,
            representative_item_id=rep_item_id,
            reference_relative="meta/reference.png",
            character_base_relative=char_paths.get("character_base"),
            character_base_white_relative=char_paths.get("character_base_white"),
            standardized_character_relative=std_rel,
            character_profile=profile.model_dump(),
            pet_profile=pet.model_dump(),
            animated_items=animated_for_package,
            test_mode=partial_generation,
            generated_count=len(package_rows),
            selected_cut_ids=list(selected_cut_ids)
            if partial_generation and selected_cut_ids
            else None,
            no_ai_text=no_ai_text,
            text_overlay_applied=no_ai_text,
            stylizer_backend=stylizer_backend,
            generator_backend=args.generator,
            canonical_reference_used=canonical_reference_used,
            canonical_reference_policy=canonical_reference_policy,
            pet_profile_source=PET_PROFILE_SOURCE,
            reference_type=ref_class.reference_type,
            reference_type_confidence=ref_class.confidence,
            reference_type_reasons=list(ref_class.reasons),
            reference_classifier_metrics=dict(ref_class.metrics),
            canonical_character_used=bool(canonical_character_used_for_pkg),
            canonical_character_path=canonical_character_path_for_pkg,
            canonical_character_policy=canonical_character_policy_for_pkg,
            canonical_sheet_used=bool(canonical_sheet_used_for_pkg),
            canonical_sheet_path=canonical_sheet_path_for_pkg,
            canonical_sheet_policy=canonical_sheet_policy_for_pkg,
            character_art_direct_canonical=(True if _cad_pi else None),
            forced_character_sheet_on_character_art=(True if _forced_pi else None),
            policy=(_pol_pi if _cad_pi else None),
            style_intensity=style_si,
        )

        qc = QualityChecker()
        qc_report = qc.check_big_emoticon_package(
            package_dir,
            emoticon_subdir=emoticon_subdir,
            expected_cut_ids=qc_expected_ids,
        )

        png_cut_err = qc_report.get("per_cut_png_errors") or {}
        icon_cut_err = qc_report.get("per_cut_icon_errors") or {}
        qc_fail_cut_ids = sorted(set(png_cut_err) | set(icon_cut_err))

        qc_regen_result: dict | None = None
        if (
            effective_auto_regenerate
            and waves_left > 0
            and c_checker is not None
            and qc_fail_cut_ids
        ):
            fail_quality_payload = []
            for cid in qc_fail_cut_ids:
                issues = list(png_cut_err.get(cid, [])) + list(icon_cut_err.get(cid, []))
                fail_quality_payload.append({"id": cid, "issues": issues})

            mgr_q = RegenerationManager(args.generator)
            try:
                qc_regen_result = mgr_q.regenerate_failed_items(
                    regeneration_ctx,
                    fail_quality_payload,
                    items_by_id,
                    generator=generator,
                    prompt_builder=prompt_builder,
                    processor=processor,
                    checker=c_checker,
                    max_attempts=waves_left,
                    failure_source="quality",
                    prompts_records=prompts_records,
                    package_rows=package_rows,
                    prompts_json_writer=write_prompts_json,
                )
            except OpenAIMissingKeyError as mk:
                print(f"[오류] 품질 재생성 중 {mk}", file=sys.stderr)
                return 7

            regeneration_log_body["quality_phase"] = _summarize_regeneration_phase(
                qc_regen_result
            )
            waves_left -= int(qc_regen_result.get("batches_used") or 0)
            fc_dir_refresh = package_dir / "failed_consistency"
            fc_dir_refresh.mkdir(parents=True, exist_ok=True)
            consistency_report = qc_regen_result["final_consistency_report"]
            (meta_dir / "consistency_report.json").write_text(
                json.dumps(consistency_report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            copy_failed_consistency(package_dir, consistency_report)

            if effective_postprocess:
                _humanize_after_generate(
                    True,
                    strength=args.postprocess_strength,
                    raw_out_dir=raw_out_dir,
                    processed_dir=processed_dir,
                )
            _rebuild_icons_after_sticker_touch(package_rows, sticker_dir, icon_dir, processor)

            share_sources = _share_sticker_sources(package_rows, sticker_dir)
            processor.create_share_image(series_name, share_sources, share_dir / "share.png")
            _cad_pi2, _forced_pi2, _pol_pi2 = _read_character_art_direct_meta(package_dir)
            pkg.write_package_info(
                package_dir,
                series_name=series_name,
                theme=theme,
                items=package_rows,
                representative_item_id=rep_item_id,
                reference_relative="meta/reference.png",
                character_base_relative=char_paths.get("character_base"),
                character_base_white_relative=char_paths.get("character_base_white"),
                standardized_character_relative=std_rel,
                character_profile=profile.model_dump(),
                pet_profile=pet.model_dump(),
                animated_items=animated_for_package,
                test_mode=partial_generation,
                generated_count=len(package_rows),
                selected_cut_ids=list(selected_cut_ids)
                if partial_generation and selected_cut_ids
                else None,
                no_ai_text=no_ai_text,
                text_overlay_applied=no_ai_text,
                stylizer_backend=stylizer_backend,
                generator_backend=args.generator,
                canonical_reference_used=canonical_reference_used,
                canonical_reference_policy=canonical_reference_policy,
                pet_profile_source=PET_PROFILE_SOURCE,
                reference_type=ref_class.reference_type,
                reference_type_confidence=ref_class.confidence,
                reference_type_reasons=list(ref_class.reasons),
                reference_classifier_metrics=dict(ref_class.metrics),
                canonical_character_used=bool(canonical_character_used_for_pkg),
                canonical_character_path=canonical_character_path_for_pkg,
                canonical_character_policy=canonical_character_policy_for_pkg,
                canonical_sheet_used=bool(canonical_sheet_used_for_pkg),
                canonical_sheet_path=canonical_sheet_path_for_pkg,
                canonical_sheet_policy=canonical_sheet_policy_for_pkg,
                character_art_direct_canonical=(True if _cad_pi2 else None),
                forced_character_sheet_on_character_art=(True if _forced_pi2 else None),
                policy=(_pol_pi2 if _cad_pi2 else None),
                style_intensity=style_si,
            )
            qc_report = qc.check_big_emoticon_package(
                package_dir,
                emoticon_subdir=emoticon_subdir,
                expected_cut_ids=qc_expected_ids,
            )

            print("\n[재생성] 품질 단계 이후 일관성 재평가", file=sys.stderr)
            _print_consistency_report_block(
                consistency_report, args.consistency_threshold
            )
        elif effective_auto_regenerate:
            if not qc_fail_cut_ids:
                regeneration_log_body["quality_phase"] = {
                    "skipped": True,
                    "reason": "no_per_cut_qc_issues",
                    "qc_ok": bool(qc_report.get("ok")),
                }
            elif c_checker is None:
                regeneration_log_body["quality_phase"] = {
                    "skipped": True,
                    "reason": "no_consistency_checker",
                }
            elif waves_left <= 0:
                regeneration_log_body["quality_phase"] = {
                    "skipped": True,
                    "reason": "no_regenerate_waves_remaining_before_quality_phase",
                    "targets": qc_fail_cut_ids,
                }

        if effective_auto_regenerate and not effective_check_consistency:
            if regeneration_log_body.get("consistency_phase") is None:
                regeneration_log_body["consistency_phase"] = {
                    "skipped": True,
                    "reason": "check_consistency_disabled",
                }

        if effective_auto_regenerate:
            regeneration_log_body["waves_remaining_after_run"] = waves_left
        regeneration_log_body["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        if not effective_auto_regenerate:
            regeneration_log_body.setdefault(
                "note",
                "auto_regenerate 미사용 — 재생성 배치 및 regeneration_log 요약은 최소 기록만 포함합니다.",
            )
        (meta_dir / "regeneration_log.json").write_text(
            json.dumps(regeneration_log_body, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        if args.make_preview:
            from services.preview_builder import write_preview_html

            preview_path = write_preview_html(
                package_dir,
                emoticon_subdir=emoticon_subdir,
                qc_report=qc_report,
                consistency_report=consistency_report,
                generation_log=generation_log,
            )
            print(f"[미리보기] {preview_path.resolve()}", file=sys.stderr)

        print(json.dumps(qc_report, ensure_ascii=False, indent=2))

        strict_consistency_blocked = False
        if (
            args.strict_consistency
            and effective_check_consistency
            and consistency_report is not None
            and not bool(consistency_report.get("ok"))
        ):
            strict_consistency_blocked = True

        _print_run_summary(
            package_dir=package_dir,
            raw_out_dir=raw_out_dir,
            processed_dir=processed_dir,
            sticker_dir=sticker_dir,
            webp_dir=package_dir / "webp",
            icon_dir=icon_dir,
            share_png=share_dir / "share.png",
            postprocess=bool(effective_postprocess),
            make_webp=effective_make_webp,
            qc_report=qc_report,
            consistency_report=consistency_report,
            check_consistency_ran=bool(effective_check_consistency),
            regeneration_log_body=regeneration_log_body,
            generation_log=generation_log,
            test_one=test_one,
            logical_emoticon_n=len(package_rows),
            selected_cut_ids=selected_cut_ids,
            preservation_policy=preservation_policy,
        )

        if strict_consistency_blocked:
            print(
                "[오류] --strict-consistency: 캐릭터 일관성 검사에 실패한 컷이 있습니다.",
                file=sys.stderr,
            )
            return 9

        if qc_report["ok"]:
            return 0

        print("[오류] 정적 품질 검사 실패 — 위 요약·JSON errors 항목을 참고하세요.", file=sys.stderr)
        return 1

    except (OSError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[오류] 작업 중 문제가 발생했습니다: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
