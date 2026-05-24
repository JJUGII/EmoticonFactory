"""Generate base character candidates from one input image (mock or OpenAI)."""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import traceback
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from services.base_character_prompt import (
    BASE_CANDIDATE_STYLE_HINTS,
    BASE_CANDIDATE_VARIATION_SEEDS,
    base_candidate_prompt_for_index,
)
from services.env_log import format_openai_exception, openai_client_kwargs
from services.image_generator import OpenAIMissingKeyError
from services.image_io import pil_open_image

_SHEET_BIBLE_KO = (
    "제공된 캐릭터 시트를 기준으로 동일한 정체성의 베이스 캐릭터로 그려줘. "
    "새 캐릭터를 만들지 마. "
)

_FALLBACK_CONSOLE_WARNING = (
    "[경고] 이미지 참조 없이 텍스트 생성으로 폴백되어 결과가 달라질 수 있습니다."
)


@dataclass
class CandidateGenerationResult:
    success: bool
    paths: list[Path] = field(default_factory=list)
    manifest_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    entries: list[dict[str, Any]] = field(default_factory=list)
    used_image_reference: bool = False
    text_only_fallback: bool = False
    drift_risk_warning: bool = False
    fallback_warning: str | None = None


class BaseCharacterCandidateGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        *,
        original_photo_path: Path,
        series_name: str,
        species_hint: str,
        personality_hint: str,
        count: int,
        output_dir: Path,
        used_character_sheet: bool = False,
        source_reference: str = "",
    ) -> CandidateGenerationResult:
        ...


def _prepare_image_bytes_for_edit(path: Path) -> io.BytesIO:
    """PNG/RGBA, 최대 변 한쪽 1024 — images.edit 입력용."""
    img = pil_open_image(path).convert("RGBA")
    max_side = 1024
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    bio = io.BytesIO()
    img.save(bio, format="PNG", optimize=True)
    bio.seek(0)
    bio.name = path.name if path.suffix else "input.png"
    return bio


class MockCharacterCandidateGenerator(BaseCharacterCandidateGenerator):
    """Three Pillow variants — 입력 이미지 픽셀 기반(오프라인)."""

    def generate(
        self,
        *,
        original_photo_path: Path,
        series_name: str,
        species_hint: str,
        personality_hint: str,
        count: int,
        output_dir: Path,
        used_character_sheet: bool = False,
        source_reference: str = "",
    ) -> CandidateGenerationResult:
        _ = series_name, used_character_sheet, source_reference
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        n = max(1, min(8, int(count)))
        result = CandidateGenerationResult(success=True)
        try:
            base = pil_open_image(original_photo_path).convert("RGBA")
        except OSError as exc:
            result.success = False
            result.errors.append(repr(exc))
            return result

        w, h = base.size
        thumb = base.copy()
        thumb.thumbnail((512, 512), Image.Resampling.LANCZOS)

        accents = (
            ((255, 140, 80, 255), (40, 90, 200, 255)),
            ((80, 200, 160, 255), (200, 60, 120, 255)),
            ((220, 200, 60, 255), (90, 40, 160, 255)),
        )
        for i in range(n):
            idx = i + 1
            seed = BASE_CANDIDATE_VARIATION_SEEDS.get(idx, 100 + idx)
            style_hint = BASE_CANDIDATE_STYLE_HINTS.get(idx, "귀여운 이모티콘 감성")
            prompt = base_candidate_prompt_for_index(
                idx,
                species_hint=species_hint,
                personality_hint=personality_hint,
            )
            out = thumb.copy()
            out = ImageEnhance.Color(out).enhance(1.12 + (seed % 7) * 0.02)
            out = ImageEnhance.Brightness(out).enhance(0.92 + (seed % 5) * 0.02)
            draw = ImageDraw.Draw(out)
            ax, bx = accents[i % len(accents)]
            draw.rounded_rectangle(
                (12 + i * 4, 12, 120 + i * 10, 48 + i * 2),
                radius=10,
                outline=ax,
                width=3 + i,
            )
            cx, cy = out.size[0] // 2, int(out.size[1] * 0.35)
            draw.ellipse(
                (cx - 36 - i * 4, cy - 18, cx + 36 + i * 4, cy + 42 + i * 6),
                outline=bx,
                width=3 + i,
            )
            if idx == 3:
                out = out.filter(ImageFilter.GaussianBlur(radius=0.4))
            elif idx == 2:
                out = out.filter(ImageFilter.SMOOTH_MORE)
            else:
                out = out.filter(ImageFilter.SHARPEN)
            path = output_dir / f"candidate_{idx:02d}.png"
            out.save(path, format="PNG")
            result.paths.append(path)
            result.entries.append(
                {
                    "index": idx,
                    "path": str(path.resolve()),
                    "success": True,
                    "backend": "mock",
                    "prompt": prompt,
                    "style_hint": style_hint,
                    "variation_seed": seed,
                    "api_phase": "mock_local",
                    "used_image_reference": True,
                    "text_only_fallback": False,
                    "drift_risk_warning": False,
                    "note": "mock base character candidate (입력 이미지 픽셀 변형)",
                }
            )

        result.used_image_reference = True
        manifest = output_dir / "candidates.json"
        doc = _manifest_doc(
            series_name=series_name,
            species_hint=species_hint,
            personality_hint=personality_hint,
            original_photo_path=original_photo_path,
            source_reference=source_reference,
            used_character_sheet=used_character_sheet,
            n=n,
            w=w,
            h=h,
            entries=result.entries,
            used_image_reference=True,
            text_only_fallback=False,
            drift_risk_warning=False,
        )
        manifest.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result.manifest_path = manifest
        return result


