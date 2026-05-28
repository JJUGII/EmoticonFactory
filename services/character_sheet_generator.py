"""Generate ``character/canonical_sheet.png`` (turnaround / expression sheet) from a pet photo."""

from __future__ import annotations

import base64
import json
import os
import traceback
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from services.character_profile import CharacterProfile
from services.illustration_style import (
    clamp_style_intensity,
    illustration_texture_fragment,
    sheet_illustration_reference_prompt_fragment,
)
from services.image_generator import OpenAIMissingKeyError

SHEET_FILENAME = "canonical_sheet.png"
LOG_FILENAME = "canonical_sheet_log.json"


class BaseCharacterSheetGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        *,
        photo_path: Path,
        package_dir: Path,
        series_name: str,
        profile: CharacterProfile | None,
        reference_type: str | None = None,
        forced_character_sheet_on_character_art: bool = False,
        style_intensity: float = 0.5,
    ) -> dict[str, Any]:
        """Write ``character/canonical_sheet.png`` and return log payload."""


class MockCharacterSheetGenerator(BaseCharacterSheetGenerator):
    """Pillow composite: 5 labeled regions on white (visual only, no typography)."""

    _PANEL_LABELS = ("front", "three_quarter", "happy", "neutral", "paw")

    def generate(
        self,
        *,
        photo_path: Path,
        package_dir: Path,
        series_name: str,
        profile: CharacterProfile | None,
        reference_type: str | None = None,
        forced_character_sheet_on_character_art: bool = False,
        style_intensity: float = 0.5,
    ) -> dict[str, Any]:
        _ = profile
        si = clamp_style_intensity(style_intensity)
        char_dir = package_dir / "character"
        char_dir.mkdir(parents=True, exist_ok=True)
        out_path = char_dir / SHEET_FILENAME

        base = Image.open(photo_path).convert("RGBA")
        base.thumbnail((420, 420), Image.Resampling.LANCZOS)

        sheet_w, sheet_h = 1200, 720
        canvas = Image.new("RGB", (sheet_w, sheet_h), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        layouts = [
            (40, 40, 360, 360),
            (420, 40, 360, 360),
            (800, 40, 360, 360),
            (230, 380, 360, 360),
            (610, 380, 360, 360),
        ]
        transforms: list[tuple[float, float, float]] = [
            (1.0, 1.0, 0.0),
            (0.95, 1.02, -12.0),
            (1.05, 1.05, 4.0),
            (1.0, 0.98, 0.0),
            (1.08, 0.92, 8.0),
        ]
        for i, (box, tf) in enumerate(zip(layouts, transforms, strict=False)):
            x0, y0, bw, bh = box
            panel = base.copy()
            br, sat, rot = tf
            panel = ImageEnhance.Brightness(panel).enhance(br)
            panel = ImageEnhance.Color(panel).enhance(sat)
            panel = panel.rotate(rot, expand=True, resample=Image.Resampling.BICUBIC)
            panel.thumbnail((bw - 16, bh - 16), Image.Resampling.LANCZOS)
            px = x0 + (bw - panel.width) // 2
            py = y0 + (bh - panel.height) // 2
            if panel.mode == "RGBA":
                canvas.paste(panel, (px, py), panel)
            else:
                canvas.paste(panel, (px, py))
            draw.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=12, outline=(210, 210, 220), width=2)

        if si >= 0.65:
            canvas = canvas.filter(ImageFilter.GaussianBlur(radius=0.6))
            canvas = ImageEnhance.Color(canvas).enhance(1.08)
        elif si <= 0.2:
            canvas = canvas.filter(ImageFilter.SHARPEN)
        else:
            canvas = canvas.filter(ImageFilter.SMOOTH_MORE)
        canvas.save(out_path, format="PNG")

        log: dict[str, Any] = {
            "backend": "mock",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "series_name": series_name,
            "source_photo": str(Path(photo_path).resolve()),
            "output": f"character/{SHEET_FILENAME}",
            "panels": list(self._PANEL_LABELS),
            "note": "Mock sheet: same thumbnail variants; not a real turnaround.",
            "sheet_mock": True,
            "sheet_generation_mode": "mock_composite",
            "sheet_reference_type": str(reference_type or ""),
            "style_intensity": si,
            "character_sheet_generator_backend": "mock",
            "character_sheet_generation_mode": "mock_composite",
            "character_sheet_model": None,
            "used_image_reference": str(Path(photo_path).resolve()),
            "text_only_fallback": False,
            "drift_risk_warning": False,
        }
        if forced_character_sheet_on_character_art:
            log["forced_character_sheet_on_character_art"] = True
        (char_dir / LOG_FILENAME).write_text(
            json.dumps(log, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return log


class OpenAICharacterSheetGenerator(BaseCharacterSheetGenerator):
    """OpenAI Images: ``images.generate`` with gpt-image-1 (no dall-e-2 dependency)."""

    def __init__(
        self,
        *,
        model: str = "gpt-image-1",
        mode: str = "auto",
        size: str = "1024x1024",
        retries: int = 2,
    ) -> None:
        self.model = str(model).strip()
        self.mode = str(mode or "auto").strip().lower()
        self.size = str(size or "1024x1024").strip()
        self.retries = max(1, int(retries))

    def _require_key(self) -> None:
        key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if not key:
            raise OpenAIMissingKeyError(
                "OPENAI_API_KEY 가 설정되어 있지 않습니다. "
                ".env 또는 환경변수 OPENAI_API_KEY 를 설정하세요."
            )
        os.environ["OPENAI_API_KEY"] = key

    def _save_response(self, resp: Any, out_path: Path) -> None:
        if not getattr(resp, "data", None):
            raise RuntimeError("OpenAI 응답 data 비어 있음")
        datum = resp.data[0]
        b64 = getattr(datum, "b64_json", None)
        url = getattr(datum, "url", None)
        if hasattr(datum, "model_dump"):
            dump = datum.model_dump()
            b64 = b64 or dump.get("b64_json")
            url = url or dump.get("url")
        raw: bytes | None = None
        if b64:
            raw = base64.b64decode(b64, validate=False)
        elif url:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "KakaoEmoticonFactory/sheet (OpenAI image download)"},
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read()
        if not raw:
            raise RuntimeError("OpenAI 이미지 페이로드 없음")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(raw)

    def _resolve_reference(
        self, package_dir: Path, photo_path: Path
    ) -> tuple[Path | None, str]:
        """Priority: canonical_character.png → character/reference.png → primary photo_path."""
        canon = package_dir / "character" / "canonical_character.png"
        if canon.is_file():
            return canon, "canonical_character"
        ref = package_dir / "character" / "reference.png"
        if ref.is_file():
            return ref, "reference"
        p = Path(photo_path)
        if p.is_file():
            return p, "photo_path"
        return None, "none"

    def _profile_brief(self, profile: CharacterProfile | None) -> str:
        if profile is None:
            return "Pet: unspecified; match a single cute sticker mascot."
        return (
            f"Species: {profile.species}. Breed/style: {profile.breed_style}. "
            f"Main colors/markings: {profile.main_colors}. Face: {profile.face_mask_color}. "
            f"Eyes: {profile.eye_color}. Ears: {profile.ear_shape}. "
            f"Expression baseline: {profile.expression}. Personality: {profile.personality}. "
            f"Design keywords: {', '.join(profile.design_keywords)}. "
            f"Avoid: {', '.join(profile.negative_keywords)}."
        )

    def _build_prompt(
        self,
        *,
        profile: CharacterProfile | None,
        reference_type: str | None,
        anchor_label: str,
        style_intensity: float = 0.5,
    ) -> str:
        rt = str(reference_type or "").strip().lower()
        art_block = ""
        if rt == "character_art":
            art_block = (
                "The input is existing character artwork: preserve the exact existing character art style; "
                "do not reinterpret the style; do not flatten into a different illustration language. "
            )

        identity_anchor = ""
        if anchor_label == "canonical_character":
            identity_anchor = (
                "Identity anchor: a canonical locked character image exists for this series — "
                "the turnaround must be the same character as that artwork (not a redesign). "
            )
        elif anchor_label == "reference":
            identity_anchor = (
                "Identity anchor: match the packaged real pet reference — same animal, markings, and breed. "
            )
        elif anchor_label == "photo_path":
            identity_anchor = "Identity anchor: match the primary reference photo used for this run. "

        text_only_note = (
            "This sheet is generated with images.generate (text + character bible only); "
            "no reference image bytes are sent to the API — follow the bible literally to reduce drift. "
        )

        brief = self._profile_brief(profile)
        si = clamp_style_intensity(style_intensity)
        sheet_body = sheet_illustration_reference_prompt_fragment(si)
        return (
            f"{illustration_texture_fragment(si)}"
            f"Create an illustration reference sheet (not a flat corporate turnaround vector). "
            f"{sheet_body}. "
            "\n\nLayout (one image, five panels or a clear five-region grid): "
            "front view; 3/4 view; happy expression; neutral expression; simple paw pose. "
            "CRITICAL: pose/expression variation only — same character identity in every panel. "
            f"{identity_anchor}{art_block}{text_only_note}"
            f"\n\nCharacter bible (text): {brief}"
        )

    def _assert_mode(self) -> None:
        if self.mode == "edit":
            raise RuntimeError(
                "Character sheet 생성은 gpt-image-1 기반 images.generate 로만 지원합니다. "
                "--sheet-openai-mode generate 또는 auto 를 사용하세요. "
                "images.edit / dall-e-2 경로는 시트 생성에서 제거되었습니다."
            )

    def generate(
        self,
        *,
        photo_path: Path,
        package_dir: Path,
        series_name: str,
        profile: CharacterProfile | None,
        reference_type: str | None = None,
        forced_character_sheet_on_character_art: bool = False,
        style_intensity: float = 0.5,
    ) -> dict[str, Any]:
        from openai import OpenAI

        self._assert_mode()
        si = clamp_style_intensity(style_intensity)
        self._require_key()
        client = OpenAI()
        char_dir = package_dir / "character"
        char_dir.mkdir(parents=True, exist_ok=True)
        out_path = char_dir / SHEET_FILENAME

        _ref_path, anchor_label = self._resolve_reference(package_dir, photo_path)

        used_image_ref: str | None = {
            "canonical_character": "character/canonical_character.png",
            "reference": "character/reference.png",
            "photo_path": str(Path(photo_path).resolve()),
            "none": None,
        }.get(anchor_label)

        prompt = self._build_prompt(
            profile=profile,
            reference_type=reference_type,
            anchor_label=anchor_label,
            style_intensity=si,
        )
        if len(prompt) > 9000:
            prompt = prompt[:8990] + "…"

        attempts: list[dict[str, Any]] = []
        last_err: str | None = None
        sheet_generation_mode = "generate"
        text_only_fallback = True
        drift_risk_warning = True

        for attempt in range(1, self.retries + 1):
            st = datetime.now(timezone.utc).isoformat()
            try:
                gen_kw: dict[str, Any] = {
                    "model": self.model,
                    "prompt": prompt,
                    "n": 1,
                }
                if self.size:
                    gen_kw["size"] = self.size
                try:
                    resp = client.images.generate(**gen_kw)
                except TypeError:
                    gen_kw.pop("size", None)
                    resp = client.images.generate(**gen_kw)
                self._save_response(resp, out_path)
                attempts.append({"attempt": attempt, "phase": "images.generate", "ok": True, "at": st})

                log: dict[str, Any] = {
                    "backend": "openai",
                    "model": self.model,
                    "created_at_utc": datetime.now(timezone.utc).isoformat(),
                    "series_name": series_name,
                    "source_photo": str(Path(photo_path).resolve()),
                    "output": f"character/{SHEET_FILENAME}",
                    "attempts": attempts,
                    "pet_species": getattr(profile, "species", None) if profile else None,
                    "sheet_openai_mode": self.mode,
                    "sheet_generation_mode": sheet_generation_mode,
                    "sheet_reference_type": str(reference_type or ""),
                    "style_intensity": si,
                    "used_image_reference": used_image_ref,
                    "text_only_fallback": text_only_fallback,
                    "drift_risk_warning": drift_risk_warning,
                    "character_sheet_generator_backend": "openai",
                    "character_sheet_generation_mode": sheet_generation_mode,
                    "character_sheet_reference_type": str(reference_type or ""),
                    "character_sheet_model": self.model,
                    "sheet_mock": False,
                    "api_phase": "images.generate",
                }
                if forced_character_sheet_on_character_art:
                    log["forced_character_sheet_on_character_art"] = True
                (char_dir / LOG_FILENAME).write_text(
                    json.dumps(log, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return log
            except Exception as exc:
                last_err = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                attempts.append(
                    {
                        "attempt": attempt,
                        "phase": "images.generate",
                        "ok": False,
                        "at": st,
                        "error": last_err,
                    }
                )

        raise RuntimeError(f"character sheet OpenAI 실패: {last_err}")


def create_character_sheet_generator(backend: str, **kwargs: Any) -> BaseCharacterSheetGenerator:
    b = str(backend).strip().lower()
    if b == "mock":
        return MockCharacterSheetGenerator()
    if b == "openai":
        return OpenAICharacterSheetGenerator(
            model=str(kwargs.get("openai_model", "gpt-image-1")),
            mode=str(kwargs.get("openai_mode", "auto")),
            size=str(kwargs.get("openai_size", "1024x1024")),
            retries=int(kwargs.get("openai_retries", 2)),
        )
    raise ValueError(f"Unsupported sheet generator: {backend!r}")
