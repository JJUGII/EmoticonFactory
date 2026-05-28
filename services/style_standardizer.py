"""Style standardization: ``none`` (no standard sheet; generate from original photo), ``mock``, ``openai``."""

from __future__ import annotations

import base64
import io
import math
import os
import time
import traceback
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from config import EMOTICON_SIZE
from services.character_profile import CharacterProfile
from services.image_io import pil_save_image


class BaseStyleStandardizer(ABC):
    """Convert a reference image into an emoticon-ready stylized base asset."""

    @abstractmethod
    def standardize(
        self,
        source_path: Path,
        output_path: Path,
        profile: CharacterProfile,
        style: str = "clean_vector_line_art",
    ) -> Path:
        """Write or select a stylized 540×540 RGBA PNG; return resolved path."""


class NoneStyleStandardizer(BaseStyleStandardizer):
    """No-op: pipeline does not write a standard sheet; generation uses the packaged original photo."""

    def standardize(
        self,
        source_path: Path,
        output_path: Path,
        profile: CharacterProfile,
        style: str = "clean_vector_line_art",
    ) -> Path:
        _ = output_path
        _ = style
        _ = profile
        return Path(source_path).resolve()


class MockStyleStandardizer(BaseStyleStandardizer):
    """Pillow-only dev mascot (not photo-accurate). Writes ``standardized_character_mock.png``."""

    _OUTLINE = (35, 28, 24, 255)
    _CREAM = (252, 236, 214, 255)
    _CREAM_SHADOW = (235, 215, 190, 255)
    _MASK = (72, 48, 38, 255)
    _MASK_DEEP = (52, 34, 28, 255)
    _EAR_OUTER = (30, 26, 28, 255)
    _EAR_INNER = (255, 190, 200, 255)
    _EYE_BLUE = (90, 160, 220, 255)
    _NOSE = (255, 160, 175, 255)
    _PAW = (55, 42, 38, 255)

    def standardize(
        self,
        source_path: Path,
        output_path: Path,
        profile: CharacterProfile,
        style: str = "clean_vector_line_art",
    ) -> Path:
        _ = source_path
        _ = style
        _ = profile

        w, h = EMOTICON_SIZE
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        cx, cy = w // 2, int(h * 0.52)
        body_w, body_h = 280, 240
        draw.rounded_rectangle(
            (cx - body_w // 2, cy - 20, cx + body_w // 2, cy + body_h - 30),
            radius=70,
            fill=self._CREAM,
            outline=self._OUTLINE,
            width=8,
        )
        draw.rounded_rectangle(
            (cx - body_w // 2 + 36, cy + 30, cx + body_w // 2 - 36, cy + body_h - 70),
            radius=50,
            fill=self._CREAM_SHADOW,
            outline=None,
        )
        paw_y = cy + body_h - 78
        for px in (cx - 72, cx + 72):
            draw.rounded_rectangle(
                (px - 44, paw_y, px + 44, paw_y + 68),
                radius=22,
                fill=self._CREAM,
                outline=self._OUTLINE,
                width=7,
            )
            draw.ellipse(
                (px - 28, paw_y + 38, px + 28, paw_y + 62),
                fill=self._PAW,
                outline=self._OUTLINE,
                width=4,
            )
        head_r = 118
        head_cy = cy - 110
        draw.ellipse(
            (cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r),
            fill=self._CREAM,
            outline=self._OUTLINE,
            width=8,
        )
        ear_h = 115
        for sign in (-1, 1):
            tip_x = cx + sign * (head_r - 10)
            tip_y = head_cy - head_r + 8
            base_in = cx + sign * 40
            base_out = cx + sign * (head_r + 18)
            base_y = head_cy - 30
            pts = [
                (tip_x, tip_y - ear_h + 20),
                (base_out, base_y),
                (base_in, base_y + 18),
            ]
            draw.polygon(pts, fill=self._EAR_OUTER, outline=self._OUTLINE)
            inner = [
                (tip_x, tip_y - ear_h + 52),
                (base_out - sign * 18, base_y + 6),
                (base_in + sign * 10, base_y + 16),
            ]
            draw.polygon(inner, fill=self._EAR_INNER, outline=None)
        mask_pts = [
            (cx, head_cy - 8),
            (cx - 96, head_cy + 36),
            (cx - 88, head_cy + 92),
            (cx - 40, head_cy + 108),
            (cx + 40, head_cy + 108),
            (cx + 88, head_cy + 92),
            (cx + 96, head_cy + 36),
        ]
        draw.polygon(mask_pts, fill=self._MASK, outline=self._MASK_DEEP)
        eye_y = head_cy + 22
        eye_dx = 46
        for sign in (-1, 1):
            ex = cx + sign * eye_dx
            draw.line((ex - 28, eye_y, ex + 28, eye_y), fill=self._EYE_BLUE, width=10)
            draw.arc(
                (ex - 26, eye_y - 14, ex + 26, eye_y + 18),
                start=200,
                end=340,
                fill=self._EYE_BLUE,
                width=8,
            )
        for sign in (-1, 1):
            ex = cx + sign * eye_dx
            draw.arc(
                (ex - 32, eye_y - 42, ex + 16, eye_y - 8),
                start=170,
                end=10,
                fill=self._MASK_DEEP,
                width=6,
            )
        draw.polygon(
            [(cx, head_cy + 62), (cx - 14, head_cy + 80), (cx + 14, head_cy + 80)],
            fill=self._NOSE,
            outline=self._OUTLINE,
        )
        draw.arc(
            (cx - 22, head_cy + 74, cx + 22, head_cy + 118),
            start=200,
            end=340,
            fill=self._OUTLINE,
            width=6,
        )
        wy = head_cy + 72
        for sign in (-1, 1):
            for i, length in enumerate((78, 86, 78)):
                y0 = wy + i * 10 - 10
                x0 = cx + sign * 70
                x1 = x0 + sign * length
                dy = (-4, 0, 4)[i]
                draw.line((x0, y0, x1, y0 + dy), fill=self._OUTLINE, width=4)
        tail_pts = []
        for t in range(0, 80, 4):
            ang = math.radians(120 + t * 2.4)
            r = 40 + t * 0.35
            tx = cx + head_r + 30 + math.cos(ang) * r
            ty = cy + 40 + math.sin(ang) * r * 0.85
            tail_pts.append((tx, ty))
        if len(tail_pts) >= 2:
            draw.line(tail_pts, fill=self._OUTLINE, width=10)
            draw.line(tail_pts, fill=self._CREAM, width=5)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pil_save_image(img, output_path, format="PNG")
        return output_path.resolve()


def _decode_openai_image(resp: Any, output_path: Path) -> None:
    if not getattr(resp, "data", None):
        raise RuntimeError("OpenAI 응답 data 비어있음")
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
            headers={"User-Agent": "KakaoEmoticonFactory/1 (OpenAI style)"},
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read()
    if not raw:
        raise RuntimeError("OpenAI 이미지 페이로드 없음")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(raw)


class OpenAIStyleStandardizer(BaseStyleStandardizer):
    """One clean sticker-style character sheet from a real pet photo (generate-first for gpt-image-1)."""

    def __init__(self, model: str = "gpt-image-1", size: str = "1024x1024") -> None:
        self.model = model
        self.size = size
        self._last_phases: list[dict[str, Any]] = []

    def _require_key(self) -> None:
        key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY 가 필요합니다 (--stylizer openai). "
                ".env 또는 환경 변수를 설정하세요."
            )
        os.environ["OPENAI_API_KEY"] = key

    def standardize(
        self,
        source_path: Path,
        output_path: Path,
        profile: CharacterProfile,
        style: str = "clean_vector_line_art",
    ) -> Path:
        _ = style
        from openai import OpenAI

        self._require_key()
        client = OpenAI()
        sp = profile.species
        palette = profile.main_colors
        self._last_phases = []
        phases = self._last_phases

        base_prompt = (
            "Create one clean sticker character design based on the provided real pet photo. "
            "single pet only. front-facing neutral pose. "
            "no Korean text. no caption. no props. "
            "clean transparent or plain white background. "
            "hand-drawn sticker character. thick soft outline. simplified flat colors. "
            "preserve the pet's unique fur colors, face markings, ear shape, eye impression, "
            "body silhouette. do not invent a different breed or species. "
            "do not make it photorealistic. do not add clothes or accessories. "
            f"Species hint: {sp}. Palette notes: {palette}."
        )

        def log_phase(name: str, ok: bool, err: str | None = None, extra: dict | None = None) -> None:
            row: dict[str, Any] = {"phase": name, "ok": ok, "ts": time.time(), "error": err}
            if extra:
                row.update(extra)
            phases.append(row)

        src = Path(source_path)
        last_err: str | None = None
        if src.is_file() and self.model.strip().lower().startswith("dall-e-2"):
            try:
                st = time.perf_counter()
                bio = io.BytesIO(src.read_bytes())
                resp = client.images.edit(
                    model="dall-e-2",
                    image=bio,
                    prompt=base_prompt[:950],
                    n=1,
                    size="1024x1024",
                )
                _decode_openai_image(resp, output_path)
                log_phase("images.edit", True, extra={"wall_seconds": round(time.perf_counter() - st, 4)})
                return output_path.resolve()
            except Exception as e:
                last_err = "".join(traceback.format_exception_only(type(e), e)).strip()
                log_phase("images.edit", False, err=last_err)

        try:
            st = time.perf_counter()
            desc = (
                base_prompt
                + " If you cannot see the photo, approximate a generic cute sticker pet "
                f"matching hints: species={sp}, colors={palette}."
            )
            resp = client.images.generate(
                model=self.model,
                prompt=desc,
                size=self.size,  # type: ignore[arg-type]
                n=1,
            )
            _decode_openai_image(resp, output_path)
            log_phase(
                "images.generate",
                True,
                extra={
                    "wall_seconds": round(time.perf_counter() - st, 4),
                    "fallback_after_edit_failure": bool(last_err),
                },
            )
            return output_path.resolve()
        except Exception as e:
            err = "".join(traceback.format_exception_only(type(e), e)).strip()
            log_phase("images.generate", False, err=err)
            raise RuntimeError(f"OpenAIStyleStandardizer 실패: {err}") from e


def style_prompt_document(profile: CharacterProfile, stylizer_kind: str) -> str:
    """Build ``meta/style_prompt.txt`` contents."""
    design = ", ".join(profile.design_keywords)
    lines: list[str] = [
        "# Kakao 큰 이모티콘 — 스타일 표준화 (자동 생성)",
        "",
        "## 1) 캐릭터 설명",
        f"- Species: {profile.species}",
        f"- Style line: {profile.breed_style}",
        f"- Colors / markings: {profile.main_colors}",
        f"- Face: {profile.face_mask_color}",
        f"- Eyes: {profile.eye_color}",
        f"- Ears: {profile.ear_shape}",
        f"- Expression baseline: {profile.expression}",
        f"- Personality: {profile.personality}",
        "",
        "## 2) 디자인 키워드",
        f"- {design}",
        "",
        "## 3) 금지",
    ]
    for nk in profile.negative_keywords:
        lines.append(f"- {nk}")
    lines += ["", "## 4) 일관성 규칙"]
    for rule in profile.consistency_rules:
        lines.append(f"- {rule}")
    lines += [
        "",
        "## 5) 카카오 큰 이모티콘 캔버스",
        f"- {EMOTICON_SIZE[0]}×{EMOTICON_SIZE[1]} px RGBA",
        "",
        "## 6) 파이프라인",
        f"- Stylizer 백엔드: {stylizer_kind}",
        "- mock 은 개발용 벡터 목업(실제 반려동물과 다를 수 있음).",
        "- none 은 표준화 PNG를 만들지 않고 흰 배경 기준 사진을 캐논으로 사용.",
        "- openai 는 실제 사진 기반 단일 캐릭터 시트를 생성(gpt-image-1 은 주로 images.generate).",
    ]
    return "\n".join(lines) + "\n"


def create_stylizer(
    kind: str,
    *,
    openai_model: str = "gpt-image-1",
    openai_size: str = "1024x1024",
) -> BaseStyleStandardizer:
    """Factory for CLI ``--stylizer``."""
    k = kind.strip().lower()
    if k == "none":
        return NoneStyleStandardizer()
    if k == "mock":
        return MockStyleStandardizer()
    if k == "openai":
        return OpenAIStyleStandardizer(model=openai_model, size=openai_size)
    raise ValueError(f"지원하지 않는 stylizer 입니다: {kind!r} (none|mock|openai)")
