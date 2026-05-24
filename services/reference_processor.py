"""Normalize user reference PNG into 540×540 emoticon-ready character bases."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from config import EMOTICON_SIZE
from services.image_io import ImageReadError, pil_open_image, pil_save_image
from utils.files import is_junk_filename, warn_skip_file


class ReferenceProcessor:
    """Build standardized character assets without failing the main pipeline."""

    def __init__(self, canvas_size: tuple[int, int] | None = None) -> None:
        self._size = canvas_size or EMOTICON_SIZE

    def process(self, reference_path: Path, character_dir: Path) -> dict[str, Any]:
        """Create ``character_base*.png`` under ``character_dir``.

        Always attempts ``character_base.png`` (RGBA, transparent canvas) and
        ``character_base_white.png``. Writes ``character_base_transparent.png`` only when
        the source image has meaningful alpha.

        Returns:
            Dict with ``warnings`` (list[str]), ``paths`` (rel names or empty),
            and ``character_base_absolute`` optional Path for downstream use.
        """
        warnings: list[str] = []
        paths: dict[str, str] = {}
        cw, ch = self._size
        character_dir = Path(character_dir)
        character_dir.mkdir(parents=True, exist_ok=True)

        if not reference_path.is_file():
            warnings.append(f"참조 파일이 없습니다: {reference_path}")
            return {
                "warnings": warnings,
                "paths": paths,
                "character_base_absolute": None,
            }

        if is_junk_filename(reference_path.name):
            warn_skip_file(reference_path, "AppleDouble/hidden file")
            warnings.append(
                f"참조 이미지가 AppleDouble/숨김 파일입니다: {reference_path.resolve()}"
            )
            return {
                "warnings": warnings,
                "paths": paths,
                "character_base_absolute": None,
            }

        try:
            im = pil_open_image(reference_path).convert("RGBA")
        except (OSError, ImageReadError) as exc:
            warnings.append(
                f"참조 이미지를 열 수 없습니다: {reference_path.resolve()} ({exc})"
            )
            return {
                "warnings": warnings,
                "paths": paths,
                "character_base_absolute": None,
            }

        try:
            src_has_alpha = _has_meaningful_alpha(im)
            fitted = self._fit_center(im)
            ox = (cw - fitted.width) // 2
            oy = (ch - fitted.height) // 2

            base_transparent = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            base_transparent.paste(fitted, (ox, oy), fitted)

            base_path = character_dir / "character_base.png"
            pil_save_image(base_transparent, base_path, format="PNG")
            paths["character_base"] = "character/character_base.png"

            white = Image.new("RGBA", (cw, ch), (255, 255, 255, 255))
            white.paste(base_transparent, (0, 0), base_transparent)
            white_rgb = white.convert("RGB")
            white_path = character_dir / "character_base_white.png"
            pil_save_image(white_rgb, white_path, format="PNG")
            paths["character_base_white"] = "character/character_base_white.png"

            if src_has_alpha:
                tr_path = character_dir / "character_base_transparent.png"
                pil_save_image(base_transparent, tr_path, format="PNG")
                paths["character_base_transparent"] = (
                    "character/character_base_transparent.png"
                )
            else:
                warnings.append(
                    "참조에 유의미한 알파 채널이 없어 character_base_transparent.png 는 생략했습니다."
                )

        except OSError as exc:
            warnings.append(f"캐릭터 베이스 저장 실패: {exc}")

        abs_base = character_dir / "character_base.png"
        return {
            "warnings": warnings,
            "paths": paths,
            "character_base_absolute": abs_base if abs_base.is_file() else None,
        }

    def _fit_center(self, im: Image.Image) -> Image.Image:
        """Scale ``im`` to fit inside canvas (contain), preserving aspect."""
        cw, ch = self._size
        w, h = im.size
        if w <= 0 or h <= 0:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        scale = min(cw / w, ch / h)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        return im.resize((nw, nh), Image.Resampling.LANCZOS)


def _has_meaningful_alpha(im: Image.Image) -> bool:
    """True if any pixel alpha is below 255 (rough cutout detection)."""
    if im.mode != "RGBA":
        return False
    alpha = im.split()[3]
    lo, hi = alpha.getextrema()
    return lo < hi or lo < 255
