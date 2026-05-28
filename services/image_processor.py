"""Resize, pad, and export PNG assets for Kakao-style packages."""

# TODO(v0.2): optional animated WebP export path (3 required motions, <=24 frames,
# 4 loops, last frame equals representative static, WebP <= 1 MiB).

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from config import (
    EMOTICON_SIZE,
    ICON_SIZE,
    MAX_EMOTICON_BYTES,
    MAX_ICON_BYTES,
    MAX_SHARE_BYTES,
    SHARE_SIZE,
)
from services.image_io import pil_open_image, pil_save_image


def draw_text_with_white_outline(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int, int] = (50, 50, 70, 255),
    outline: tuple[int, int, int, int] = (255, 255, 255, 255),
    outline_width: int = 2,
    anchor: str = "lt",
) -> None:
    """Draw ``text`` with a simple multi-direction outline (sticker caption)."""
    x, y = xy
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=outline, anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)


class ImageProcessor:
    """Normalize emoticons and derive icon/share PNGs with size/byte guards."""

    def __init__(self) -> None:
        self.emoticon_size = EMOTICON_SIZE
        self.icon_size = ICON_SIZE
        self.share_size = SHARE_SIZE

    def normalize_emoticon(self, path: Path) -> Path:
        """Fit ``path`` into RGBA ``EMOTICON_SIZE`` canvas (contain, centered)."""
        return self.normalize_emoticon_to(path, path)

    def normalize_emoticon_to(self, source_path: Path, dest_path: Path) -> Path:
        """Read ``source_path``, normalize to sticker canvas, write ``dest_path``."""
        target_w, target_h = self.emoticon_size
        im = pil_open_image(source_path).convert("RGBA")
        src_w, src_h = im.size
        scale = min(target_w / src_w, target_h / src_h)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        resized = im.resize((new_w, new_h), Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        ox = (target_w - new_w) // 2
        oy = (target_h - new_h) // 2
        canvas.paste(resized, (ox, oy), resized)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self._save_png_under_limit(canvas, dest_path, MAX_EMOTICON_BYTES)
        return dest_path

    def add_text_overlay(
        self,
        image_path: Path,
        output_path: Path,
        text: str,
        position: str,
        canvas_size: tuple[int, int] | None = None,
        font_path: Optional[Path] = None,
        fill: tuple[int, int, int, int] = (70, 50, 35, 255),
        stroke_fill: tuple[int, int, int, int] = (255, 255, 240, 255),
        stroke_width: int = 6,
    ) -> Path:
        """Draw Korean caption with thick outline; safe margins inside ``canvas_size``."""
        cw, ch = canvas_size or self.emoticon_size
        im = pil_open_image(image_path).convert("RGBA")
        if im.size != (cw, ch):
            im = im.resize((cw, ch), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(im)
        pos = (position or "bottom").strip().lower()
        if pos == "none" or not (text or "").strip():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._save_png_under_limit(im, output_path, MAX_EMOTICON_BYTES)
            return output_path

        t = str(text).strip()
        font = self._overlay_font(font_path, 56)

        def try_font(sz: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
            return self._overlay_font(font_path, sz)

        font_size = 56
        margin_x = 24
        max_w = cw - 2 * margin_x
        font = try_font(font_size)
        bbox = draw.textbbox((0, 0), t, font=font, anchor="mm")
        tw = bbox[2] - bbox[0]
        while tw > max_w and font_size > 16:
            font_size -= 2
            font = try_font(font_size)
            bbox = draw.textbbox((0, 0), t, font=font, anchor="mm")
            tw = bbox[2] - bbox[0]

        if pos == "top":
            cx, cy = cw // 2, 72
        elif pos == "left":
            cx, cy = int(cw * 0.22), ch // 2
        elif pos == "right":
            cx, cy = int(cw * 0.78), ch // 2
        else:
            cx, cy = cw // 2, int(ch - 95)

        try:
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
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx == 0 and dy == 0:
                        continue
                    draw.text((cx + dx, cy + dy), t, font=font, fill=stroke_fill, anchor="mm")
            draw.text((cx, cy), t, font=font, fill=fill, anchor="mm")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._save_png_under_limit(im, output_path, MAX_EMOTICON_BYTES)
        return output_path

    def _overlay_font(
        self, font_path: Optional[Path], size: int
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        import sys as _sys
        paths: list[Path] = []
        if font_path is not None:
            paths.append(Path(font_path))
        if _sys.platform == "darwin":
            paths.extend([
                Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
                Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
            ])
        elif _sys.platform == "win32":
            paths.extend([
                Path(r"C:\Windows\Fonts\malgunbd.ttf"),
                Path(r"C:\Windows\Fonts\malgun.ttf"),
            ])
        else:
            paths.extend([
                Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
                Path("/usr/share/fonts/nanum/NanumGothic.ttf"),
            ])
        for p in paths:
            if p.is_file():
                try:
                    return ImageFont.truetype(str(p), size=size)
                except OSError:
                    continue
        return self._font(size)

    def create_icon(self, source_path: Path, output_path: Path) -> Path:
        """Downscale ``source_path`` to ``ICON_SIZE`` RGBA PNG."""
        tw, th = self.icon_size
        im = pil_open_image(source_path).convert("RGBA")
        icon = im.resize((tw, th), Image.Resampling.LANCZOS)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._save_png_under_limit(icon, output_path, MAX_ICON_BYTES)
        return output_path

    def create_share_image(
        self, series_name: str, source_paths: list[Path], output_path: Path
    ) -> Path:
        """Build a 600x166 banner with title and a grid of small previews."""
        w, h = self.share_size
        img = Image.new("RGBA", (w, h), (250, 248, 255, 255))
        draw = ImageDraw.Draw(img)

        title_font = self._font(22)
        draw_text_with_white_outline(
            draw,
            (12, 8),
            series_name,
            title_font,
            fill=(70, 60, 110, 255),
            outline_width=2,
        )

        paths = sorted(
            (p for p in source_paths if Path(p).is_file()),
            key=lambda p: p.stem,
        )
        # Two rows of 8 thumbnails
        cols, rows = 8, 2
        margin_top = 44
        cell_w = (w - 16) // cols
        cell_h = (h - margin_top - 8) // rows
        thumb = max(1, min(cell_w - 4, cell_h - 4))

        for idx, p in enumerate(paths[: cols * rows]):
            r, c = divmod(idx, cols)
            cx = 8 + c * cell_w + (cell_w - thumb) // 2
            cy = margin_top + r * cell_h + (cell_h - thumb) // 2
            src = pil_open_image(p).convert("RGBA")
            sm = src.resize((thumb, thumb), Image.Resampling.LANCZOS)
            img.paste(sm, (cx, cy), sm)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._save_png_under_limit(img, output_path, MAX_SHARE_BYTES)
        return output_path

    def _font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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

    def _save_png_under_limit(self, image: Image.Image, path: Path, max_bytes: int) -> None:
        """Save PNG; if too large, retry with higher compression / optional downscale."""
        path.parent.mkdir(parents=True, exist_ok=True)
        pil_save_image(image, path, format="PNG", optimize=True, compress_level=9)
        if path.stat().st_size <= max_bytes:
            return

        # Second pass: quantize alpha-heavy stickers slightly (still RGBA)
        tmp = image.copy()
        if tmp.mode != "RGBA":
            tmp = tmp.convert("RGBA")
        pil_save_image(tmp, path, format="PNG", optimize=True, compress_level=9)
        if path.stat().st_size <= max_bytes:
            return

        # Last resort: scale down a few percent and center-paste back (rare for mock)
        factor = 0.92
        tw, th = tmp.size
        smaller = tmp.resize((max(1, int(tw * factor)), max(1, int(th * factor))), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", tmp.size, (0, 0, 0, 0))
        ox = (tmp.size[0] - smaller.size[0]) // 2
        oy = (tmp.size[1] - smaller.size[1]) // 2
        canvas.paste(smaller, (ox, oy), smaller)
        pil_save_image(canvas, path, format="PNG", optimize=True, compress_level=9)