class OpenAICharacterCandidateGenerator(BaseCharacterCandidateGenerator):
    """입력 이미지 bytes → images.edit 우선; auto 실패 시에만 images.generate 폴백."""

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

    def _edit_model(self) -> str:
        m = self.model.lower()
        if m.startswith("dall-e"):
            return "dall-e-2" if "dall-e-2" in m or m == "dall-e" else self.model
        return self.model

    def _build_prompt(
        self,
        *,
        idx: int,
        species_hint: str,
        personality_hint: str,
        used_character_sheet: bool,
        text_only: bool,
    ) -> str:
        prefix = _SHEET_BIBLE_KO if used_character_sheet else ""
        body = base_candidate_prompt_for_index(
            idx,
            species_hint=species_hint,
            personality_hint=personality_hint,
            include_english_fallback=text_only,
        )
        prompt = (prefix + body).strip()
        if len(prompt) > 3900:
            prompt = prompt[:3890] + "…"
        return prompt

    def _generate_kwargs(self, prompt: str) -> dict[str, Any]:
        kw: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
        }
        if self.size:
            kw["size"] = self.size
        return kw

    def _decode_and_save(self, resp: Any, output_path: Path) -> None:
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
                headers={"User-Agent": "KakaoEmoticonFactory/candidates (OpenAI image download)"},
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read()
        if not raw:
            raise RuntimeError("OpenAI 이미지 페이로드 없음")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(raw)

    def _try_edit(self, client: Any, photo: Path, prompt: str) -> Any:
        bio = _prepare_image_bytes_for_edit(photo)
        edit_model = self._edit_model()
        return client.images.edit(
            model=edit_model,
            image=bio,
            prompt=prompt[:950],
            n=1,
            size=self.size or "1024x1024",
        )

    def _try_generate(self, client: Any, prompt: str) -> Any:
        gen_kw = self._generate_kwargs(prompt)
        try:
            return client.images.generate(**gen_kw)
        except TypeError:
            gen_kw.pop("size", None)
            return client.images.generate(**gen_kw)

    def _render_one(
        self,
        client: Any,
        photo: Path,
        prompt: str,
        path: Path,
        *,
        idx: int,
        species_hint: str,
        personality_hint: str,
        used_character_sheet: bool,
    ) -> dict[str, Any]:
        """한 장 생성. 반환: api_phase, used_image_reference, text_only_fallback, attempts."""
        attempts: list[dict[str, Any]] = []
        mode = self.mode

        if mode == "generate":
            for attempt in range(1, self.retries + 1):
                st = datetime.now(timezone.utc).isoformat()
                try:
                    resp = self._try_generate(client, prompt)
                    self._decode_and_save(resp, path)
                    attempts.append(
                        {"attempt": attempt, "phase": "images.generate", "ok": True, "at": st}
                    )
                    return {
                        "api_phase": "images.generate",
                        "used_image_reference": False,
                        "text_only_fallback": True,
                        "drift_risk_warning": True,
                        "attempts": attempts,
                        "ok": True,
                    }
                except Exception as exc:
                    err = format_openai_exception(exc)
                    print(f"[OpenAI candidate {idx}] images.generate error:\n{err}", file=sys.stderr)
                    attempts.append(
                        {
                            "attempt": attempt,
                            "phase": "images.generate",
                            "ok": False,
                            "at": st,
                            "error": err,
                        }
                    )
            return {
                "api_phase": "images.generate",
                "used_image_reference": False,
                "text_only_fallback": True,
                "drift_risk_warning": True,
                "attempts": attempts,
                "ok": False,
                "error": attempts[-1].get("error") if attempts else "generate failed",
            }

        if mode == "edit":
            for attempt in range(1, self.retries + 1):
                st = datetime.now(timezone.utc).isoformat()
                try:
                    resp = self._try_edit(client, photo, prompt)
                    self._decode_and_save(resp, path)
                    attempts.append(
                        {"attempt": attempt, "phase": "images.edit", "ok": True, "at": st}
                    )
                    return {
                        "api_phase": "images.edit",
                        "used_image_reference": True,
                        "text_only_fallback": False,
                        "drift_risk_warning": False,
                        "attempts": attempts,
                        "ok": True,
                    }
                except Exception as exc:
                    err = format_openai_exception(exc)
                    print(f"[OpenAI candidate {idx}] images.edit error:\n{err}", file=sys.stderr)
                    attempts.append(
                        {
                            "attempt": attempt,
                            "phase": "images.edit",
                            "ok": False,
                            "at": st,
                            "error": err,
                        }
                    )
            return {
                "api_phase": "images.edit",
                "used_image_reference": False,
                "text_only_fallback": False,
                "drift_risk_warning": False,
                "attempts": attempts,
                "ok": False,
                "error": attempts[-1].get("error") if attempts else "edit failed",
            }

        # auto: edit 우선 → 실패 시 generate 폴백
        edit_err: str | None = None
        for attempt in range(1, self.retries + 1):
            st = datetime.now(timezone.utc).isoformat()
            try:
                resp = self._try_edit(client, photo, prompt)
                self._decode_and_save(resp, path)
                attempts.append(
                    {"attempt": attempt, "phase": "images.edit", "ok": True, "at": st}
                )
                return {
                    "api_phase": "images.edit",
                    "used_image_reference": True,
                    "text_only_fallback": False,
                    "drift_risk_warning": False,
                    "attempts": attempts,
                    "ok": True,
                }
            except Exception as exc:
                edit_err = format_openai_exception(exc)
                print(f"[OpenAI candidate {idx}] images.edit error:\n{edit_err}", file=sys.stderr)
                attempts.append(
                    {
                        "attempt": attempt,
                        "phase": "images.edit",
                        "ok": False,
                        "at": st,
                        "error": edit_err,
                    }
                )

        gen_prompt = self._build_prompt(
            idx=idx,
            species_hint=species_hint,
            personality_hint=personality_hint,
            used_character_sheet=used_character_sheet,
            text_only=True,
        )

        for attempt in range(1, self.retries + 1):
            st = datetime.now(timezone.utc).isoformat()
            try:
                resp = self._try_generate(client, gen_prompt)
                self._decode_and_save(resp, path)
                attempts.append(
                    {
                        "attempt": attempt,
                        "phase": "images.generate",
                        "ok": True,
                        "at": st,
                        "fallback_from": "images.edit",
                    }
                )
                print(_FALLBACK_CONSOLE_WARNING, file=sys.stderr)
                return {
                    "api_phase": "images.generate",
                    "used_image_reference": False,
                    "text_only_fallback": True,
                    "drift_risk_warning": True,
                    "attempts": attempts,
                    "ok": True,
                    "warning": _FALLBACK_CONSOLE_WARNING,
                }
            except Exception as exc:
                err = format_openai_exception(exc)
                print(
                    f"[OpenAI candidate {idx}] images.generate (fallback) error:\n{err}",
                    file=sys.stderr,
                )
                attempts.append(
                    {
                        "attempt": attempt,
                        "phase": "images.generate",
                        "ok": False,
                        "at": st,
                        "error": err,
                        "fallback_from": "images.edit",
                    }
                )
        return {
            "api_phase": "images.generate",
            "used_image_reference": False,
            "text_only_fallback": True,
            "drift_risk_warning": True,
            "attempts": attempts,
            "ok": False,
            "error": edit_err or (attempts[-1].get("error") if attempts else "failed"),
        }

    def generate(
        self,
        *,
        original_photo_path: Path,
        series_name: str,
        species_hint: str,
        personality_hint: str,
        count: int,
        output_dir: Path,
        used_character_sheet: bool = False,
        source_reference: str = "",
    ) -> CandidateGenerationResult:
        _ = source_reference
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        n = max(1, min(8, int(count)))
        result = CandidateGenerationResult(success=True)

        self._require_key()
        from openai import OpenAI

        client = OpenAI(**openai_client_kwargs())
        photo = Path(original_photo_path)

        any_fallback = False

        for i in range(n):
            idx = i + 1
            path = output_dir / f"candidate_{idx:02d}.png"
            style_hint = BASE_CANDIDATE_STYLE_HINTS.get(idx, "귀여운 이모티콘 감성")
            seed = BASE_CANDIDATE_VARIATION_SEEDS.get(idx, 100 + idx)
            text_only = self.mode == "generate"
            prompt = self._build_prompt(
                idx=idx,
                species_hint=species_hint,
                personality_hint=personality_hint,
                used_character_sheet=used_character_sheet,
                text_only=text_only,
            )

            entry: dict[str, Any] = {
                "index": idx,
                "path": str(path.resolve()),
                "success": False,
                "backend": "openai",
                "prompt": prompt,
                "style_hint": style_hint,
                "variation_seed": seed,
                "candidate_openai_model": self.model,
                "candidate_openai_mode": self.mode,
                "attempts": [],
            }

            render = self._render_one(
                client,
                photo,
                prompt,
                path,
                idx=idx,
                species_hint=species_hint,
                personality_hint=personality_hint,
                used_character_sheet=used_character_sheet,
            )
            entry["api_phase"] = render["api_phase"]
            entry["used_image_reference"] = render["used_image_reference"]
            entry["text_only_fallback"] = render["text_only_fallback"]
            entry["drift_risk_warning"] = render["drift_risk_warning"]
            entry["candidate_generation_mode"] = (
                "generate" if render["text_only_fallback"] else "edit"
            )
            entry["attempts"] = render.get("attempts", [])
            if render.get("warning"):
                entry["warning"] = render["warning"]

            if render.get("ok"):
                entry["success"] = True
                result.paths.append(path)
                if render["text_only_fallback"]:
                    any_fallback = True
            else:
                result.errors.append(
                    f"candidate_{idx:02d}: {render.get('error', 'unknown')}"
                )
                if render.get("text_only_fallback"):
                    any_fallback = True

            result.entries.append(entry)

        result.success = any(e.get("success") for e in result.entries)
        ok_entries = [e for e in result.entries if e.get("success")]
        result.used_image_reference = bool(ok_entries) and all(
            e.get("used_image_reference") for e in ok_entries
        )
        result.text_only_fallback = any_fallback or self.mode == "generate"
        result.drift_risk_warning = result.text_only_fallback
        if any_fallback:
            result.fallback_warning = _FALLBACK_CONSOLE_WARNING

        manifest = output_dir / "candidates.json"
        doc = _manifest_doc(
            series_name=series_name,
            species_hint=species_hint,
            personality_hint=personality_hint,
            original_photo_path=photo,
            source_reference=source_reference or str(photo.resolve()),
            used_character_sheet=used_character_sheet,
            n=n,
            w=0,
            h=0,
            entries=result.entries,
            candidate_openai_model=self.model,
            candidate_openai_mode=self.mode,
            used_image_reference=result.used_image_reference,
            text_only_fallback=result.text_only_fallback,
            drift_risk_warning=result.drift_risk_warning,
            fallback_warning=result.fallback_warning,
        )
        manifest.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result.manifest_path = manifest
        return result


