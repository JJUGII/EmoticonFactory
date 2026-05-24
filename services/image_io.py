"""Unicode-safe image I/O for Windows (e.g. Korean paths).

``cv2.imread`` / ``cv2.imwrite`` use narrow APIs on Windows and may fail on non-ASCII
paths. Use ``np.fromfile`` + ``cv2.imdecode`` and ``cv2.imencode`` + ``Path.write_bytes``.

Pillow may also fail on some legacy configurations; read via ``Path.read_bytes`` +
``BytesIO`` and write via in-memory ``save`` + ``Path.write_bytes``.
"""

from __future__ import annotations

import io
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np
from PIL import Image

from utils.files import is_junk_filename, is_valid_image_file, warn_skip_file


class ImageReadError(OSError):
    """Failed to read an image from disk."""

    def __init__(self, path: Path, detail: str) -> None:
        self.path = path.resolve()
        self.detail = detail
        super().__init__(f"{detail} — 파일: {self.path}")


class ImageWriteError(OSError):
    """Failed to write an image to disk."""

    def __init__(self, path: Path, detail: str) -> None:
        self.path = path.resolve()
        self.detail = detail
        super().__init__(f"{detail} — 파일: {self.path}")


def _as_path(path: Path | str) -> Path:
    return Path(path).expanduser()


def cv_imread(path: Path | str, flags: int = cv2.IMREAD_UNCHANGED) -> np.ndarray:
    """Read an image like ``cv2.imread`` but safe for Unicode paths (Windows)."""
    p = _as_path(path).resolve()
    if is_junk_filename(p.name):
        warn_skip_file(p, "AppleDouble/hidden file")
        raise ImageReadError(p, "AppleDouble 또는 숨김 메타파일입니다")
    if not p.is_file():
        raise ImageReadError(p, "이미지 파일이 없습니다.")
    try:
        raw = np.fromfile(str(p), dtype=np.uint8)
    except OSError as exc:
        raise ImageReadError(p, f"바이너리 읽기 실패: {exc}") from exc
    if raw.size == 0:
        raise ImageReadError(p, "파일이 비어 있습니다.")
    decoded = cv2.imdecode(raw, flags)
    if decoded is None:
        raise ImageReadError(
            p,
            "cv2.imdecode 실패(손상되었거나 지원하지 않는 형식)",
        )
    return decoded


def cv_imwrite(
    path: Path | str,
    img: np.ndarray,
    params: list[int] | None = None,
) -> None:
    """Write an image like ``cv2.imwrite`` but safe for Unicode paths."""
    p = _as_path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    suffix = p.suffix.lower()
    ext = suffix if suffix.startswith(".") else f".{suffix or 'png'}"
    ok, buf = cv2.imencode(ext, img, params or [])
    if not ok or buf is None:
        raise ImageWriteError(p, "cv2.imencode 실패")
    try:
        p.write_bytes(buf.tobytes())
    except OSError as exc:
        raise ImageWriteError(p, f"파일 쓰기 실패: {exc}") from exc


def pil_open_image(path: Path | str) -> Image.Image:
    """Open an image fully into memory (first frame / static)."""
    p = _as_path(path).resolve()
    if is_junk_filename(p.name):
        warn_skip_file(p, "AppleDouble/hidden file")
        raise ImageReadError(p, "AppleDouble 또는 숨김 메타파일입니다")
    if not p.is_file():
        raise ImageReadError(p, "이미지 파일이 없습니다.")
    try:
        if p.stat().st_size < 1:
            raise ImageReadError(p, "파일이 비어 있습니다.")
    except OSError as exc:
        raise ImageReadError(p, f"파일 정보 읽기 실패: {exc}") from exc
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise ImageReadError(p, f"바이너리 읽기 실패: {exc}") from exc
    if not data:
        raise ImageReadError(p, "파일이 비어 있습니다.")
    try:
        bio = io.BytesIO(data)
        im = Image.open(bio)
        im.load()
    except OSError as exc:
        raise ImageReadError(p, f"Pillow Image.open 실패: {exc}") from exc
    except Exception as exc:
        raise ImageReadError(p, f"이미지 형식을 인식할 수 없습니다: {exc}") from exc
    return im


@contextmanager
def pil_open_buffer(path: Path | str) -> Iterator[Image.Image]:
    """Open from memory for inspection (supports ``n_frames`` / ``seek``). Caller must finish inside ``with``."""
    p = _as_path(path).resolve()
    if is_junk_filename(p.name):
        warn_skip_file(p, "AppleDouble/hidden file")
        raise ImageReadError(p, "AppleDouble 또는 숨김 메타파일입니다")
    if not p.is_file():
        raise ImageReadError(p, "이미지 파일이 없습니다.")
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise ImageReadError(p, f"바이너리 읽기 실패: {exc}") from exc
    bio = io.BytesIO(data)
    im = Image.open(bio)
    try:
        yield im
    finally:
        im.close()


def pil_animation_frame_rgba(path: Path | str) -> list[Image.Image]:
    """Load every animation frame as an independent RGBA copy (multiframe GIF/WebP/APNG)."""
    frames: list[Image.Image] = []
    with pil_open_buffer(path) as holder:
        n = getattr(holder, "n_frames", 1)
        for i in range(n):
            holder.seek(i)
            frames.append(holder.copy().convert("RGBA"))
    return frames


def pil_save_image(image: Image.Image, path: Path | str, **kwargs: Any) -> None:
    """Save a Pillow image to ``path`` (supports ``save_all`` / ``append_images`` etc.)."""
    p = _as_path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    bio = io.BytesIO()
    try:
        image.save(bio, **kwargs)
    except OSError as exc:
        raise ImageWriteError(p, f"Pillow save 실패: {exc}") from exc
    try:
        p.write_bytes(bio.getvalue())
    except OSError as exc:
        raise ImageWriteError(p, f"파일 쓰기 실패: {exc}") from exc
