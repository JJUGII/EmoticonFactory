"""OpenCV heuristic: detect face-heavy / low-body compositions for auto rerender."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BodyVisibilityScore:
    score: float
    face_body_ratio: float
    lower_band_activity: float
    rerender: bool


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def body_visibility_rerender_enabled() -> bool:
    raw = (os.getenv("COMFYUI_BODY_VISIBILITY_RERENDER") or "true").strip().lower()
    return raw not in ("0", "false", "off", "no")


def min_body_visibility_score() -> float:
    return _env_float("COMFYUI_BODY_VISIBILITY_MIN", 0.35)


def score_body_visibility(image_path: Path) -> BodyVisibilityScore:
    """
    Heuristic 0–1: higher = more full-body / limb visibility (better for stickers).

    Uses alpha bbox + vertical mass distribution (no ML).
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return BodyVisibilityScore(
            score=1.0,
            face_body_ratio=0.0,
            lower_band_activity=1.0,
            rerender=False,
        )

    p = Path(image_path)
    if not p.is_file():
        return BodyVisibilityScore(0.0, 1.0, 0.0, True)

    from services.image_io import pil_open_image

    im = pil_open_image(p).convert("RGBA")
    arr = np.array(im)
    h, w = arr.shape[:2]
    if h < 8 or w < 8:
        return BodyVisibilityScore(0.5, 0.5, 0.5, False)

    alpha = arr[:, :, 3]
    mask = alpha > 32
    if not mask.any():
        gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGBA2BGR)
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)

    ys, xs = np.where(mask)
    if len(ys) < 50:
        return BodyVisibilityScore(0.2, 0.9, 0.1, True)

    y_min, y_max = int(ys.min()), int(ys.max())
    x_min, x_max = int(xs.min()), int(xs.max())
    body_h = max(1, y_max - y_min)
    body_w = max(1, x_max - x_min)

    # Tall narrow bbox → portrait-like
    aspect = body_h / max(body_w, 1)
    face_body_ratio = min(1.0, max(0.0, (aspect - 1.1) / 1.4))

    # Mass in lower 35% (legs/feet) vs upper 35% (face)
    upper = mask[y_min : y_min + max(1, body_h // 3), x_min : x_max + 1].sum()
    lower = mask[y_max - max(1, body_h // 3) : y_max + 1, x_min : x_max + 1].sum()
    total = max(1, mask[y_min : y_max + 1, x_min : x_max + 1].sum())
    lower_band_activity = float(lower) / float(total)
    upper_band_activity = float(upper) / float(total)

    # Score: reward lower-body mass, penalize extreme vertical crop
    score = 0.45 * lower_band_activity + 0.35 * min(1.0, body_h / h) + 0.20 * (
        1.0 - face_body_ratio
    )
    score = max(0.0, min(1.0, score))

    rerender = False
    if body_visibility_rerender_enabled():
        rerender = score < min_body_visibility_score() and face_body_ratio > 0.55

    return BodyVisibilityScore(
        score=round(score, 3),
        face_body_ratio=round(face_body_ratio, 3),
        lower_band_activity=round(lower_band_activity, 3),
        rerender=rerender,
    )


def log_body_visibility(cut_id: str, result: BodyVisibilityScore) -> None:
    print(
        f"[BODY_VISIBILITY] cut={cut_id} score={result.score:.2f} "
        f"face_body_ratio={result.face_body_ratio:.2f} "
        f"lower_band={result.lower_band_activity:.2f} rerender={str(result.rerender).lower()}",
        file=sys.stderr,
    )