def _manifest_doc(
    *,
    series_name: str,
    species_hint: str,
    personality_hint: str,
    original_photo_path: Path,
    source_reference: str,
    used_character_sheet: bool,
    n: int,
    w: int,
    h: int,
    entries: list[dict[str, Any]],
    candidate_openai_model: str | None = None,
    candidate_openai_mode: str | None = None,
    used_image_reference: bool | None = None,
    text_only_fallback: bool | None = None,
    drift_risk_warning: bool | None = None,
    fallback_warning: str | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "purpose": "base_character_candidates",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "series_name": series_name,
        "species_hint": species_hint,
        "personality_hint": personality_hint,
        "source_photo": str(Path(original_photo_path).resolve()),
        "source_reference": source_reference or str(Path(original_photo_path).resolve()),
        "used_character_sheet": bool(used_character_sheet),
        "count": n,
        "candidate_style_hints": [
            BASE_CANDIDATE_STYLE_HINTS.get(i + 1, "") for i in range(n)
        ],
        "candidate_variation_seeds": [
            BASE_CANDIDATE_VARIATION_SEEDS.get(i + 1, 100 + i) for i in range(n)
        ],
        "candidates": entries,
    }
    if w and h:
        doc["canvas_note"] = f"resized from {w}x{h}"
    if candidate_openai_model:
        doc["candidate_openai_model"] = candidate_openai_model
        doc["openai_model_note"] = candidate_openai_model
    if candidate_openai_mode is not None:
        doc["candidate_openai_mode"] = candidate_openai_mode
    if used_image_reference is not None:
        doc["used_image_reference"] = used_image_reference
    if text_only_fallback is not None:
        doc["text_only_fallback"] = text_only_fallback
    if drift_risk_warning is not None:
        doc["drift_risk_warning"] = drift_risk_warning
    if fallback_warning:
        doc["warning"] = fallback_warning
    phases = [e.get("api_phase") for e in entries if e.get("api_phase")]
    if phases:
        doc["api_phase"] = phases[0] if len(set(phases)) == 1 else "mixed"
    return doc


def create_character_candidate_generator(
    backend: str,
    *,
    openai_model: str = "gpt-image-1",
    openai_mode: str = "auto",
    openai_size: str = "1024x1024",
    openai_retries: int = 2,
) -> BaseCharacterCandidateGenerator:
    b = str(backend).strip().lower()
    if b == "mock":
        return MockCharacterCandidateGenerator()
    if b == "openai":
        return OpenAICharacterCandidateGenerator(
            model=openai_model,
            mode=openai_mode,
            size=openai_size,
            retries=openai_retries,
        )
    raise ValueError(f"Unsupported candidate generator backend: {backend!r}")
