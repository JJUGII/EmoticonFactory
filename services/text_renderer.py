"""Pillow caption overlay — Pretendard Bold preferred, outline + shadow."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from config import EMOTICON_SIZE, MAX_EMOTICON_BYTES
from services.image_io import pil_open_image, pil_save_image

# macOS / project font search (Pretendard Bold)
_FONT_CANDIDATES: tuple[str, ...] = (
    "Pretendard-Bold.otf",
    "Pretendard-Bold.ttf",
    "PretendardBold.otf",
    "malgunbd.ttf",
    "Malgun Gothic Bold.ttf",
    "AppleSDGothicNeo-Bold.ttc",
    "AppleSDGothicNeo.ttc",
)

_FONT_DIRS: tuple[Path, ...] = (
    Path(__file__).resolve().parents[1] / "assets" / "fonts",
    Path.home() / "Library" / "Fonts",
    Path("/System/Library/Fonts"),
    Path("/Library/Fonts"),
    Path(r"C:\Windows\Fonts"),
)


def resolve_overlay_font(size: int, font_path: Optional[Path] = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if font_path is not None and Path(font_path).is_file():
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except OSError:
            pass
    if font_path is not None:
        p = Path(font_path)
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                pass
    for directory in _FONT_DIRS:
        if not directory.is_dir():
            continue
        for name in _FONT_CANDIDATES:
            candidate = directory / name
            if candidate.is_file():
                try:
                    return ImageFont.truetype(str(candidate), size=size)
                except OSError:
                    continue
    for name in ("malgunbd.ttf", "malgun.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_text_overlay(
    image_path: Path,
    output_path: Path,
    text: str,
    position: str,
    *,
    canvas_size: tuple[int, int] | None = None,
    font_path: Optional[Path] = None,
    fill: tuple[int, int, int, int] = (45, 40, 55, 255),
    stroke_fill: tuple[int, int, int, int] = (255, 255, 255, 255),
    stroke_width: int = 5,
    shadow_offset: tuple[int, int] = (2, 3),
    shadow_fill: tuple[int, int, int, int] = (0, 0, 0, 90),
) -> Path:
    """Draw Korean caption with outline + soft shadow; auto top/bottom placement."""
    cw, ch = canvas_size or EMOTICON_SIZE
    im = pil_open_image(image_path).convert("RGBA")
    if im.size != (cw, ch):
        im = im.resize((cw, ch), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(im)
    pos = (position or "bottom").strip().lower()
    t = (text or "").strip()
    if pos == "none" or not t:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _save(im, output_path)
        return output_path

    margin_x = 28
    max_w = cw - 2 * margin_x
    font_size = 58
    font = resolve_overlay_font(font_size, font_path)
    bbox = draw.textbbox((0, 0), t, font=font, anchor="mm")
    tw = bbox[2] - bbox[0]
    while tw > max_w and font_size > 18:
        font_size -= 2
        font = resolve_overlay_font(font_size, font_path)
        bbox = draw.textbbox((0, 0), t, font=font, anchor="mm")
        tw = bbox[2] - bbox[0]

    if pos == "top":
        cx, cy = cw // 2, 68
    elif pos == "left":
        cx, cy = int(cw * 0.22), ch // 2
    elif pos == "right":
        cx, cy = int(cw * 0.78), ch // 2
    else:
        cx, cy = cw // 2, int(ch - 92)

    sx, sy = shadow_offset
    try:
        draw.text(
            (cx + sx, cy + sy),
            t,
            font=font,
            fill=shadow_fill,
            anchor="mm",
        )
        draw.text(
            (cx, cy),
            t,
            font=font,
            fill=fill,
            anchor="mm",
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
    except TypeError:
        for layer_fill, ox, oy in (
            (shadow_fill, sx, sy),
            (stroke_fill, 0, 0),
            (fill, 0, 0),
        ):
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if layer_fill == fill and dx == 0 and dy == 0:
                        continue
                    if layer_fill != fill and (dx != 0 or dy != 0):
                        continue
                    draw.text((cx + dx + ox, cy + dy + oy), t, font=font, fill=layer_fill, anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save(im, output_path)
    return output_path


def _save(image: Image.Image, path: Path) -> None:
    pil_save_image(image, path, format="PNG", optimize=True, compress_level=9)
    if path.stat().st_size <= MAX_EMOTICON_BYTES:
        return
    pil_save_image(image, path, format="PNG", optimize=True, compress_level=9)
