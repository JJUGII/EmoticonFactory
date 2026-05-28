"""Image generation backends: mock (Pillow) and OpenAI GPT Image API."""

from __future__ import annotations

import base64
import io
import math
import os
import random
import time
import traceback
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from services.image_io import ImageReadError, pil_open_image, pil_save_image


class BaseImageGenerator(ABC):
    """Abstract image generator used by the CLI pipeline."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        output_path: Path,
        text: str,
        item_id: str,
        reference_path: Path | None = None,
        item: dict | None = None,
    ) -> Path:
        """Create one raster image and write to ``output_path`` (parent dirs must exist)."""


class MockImageGenerator(BaseImageGenerator):
    """Mock compositor: standardized ref + pose-specific layout, props, typography."""

    _CANVAS = (540, 540)
    _REF_MIN = 320
    _REF_MAX = 420
    _TEXT_FILL = (90, 55, 40, 255)
    _TEXT_OUTLINE = (255, 255, 255, 255)

    def __init__(self, canvas_size: tuple[int, int] = (540, 540)) -> None:
        self._size = canvas_size
        self.last_attempt_logs: list[dict[str, Any]] = []

    def generate(
        self,
        prompt: str,
        output_path: Path,
        text: str,
        item_id: str,
        reference_path: Path | None = None,
        item: dict | None = None,
    ) -> Path:
        """Build sticker mock from reference when available; else legacy circle cat."""
        st = time.perf_counter()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        item = item or {}
        no_ai = bool(item.get("_no_ai_text", True))

        if reference_path is not None and reference_path.is_file():
            img = self._composite_from_reference(text, item_id, reference_path, item, no_ai_text=no_ai)
        else:
            img = self._draw_fallback_cat(text, item_id, no_ai_text=no_ai)

        pil_save_image(img, output_path, format="PNG")
        self.last_attempt_logs = [
            {
                "attempt": 1,
                "phase": "mock_pillow",
                "success": True,
                "latency_ms": round((time.perf_counter() - st) * 1000, 2),
                "wall_seconds": round(time.perf_counter() - st, 4),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "usage": None,
                "error": None,
            }
        ]
        return output_path

    def _composite_from_reference(
        self,
        text: str,
        item_id: str,
        reference_path: Path,
        item: dict[str, Any],
        *,
        no_ai_text: bool = True,
    ) -> Image.Image:
        """Layout + props + overlays; preserves same base sprite (mask/ears from asset)."""
        w, h = self._size
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        layout = str(item.get("layout_type", "square_full_body"))
        if layout == "reaction_burst":
            self._draw_burst_background(draw, w, h)

        try:
            ref_rgba = pil_open_image(reference_path).convert("RGBA")
        except (OSError, ImageReadError):
            return self._draw_fallback_cat(text, item_id)

        max_side = self._reference_max_side(item_id)
        factor = self._layout_scale_factor(layout)
        target = min(int(max_side * factor), min(w, h) - 16)

        ref_rs = self._resize_contain(ref_rgba, target)

        if self._should_mirror_back_turn(item):
            ref_rs = ImageOps.mirror(ref_rs)

        if layout == "lying_pose":
            ref_rs = ref_rs.rotate(-14, expand=True, resample=Image.Resampling.BICUBIC)

        rw, rh = ref_rs.size
        ox = (w - rw) // 2
        oy_base = self._vertical_offset(layout, rh, h)
        oy = oy_base

        canvas.paste(ref_rs, (ox, oy), ref_rs)

        rnd = self._rnd(item_id)
        cx = ox + rw // 2
        cy = oy + rh // 2

        self._draw_props_by_id(draw, item, ox, oy, rw, rh, rnd, w, h)
        self._draw_expression_overlays(draw, item, ox, oy, rw, rh)

        if not no_ai_text:
            small = self._try_load_font(18)
            draw.text((14, 12), f"#{item_id}", fill=(65, 65, 90, 255), font=small)
            self._draw_caption(draw, text, item, w, h, rnd)

        return canvas

    def _rnd(self, item_id: str) -> random.Random:
        try:
            return random.Random(int(item_id))
        except ValueError:
            return random.Random(sum(ord(c) for c in item_id))

    def _layout_scale_factor(self, layout: str) -> float:
        return {
            "square_full_body": 1.0,
            "face_closeup": 1.22,
            "half_body": 1.06,
            "lying_pose": 0.9,
            "reaction_burst": 1.04,
        }.get(layout, 1.0)

    def _vertical_offset(self, layout: str, rh: int, ch: int) -> int:
        base = (ch - rh) // 2
        deltas = {
            "square_full_body": -26,
            "face_closeup": -62,
            "half_body": -32,
            "lying_pose": 58,
            "reaction_burst": -34,
        }
        return base + deltas.get(layout, -28)

    def _should_mirror_back_turn(self, item: dict[str, Any]) -> bool:
        bp = str(item.get("body_pose", ""))
        return item.get("id") == "05" or ("뒤" in bp or "뒷" in bp)

    def _reference_max_side(self, item_id: str) -> int:
        """Deterministic max edge length in [_REF_MIN, _REF_MAX] per cut."""
        try:
            idx = int(item_id)
        except ValueError:
            idx = sum(ord(c) for c in item_id) % 16 + 1
        span = self._REF_MAX - self._REF_MIN + 1
        return self._REF_MIN + ((idx * 29) % span)

    def _resize_contain(self, im: Image.Image, max_side: int) -> Image.Image:
        w_, h_ = im.size
        if w_ <= 0 or h_ <= 0:
            return im
        longer = max(w_, h_)
        scale = max_side / longer
        nw = max(1, int(round(w_ * scale)))
        nh = max(1, int(round(h_ * scale)))
        return im.resize((nw, nh), Image.Resampling.LANCZOS)

    def _draw_burst_background(
        self, draw: ImageDraw.ImageDraw, w: int, h: int
    ) -> None:
        """Soft radial scribble burst (behind character)."""
        cx, cy = w // 2, h // 2
        for i in range(18):
            ang = math.radians(i * 20)
            x1 = cx + int(math.cos(ang) * 40)
            y1 = cy + int(math.sin(ang) * 40)
            x2 = cx + int(math.cos(ang) * (115 + i * 3))
            y2 = cy + int(math.sin(ang) * (115 + i * 3))
            draw.line((x1, y1, x2, y2), fill=(255, 200, 220, 90), width=4)

    def _draw_props_by_id(
        self,
        draw: ImageDraw.ImageDraw,
        item: dict[str, Any],
        ox: int,
        oy: int,
        rw: int,
        rh: int,
        rnd: random.Random,
        w: int,
        h: int,
    ) -> None:
        """Draw prop artwork keyed by ``item['prop']``."""
        prop = str(item.get("prop", "none")).lower().strip()
        cx = ox + rw // 2
        cy = oy + rh // 2
        cut = str(item.get("id", ""))

        if prop == "none":
            pass
        elif prop == "large_heart_hold":
            self._heart(draw, cx, oy + rh - 110, 64, fill=(255, 120, 150, 240))
            self._heart(draw, cx - 52, oy + rh // 3, 22, fill=(255, 170, 190, 200))
        elif prop == "cardboard_box":
            top = oy + int(rh * 0.42)
            left = ox - 6
            right = ox + rw + 6
            bottom = oy + rh + 8
            draw.rounded_rectangle(
                (left, top, right, bottom),
                radius=10,
                fill=(166, 124, 82, 255),
                outline=(60, 45, 35, 255),
                width=6,
            )
            flap = oy + top - 44
            draw.polygon(
                [(left, top), (right, top), (cx + 50, flap), (cx - 50, flap)],
                fill=(140, 100, 70, 255),
                outline=(60, 45, 35, 255),
            )
            draw.rectangle((left + 30, top + 50, right - 30, bottom - 26), outline=(80, 60, 40, 255), width=4)
        elif prop == "small_hearts_pair":
            self._heart(draw, cx - 72, oy + 28, 24, fill=(255, 130, 170, 230))
            self._heart(draw, cx + 72, oy + 22, 20, fill=(255, 150, 190, 220))
        elif prop == "small_lightning":
            pts = [(cx + rw // 2 + 28, oy + 42), (cx + rw // 2 - 4, oy + 110),
                   (cx + rw // 2 + 44, oy + 108), (cx + rw // 2 + 14, oy + 180)]
            draw.polygon(pts, fill=(255, 235, 120, 255), outline=(90, 70, 30, 255))
        elif prop == "heart_burst_radial":
            for i in range(10):
                ang = rnd.random() * 6.28
                rr = 70 + rnd.randint(0, 90)
                hx = cx + int(math.cos(ang) * rr)
                hy = cy + int(math.sin(ang) * rr)
                self._heart(draw, hx, hy, rnd.randint(14, 22), fill=(255, 100, 150, 200))
        elif prop == "tiny_heart_lips":
            self._heart(draw, cx + 38, cy + rh // 4, 16, fill=(255, 140, 170, 230))
            self._heart(draw, cx - 44, cy + rh // 4 + 8, 14, fill=(255, 160, 185, 220))
        elif prop == "table":
            ty = min(oy + rh - 8, h - 120)
            draw.rounded_rectangle(
                (40, ty, w - 40, ty + 28),
                radius=8,
                fill=(200, 175, 140, 255),
                outline=(70, 55, 40, 255),
                width=6,
            )
            for tx in (70, w - 90):
                draw.rectangle((tx, ty + 28, tx + 18, ty + 70), fill=(120, 95, 70, 255), outline=(50, 40, 30, 255), width=3)
        elif prop == "cushion":
            cy0 = min(oy + rh - 30, h - 100)
            draw.rounded_rectangle(
                (ox - 40, cy0, ox + rw + 40, cy0 + 56),
                radius=22,
                fill=(230, 210, 240, 255),
                outline=(120, 90, 130, 255),
                width=6,
            )
            draw.rounded_rectangle(
                (ox - 20, cy0 + 10, ox + rw + 20, cy0 + 46),
                radius=16,
                fill=(250, 235, 255, 120),
                outline=None,
            )
        elif prop == "heart_shower":
            for i in range(14):
                t = i / 13.0
                hx = cx - 140 + int(280 * t)
                hy = oy - 20 - int(math.sin(t * 3.14) * 60) + rnd.randint(-8, 8)
                self._heart(draw, hx, hy, rnd.randint(14, 24), fill=(255, 90, 130, 210))
                self._heart(draw, hx + 36, hy + 50, rnd.randint(10, 18), fill=(255, 140, 170, 180))
        elif prop == "anger_cross":
            self._anger_veins(draw, cx - 20, oy + int(rh * 0.28))
            self._flash_lines(draw, cx + rw // 3, oy + rh // 6, rnd)

        if cut == "09":
            self._question_bubble(draw, w // 2, 46)

    def _heart(
        self,
        draw: ImageDraw.ImageDraw,
        cx: int,
        cy: int,
        size: int,
        fill: tuple[int, int, int, int],
    ) -> None:
        r = max(4, size // 2)
        left = (cx - r, cy - r, cx, cy + r)
        right = (cx, cy - r, cx + r, cy + r)
        draw.ellipse(left, fill=fill)
        draw.ellipse(right, fill=fill)
        draw.polygon(
            [(cx - r, cy), (cx + r, cy), (cx, cy + int(r * 1.45))],
            fill=fill,
        )

    def _anger_veins(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        for ang in (-40, -5, 32):
            rad = math.radians(ang)
            x1 = x + int(math.cos(rad) * 10)
            y1 = y + int(math.sin(rad) * 10)
            x2 = x + int(math.cos(rad) * 52)
            y2 = y + int(math.sin(rad) * 52)
            draw.line((x1, y1, x2, y2), fill=(175, 60, 200, 240), width=7)

    def _flash_lines(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        rnd: random.Random,
    ) -> None:
        for _ in range(6):
            ang = rnd.random() * 6.28
            r2 = 20 + rnd.randint(0, 35)
            x2 = x + int(math.cos(ang) * r2)
            y2 = y + int(math.sin(ang) * r2)
            draw.line((x, y, x2, y2), fill=(255, 220, 100, 200), width=4)

    def _question_bubble(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        font = self._try_load_font(52)
        draw.text((x, y), "?", fill=(100, 120, 200, 255), font=font, anchor="mm")

    def _draw_expression_overlays(
        self,
        draw: ImageDraw.ImageDraw,
        item: dict[str, Any],
        ox: int,
        oy: int,
        rw: int,
        rh: int,
    ) -> None:
        """Simple geometric overlays preserving underlying asset identity."""
        cut = str(item.get("id", ""))
        face = str(item.get("facial_expression", ""))
        cx = ox + rw // 2
        ey = oy + int(rh * 0.36)

        if cut in {"04", "10"} or ("감음" in face and cut not in {"07"}):
            for dx in (-48, 48):
                draw.arc(
                    (cx + dx - 36, ey - 20, cx + dx + 36, ey + 20),
                    start=0,
                    end=180,
                    fill=(72, 55, 50, 255),
                    width=6,
                )
        elif cut in {"07", "16"}:
            for dx in (-46, 46):
                draw.ellipse((cx + dx - 26, ey - 30, cx + dx + 26, ey + 12), outline=(55, 120, 200, 255), width=5)
                draw.ellipse((cx + dx - 10, ey - 12, cx + dx + 6, ey + 8), fill=(40, 60, 90, 240))
        elif cut == "06" or "옆눈" in face:
            draw.ellipse(
                (cx + 38, ey - 18, cx + 78, ey + 12),
                fill=(240, 240, 255, 220),
                outline=(50, 50, 70, 255),
            )
            draw.ellipse((cx + 54, ey - 6, cx + 70, ey + 6), fill=(40, 50, 80, 250))
        elif cut == "05" or "빵빵" in face:
            for dx in (-58, 58):
                draw.ellipse(
                    (cx + dx - 30, oy + int(rh * 0.48) - 10, cx + dx + 10, oy + int(rh * 0.48) + 22),
                    fill=(255, 160, 170, 120),
                    outline=(200, 100, 120, 180),
                    width=2,
                )

        if cut == "08" or "오리입" in face or "입술" in face:
            mx = cx
            my = oy + int(rh * 0.52)
            draw.ellipse((mx - 28, my - 6, mx + 28, my + 18), fill=(255, 140, 160, 230), outline=(90, 55, 50, 255), width=3)

        if cut == "10":
            fz = self._try_load_font(26)
            for i, ch in enumerate("Zzz"):
                draw.text(
                    (cx + rw // 4 + i * 22, oy - 8 - i * 16),
                    ch,
                    fill=(130, 130, 200, 230),
                    font=fz,
                )

        if cut == "12" or "접힘" in face:
            for sign in (-1, 1):
                draw.arc(
                    (cx + sign * 86 - 20, oy + 32, cx + sign * 86 + 26, oy + 80),
                    start=200,
                    end=340,
                    fill=(60, 50, 50, 230),
                    width=5,
                )

    def _draw_caption(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        item: dict[str, Any],
        w: int,
        h: int,
        rnd: random.Random,
    ) -> None:
        pos = str(item.get("text_position", "bottom")).lower().strip()
        if pos == "none":
            return

        fs = 42 if len(text) <= 3 else (36 if len(text) <= 5 else 32)
        font = self._try_load_font(fs)
        ox, oy = w // 2, h // 2

        pad = 48
        if pos == "top":
            oy = pad + 22
            ox = w // 2
        elif pos == "bottom":
            oy = h - pad - 6
            ox = w // 2
        elif pos == "left":
            ox = pad + 20
            oy = h // 2 + rnd.randint(-10, 10)
        elif pos == "right":
            ox = w - pad - 20
            oy = h // 2 + rnd.randint(-10, 10)

        self._draw_outlined_text(
            draw,
            (ox, oy),
            text,
            font,
            fill=self._TEXT_FILL,
            outline=self._TEXT_OUTLINE,
            width=max(5, fs // 7),
        )

    def _draw_fallback_cat(self, text: str, item_id: str, *, no_ai_text: bool = True) -> Image.Image:
        """Legacy circular mock when no usable reference file exists."""
        w, h = self._size
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        cx, cy = w // 2, int(h * 0.48)
        face_r = min(w, h) // 5

        draw.ellipse(
            (cx - face_r, cy - face_r, cx + face_r, cy + face_r),
            fill=(255, 228, 210, 255),
            outline=(120, 90, 80, 255),
            width=6,
        )

        ear = int(face_r * 0.9)
        draw.polygon(
            [(cx - face_r, cy - face_r + 10), (cx - face_r - ear // 2, cy - face_r - ear), (cx, cy - face_r)],
            fill=(255, 210, 190, 255),
            outline=(120, 90, 80, 255),
        )
        draw.polygon(
            [(cx + face_r, cy - face_r + 10), (cx + face_r + ear // 2, cy - face_r - ear), (cx, cy - face_r)],
            fill=(255, 210, 190, 255),
            outline=(120, 90, 80, 255),
        )

        eye_dx = face_r // 2
        eye_y = cy - face_r // 6
        for ex in (cx - eye_dx, cx + eye_dx):
            draw.ellipse((ex - 18, eye_y - 22, ex + 18, eye_y + 10), fill=(40, 40, 60, 255))

        draw.polygon(
            [(cx, cy + 6), (cx - 12, cy + 26), (cx + 12, cy + 26)],
            fill=(255, 140, 160, 255),
            outline=(120, 90, 80, 255),
        )

        whisk_y = cy + 18
        for sign in (-1, 1):
            for i in range(3):
                yy = whisk_y + i * 10
                x0 = cx + sign * (face_r // 2)
                x1 = x0 + sign * (face_r + 30 + i * 10)
                draw.line((x0, yy, x1, yy + (i - 1) * 4), fill=(80, 60, 50, 255), width=3)

        draw.arc((cx - 24, cy + 18, cx + 24, cy + 52), start=0, end=180, fill=(80, 60, 50, 255), width=4)

        if not no_ai_text:
            font = self._try_load_font(28)
            small = self._try_load_font(20)
            draw.text((24, 24), f"#{item_id}", fill=(60, 60, 80, 255), font=small)

            ty = int(h * 0.78)
            self._draw_outlined_text(
                draw,
                (cx, ty),
                text,
                font,
                fill=self._TEXT_FILL,
                outline=self._TEXT_OUTLINE,
                width=3,
            )

        return img

    def _try_load_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        import sys as _sys
        if _sys.platform == "darwin":
            platform_fonts: tuple[str, ...] = (
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            )
        elif _sys.platform == "win32":
            platform_fonts = ("malgun.ttf", "Malgun.ttf")
        else:
            platform_fonts = (
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                "/usr/share/fonts/nanum/NanumGothic.ttf",
            )
        for name in (*platform_fonts, "arial.ttf", "Arial.ttf"):
            try:
                return ImageFont.truetype(name, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _draw_outlined_text(
        self,
        draw: ImageDraw.ImageDraw,
        xy: tuple[float, float],
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        fill: tuple[int, int, int, int],
        outline: tuple[int, int, int, int] = (255, 255, 255, 255),
        width: int = 3,
    ) -> None:
        x, y = xy
        for dx in range(-width, width + 1):
            for dy in range(-width, width + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text(
                    (x + dx, y + dy),
                    text,
                    font=font,
                    fill=outline,
                    anchor="mm",
                )
        draw.text((x, y), text, font=font, fill=fill, anchor="mm")
class OpenAIMissingKeyError(RuntimeError):
    """OPENAI_API_KEY 미설정."""


def _serialize_usage(resp):
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    return getattr(usage, "__dict__", None)


_FALLBACK_CUT_WARNING = (
    "[경고] 이미지 참조 없이 텍스트 생성으로 폴백되어 컷 결과가 달라질 수 있습니다 "
    "(예: 고양이→강아지)."
)


def _prepare_image_bytes_for_edit(path: Path) -> io.BytesIO:
    """PNG/RGBA, max side 1024 — ``images.edit`` 입력용."""
    img = Image.open(path).convert("RGBA")
    max_side = 1024
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    bio = io.BytesIO()
    img.save(bio, format="PNG", optimize=True)
    bio.seek(0)
    bio.name = "input.png"  # 항상 .png — 내용도 PNG이므로 MIME 일치 필수
    return bio


class OpenAIImageGenerator(BaseImageGenerator):
    """OpenAI Images: 참조 이미지가 있으면 ``images.edit`` 우선 (후보 생성과 동일 정책)."""

    _SUFFIX_NO_AI_TEXT = (
        "중요: 알파 채널이 있는 투명 PNG, 깔끔한 플랫 스티커 일러스트, 비실사·단순 손그림 스타일. "
        "한글·영문·캡션·워터마크·로고·글자 형태 기호는 그리지 마. "
        "나중에 소프트웨어로 문구를 올릴 여백을 비워 둬. 배경은 단순하게."
    )
    _SUFFIX_AI_TEXT = (
        "중요: 알파 채널이 있는 투명 PNG, 깔끔한 플랫 스티커 일러스트, 비실사·단순 손그림 스타일. "
        "워터마크·로고·요청한 문구 외 추가 글자는 넣지 마. 배경은 단순하게."
    )
    # images.edit 그리드용: 스타일 지시 최소화 — 참조 이미지가 스타일을 정의함
    _SUFFIX_EDIT_GRID = (
        "글자·워터마크·텍스트 없음. 배경 단순하게."
    )

    def __init__(
        self,
        model: str = "gpt-image-1",
        size: str = "1024x1024",
        retries: int = 3,
        *,
        openai_mode: str = "auto",
        no_ai_text: bool = True,
    ) -> None:
        self.model = model
        self.size = size
        self.retries = max(1, int(retries))
        self.openai_mode = (openai_mode or "auto").strip().lower()
        self.no_ai_text = bool(no_ai_text)
        self.last_attempt_logs: list[dict] = []

    def _try_edit_first(self) -> bool:
        if self.openai_mode == "edit":
            return True
        if self.openai_mode == "generate":
            return False
        return True

    def _edit_api_model(self) -> str:
        m = self.model.strip().lower()
        if m.startswith("dall-e"):
            return "dall-e-2" if "dall-e-2" in m or m == "dall-e" else self.model
        return self.model

    def _generate_kwargs(self, prompt: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "prompt": prompt,
            "size": self.size,
            "n": 1,
        }

    def _require_key(self) -> None:
        key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if not key:
            raise OpenAIMissingKeyError(
                "OPENAI_API_KEY 가 설정되어 있지 않습니다. "
                ".env 또는 환경변수 OPENAI_API_KEY 를 설정하세요 (.env.example 참고)."
            )
        os.environ["OPENAI_API_KEY"] = key

    def generate(
        self,
        prompt: str,
        output_path: Path,
        text: str,
        item_id: str,
        reference_path: Path | None = None,
        item: dict | None = None,
    ) -> Path:
        import sys

        from openai import OpenAI

        _ = item
        self._require_key()
        self.last_attempt_logs = []
        output_path.parent.mkdir(parents=True, exist_ok=True)

        suffix = self._SUFFIX_NO_AI_TEXT if self.no_ai_text else self._SUFFIX_AI_TEXT
        composed = (
            prompt.strip()
            + "\n\n[AI 렌더 규칙]\n"
            + suffix
            + "\n컷 id "
            + str(item_id)
            + "."
        )
        if not self.no_ai_text:
            composed += (
                "\n스티커 문구(정확히 한 번): «"
                + text
                + "»."
            )

        rf = Path(reference_path) if reference_path else None
        ref_ok = rf is not None and rf.is_file()
        client = OpenAI()

        edit_prompt = (
            composed
            + "\n첨부된 참조 이미지와 동일한 종·얼굴·색·무늬의 캐릭터로 유지해줘. "
            "강아지·곰·다른 동물·다른 사람으로 바꾸지 마. "
            "포즈·표정·소품·구도만 이 컷 설명대로 바꿔줘. "
            "스티커 바깥 배경은 완전 투명(알파) 또는 흰색."
        )
        gen_prompt = (
            composed
            + "\n시리즈 바이블에 맞는 스티커 이미지 한 장을 생성해줘 "
            "(위에서 글자 금지를 요청했다면 텍스트 없이)."
        )

        outer_last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            atn = attempt

            def record(
                phase: str,
                ok: bool,
                ms: float,
                err: BaseException | None,
                resp,
                extras: dict[str, Any] | None = None,
            ) -> None:
                row: dict[str, Any] = {
                    "attempt": atn,
                    "phase": phase,
                    "success": ok,
                    "latency_ms": round(ms, 2),
                    "wall_seconds": round(ms / 1000.0, 4),
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "usage": _serialize_usage(resp) if resp is not None else None,
                    "error": None
                    if err is None
                    else "".join(
                        traceback.format_exception_only(type(err), err)
                    ).strip(),
                }
                if extras:
                    row.update(extras)
                self.last_attempt_logs.append(row)

            try_edit = ref_ok and self._try_edit_first()
            if try_edit:
                assert rf is not None
                st = time.perf_counter()
                try:
                    bio = _prepare_image_bytes_for_edit(rf)
                    em = self._edit_api_model()
                    resp = client.images.edit(
                        model=em,
                        image=bio,
                        prompt=edit_prompt[:3900],
                        n=1,
                        size=self.size or "1024x1024",
                    )
                    self._decode_response(resp, output_path)
                    record(
                        "images.edit",
                        True,
                        (time.perf_counter() - st) * 1000,
                        None,
                        resp,
                        extras={"edit_model": em, "reference_file": rf.name},
                    )
                    print(
                        f"[OpenAI 컷 {item_id}] images.edit 사용 (참조: {rf.name})",
                        file=sys.stderr,
                    )
                    return output_path.resolve()
                except Exception as e:
                    outer_last = e
                    record(
                        "images.edit",
                        False,
                        (time.perf_counter() - st) * 1000,
                        e,
                        None,
                        extras={"edit_model": self._edit_api_model()},
                    )
                    print(
                        f"[OpenAI 컷 {item_id}] images.edit 실패 → images.generate "
                        f"({attempt}/{self.retries}): {e!r}",
                        file=sys.stderr,
                    )

            stg = time.perf_counter()
            try:
                try:
                    resp = client.images.generate(**self._generate_kwargs(gen_prompt))
                except TypeError:
                    resp = client.images.generate(
                        model=self.model,
                        prompt=gen_prompt,
                        size=self.size,  # type: ignore[arg-type]
                        n=1,
                    )
                self._decode_response(resp, output_path)
                prev_edit_failed = bool(
                    try_edit
                    and self.last_attempt_logs
                    and self.last_attempt_logs[-1].get("phase") == "images.edit"
                    and not self.last_attempt_logs[-1].get("success")
                )
                record(
                    "images.generate",
                    True,
                    (time.perf_counter() - stg) * 1000,
                    None,
                    resp,
                    extras={"fallback_after_edit_failure": True}
                    if prev_edit_failed
                    else None,
                )
                fb_note = " (images.edit 실패 후 폴백)" if prev_edit_failed else ""
                if prev_edit_failed:
                    print(_FALLBACK_CUT_WARNING, file=sys.stderr)
                elif not try_edit:
                    print(
                        f"[OpenAI 컷 {item_id}] 참조 이미지 없음 → images.generate",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"[OpenAI 컷 {item_id}] images.generate 사용{fb_note}",
                        file=sys.stderr,
                    )
                return output_path.resolve()
            except Exception as e:
                outer_last = e
                record(
                    "images.generate",
                    False,
                    (time.perf_counter() - stg) * 1000,
                    e,
                    None,
                )
                print(
                    f"[OpenAI 컷 {item_id}] images.generate 실패 {attempt}/{self.retries}: {e!r}",
                    file=sys.stderr,
                )

            if attempt < self.retries:
                time.sleep(min(8.0, 2**attempt))

        raise RuntimeError(
            f"[컷 {item_id}] OpenAI 이미지 생성 실패: {outer_last!s}"
        ) from outer_last

    # ──────────────────────────────────────────────────────────────────
    # 그리드 모드: 16컷을 4×4 스프라이트 시트 1장으로 생성 후 크롭
    # ──────────────────────────────────────────────────────────────────
    def generate_grid(
        self,
        cut_payloads: list[dict],
        raw_out_dir: Path,
        reference_path: Path | None = None,
    ) -> tuple[dict[str, Path], list[str]]:
        """16컷을 4×4 그리드 이미지 1장(API 1회)으로 생성 후 개별 셀 크롭.

        Args:
            cut_payloads: [{"item": dict, "prompt": str}, ...] (최대 16개)
            raw_out_dir:  크롭된 셀 PNG를 저장할 디렉터리
            reference_path: 참조 캐릭터 이미지 경로 (프롬프트 힌트용, 현재 images.generate 사용)

        Returns:
            (succeeded={cut_id: path}, failed=[cut_id, ...])
        """
        import sys as _sys
        from openai import OpenAI

        self._require_key()
        raw_out_dir.mkdir(parents=True, exist_ok=True)
        self.last_attempt_logs = []

        ROWS, COLS = 4, 4
        cuts = cut_payloads[: ROWS * COLS]

        # ── 1. 프롬프트 구성 ──────────────────────────────────────────
        # text-only(generate) 모드 전용: 첫 번째 컷의 캐릭터 정체성 블록
        base_prompt = (cuts[0]["prompt"] if cuts else "").strip()

        cell_lines: list[str] = []
        for idx, row in enumerate(cuts):
            it = row["item"]
            r_num, c_num = divmod(idx, COLS)
            r_num += 1
            c_num += 1
            emotion   = str(it.get("emotion", ""))
            body_pose = str(it.get("body_pose", ""))
            action    = str(it.get("action", ""))
            prop      = str(it.get("prop", "none"))
            prop_note = f", prop={prop}" if prop and prop.lower() not in ("none", "") else ""
            cell_lines.append(
                f"Cell{idx + 1:02d}({r_num}r{c_num}c):"
                f" {emotion} / {body_pose} / {action}{prop_note}"
            )

        suffix = self._SUFFIX_NO_AI_TEXT if self.no_ai_text else self._SUFFIX_AI_TEXT

        # images.edit용 그리드 레이아웃: 스타일 지시 최소화 (참조 이미지가 스타일을 정의)
        edit_grid_layout = (
            "\n\n[4×4 스프라이트 시트 — 엄격한 셀 규칙]\n"
            "캔버스: 1024×1024px. 정확히 4열×4행=16칸으로 분할. 각 셀=256×256px.\n"
            "★ 핵심 규칙: 각 캐릭터는 반드시 자신의 셀 안에 완전히 들어와야 함.\n"
            "  - 머리끝~(허리 또는 상체 하단)이 모두 256×256px 셀 경계 안에 포함.\n"
            "  - 셀 경계(x=256, 512, 768 / y=256, 512, 768)를 절대 넘으면 안 됨.\n"
            "  - 뷰: 상반신 위주(얼굴+어깨+상체). 전신 표현 금지.\n"
            "  - 캐릭터 실제 그림 크기: 셀의 75% 이하 (최대 192×192px). 상하좌우 여백 32px+.\n"
            "모든 셀에서 동일한 캐릭터(종·얼굴·색·무늬 고정), 포즈·표정만 컷별 변경.\n"
            "셀 순서: 좌→우, 위→아래 (Cell01=1행1열 … Cell16=4행4열).\n"
            "배경: 흰색. 구분선·번호·텍스트 없음.\n\n"
            + "\n".join(cell_lines)
            + "\n\n"
            + self._SUFFIX_EDIT_GRID
        )

        # images.generate용 그리드 레이아웃: 스타일 suffix 포함
        gen_grid_layout = (
            "\n\n[4×4 스프라이트 시트 — 엄격한 셀 규칙]\n"
            "캔버스: 1024×1024px. 정확히 4열×4행=16칸으로 분할. 각 셀=256×256px.\n"
            "★ 핵심 규칙: 각 캐릭터는 반드시 자신의 셀 안에 완전히 들어와야 함.\n"
            "  - 머리끝~상체가 모두 셀 경계 안에 포함. 전신 금지.\n"
            "  - 캐릭터 크기 셀의 75% 이하, 여백 32px+.\n"
            "모든 셀 동일 캐릭터, 포즈·표정만 변경. 셀 순서: 좌→우, 위→아래.\n\n"
            + "\n".join(cell_lines)
            + "\n\n[AI 렌더 규칙]\n"
            + suffix
        )

        # images.edit용: 단순 직접 프롬프트 — 참조 이미지가 캐릭터를 정의, 스타일 묘사 최소화
        edit_base = (
            "첨부된 참조 이미지의 캐릭터를 그대로 사용해줘.\n"
            "캐릭터의 외모(얼굴형·눈·헤어스타일·색상·아트 스타일)를 참조 이미지와 완전히 동일하게 유지.\n"
            "강아지·고양이·곰·다른 동물로 절대 바꾸지 마. 참조 이미지 속 캐릭터 그대로.\n"
            "포즈·표정·감정만 각 셀 지시에 따라 변경.\n"
        )
        edit_composed = edit_base + edit_grid_layout

        # images.generate용 (text-only): base_prompt 포함
        composed = base_prompt + gen_grid_layout

        # ── 2. API 호출 (images.edit 우선, 실패 시 images.generate 폴백) ──
        grid_size = "1024x1024"
        client = OpenAI()
        tmp_grid = raw_out_dir / "_grid_raw.png"

        rf = Path(reference_path) if reference_path else None
        ref_ok = rf is not None and rf.is_file() and self._try_edit_first()

        outer_exc: Exception | None = None
        call_ok = False
        for attempt in range(1, self.retries + 1):
            st = time.perf_counter()
            try:
                if ref_ok:
                    assert rf is not None
                    bio = _prepare_image_bytes_for_edit(rf)
                    em = self._edit_api_model()
                    resp = client.images.edit(
                        model=em,
                        image=bio,
                        prompt=edit_composed[:16000],
                        n=1,
                        size=grid_size,
                        quality="high",
                    )
                    phase = "grid.edit"
                    phase_label = f"images.edit (참조: {rf.name})"
                else:
                    resp = client.images.generate(
                        model=self.model,
                        prompt=composed[:4000],
                        size=grid_size,
                        n=1,
                        quality="high",
                    )
                    phase = "grid.generate"
                    phase_label = "images.generate"
                ms = (time.perf_counter() - st) * 1000
                self.last_attempt_logs.append(
                    {
                        "attempt": attempt,
                        "phase": phase,
                        "success": True,
                        "latency_ms": round(ms, 2),
                        "wall_seconds": round(ms / 1000.0, 4),
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "usage": _serialize_usage(resp),
                        "grid_size": grid_size,
                        "cells": len(cuts),
                    }
                )
                self._decode_response(resp, tmp_grid)
                print(
                    f"[그리드] {phase_label} 완료 ({ms / 1000:.1f}s, {grid_size}, {len(cuts)}셀)",
                    file=_sys.stderr,
                )
                call_ok = True
                break
            except Exception as e:
                ms = (time.perf_counter() - st) * 1000
                outer_exc = e
                # images.edit 실패 → images.generate 로 폴백
                if ref_ok:
                    print(
                        f"[그리드] images.edit 실패 → images.generate 폴백: {e!r}",
                        file=_sys.stderr,
                    )
                    ref_ok = False
                    continue
                self.last_attempt_logs.append(
                    {
                        "attempt": attempt,
                        "phase": "grid.generate",
                        "success": False,
                        "latency_ms": round(ms, 2),
                        "wall_seconds": round(ms / 1000.0, 4),
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "error": "".join(
                            traceback.format_exception_only(type(e), e)
                        ).strip(),
                    }
                )
                print(
                    f"[그리드] attempt {attempt}/{self.retries} 실패: {e!r}",
                    file=_sys.stderr,
                )
                if attempt < self.retries:
                    time.sleep(min(8.0, 2**attempt))

        if not call_ok:
            raise RuntimeError(
                f"[그리드] OpenAI 그리드 이미지 생성 실패: {outer_exc!s}"
            ) from outer_exc

        # ── 3. 셀 크롭 ───────────────────────────────────────────────
        succeeded: dict[str, Path] = {}
        failed: list[str] = []

        try:
            grid_img = Image.open(tmp_grid).convert("RGBA")
            gw, gh = grid_img.size
            cell_w = gw // COLS
            cell_h = gh // ROWS
            print(
                f"[그리드] 그리드 {gw}×{gh}px → 셀 {cell_w}×{cell_h}px",
                file=_sys.stderr,
            )

            # 스마트 크롭: 각 셀에 bleed 영역 포함 후 cell_w×cell_h 로 리사이즈
            # AI가 셀 경계를 약간 넘기는 경우 잘리지 않도록 ±BLEED px 확장 크롭
            BLEED = 20
            for idx, row in enumerate(cuts):
                cid = str(row["item"].get("id", f"{idx + 1:02d}"))
                r, c = divmod(idx, COLS)
                x0 = max(0, c * cell_w - BLEED)
                y0 = max(0, r * cell_h - BLEED)
                x1 = min(gw, c * cell_w + cell_w + BLEED)
                y1 = min(gh, r * cell_h + cell_h + BLEED)
                try:
                    cell = grid_img.crop((x0, y0, x1, y1))
                    # 원래 셀 크기(cell_w×cell_h)로 리사이즈 → 블리드가 있으면 약간 축소
                    cell = cell.resize((cell_w, cell_h), Image.Resampling.LANCZOS)
                    cell_path = raw_out_dir / f"{cid}.png"
                    cell.save(cell_path, format="PNG")
                    succeeded[cid] = cell_path
                except Exception as crop_e:
                    print(
                        f"[그리드] 셀 {cid} 크롭 실패: {crop_e!r}",
                        file=_sys.stderr,
                    )
                    failed.append(cid)

            print(
                f"[그리드] 크롭 완료: {len(succeeded)}성공 / {len(failed)}실패",
                file=_sys.stderr,
            )
        except Exception as e:
            print(
                f"[그리드] 크롭 전체 실패: {e!r} — 전체 컷 fallback",
                file=_sys.stderr,
            )
            failed = [
                str(row["item"].get("id", f"{i + 1:02d}"))
                for i, row in enumerate(cuts)
            ]
            succeeded = {}

        return succeeded, failed

    def _decode_response(self, resp, output_path: Path) -> None:
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
                headers={"User-Agent": "KakaoEmoticonFactory/1 (OpenAI image download)"},
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read()
        if not raw:
            raise RuntimeError(
                "OpenAI 이미지 페이로드 없음(b64_json · url 모두 없음)"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(raw)


def create_image_generator(
    backend: str,
    *,
    openai_model: str = "gpt-image-1",
    openai_size: str = "1024x1024",
    openai_retries: int = 3,
    openai_mode: str = "auto",
    no_ai_text: bool = True,
) -> BaseImageGenerator:
    k = backend.strip().lower()
    if k == "mock":
        return MockImageGenerator()
    if k == "openai":
        return OpenAIImageGenerator(
            model=openai_model,
            size=openai_size,
            retries=int(openai_retries),
            openai_mode=openai_mode,
            no_ai_text=no_ai_text,
        )
    raise ValueError(f"지원하지 않는 generator: {backend!r}")
