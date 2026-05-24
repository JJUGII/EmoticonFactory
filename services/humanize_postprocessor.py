"""Conservative post-process to reduce AI/photo noise and nudge toward sticker look."""

from __future__ import annotations

import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from services.image_io import pil_open_image, pil_save_image

_STRENGTH_EPS = 1e-6


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


class HumanizePostProcessor:
    """Pillow + OpenCV pipeline: alpha cleanup, mild denoise, palette nudge, outline, encode."""

    def __init__(self, default_strength: float = 0.45) -> None:
        self.default_strength = _clamp01(default_strength)

    def process_image(
        self,
        input_path: Path,
        output_path: Path,
        strength: float | None = None,
    ) -> Path:
        """Read ``input_path`` RGBA PNG, write humanized RGBA to ``output_path``."""
        s = _clamp01(self.default_strength if strength is None else strength)
        if s <= _STRENGTH_EPS:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, output_path)
            return output_path

        im = pil_open_image(input_path).convert("RGBA")

        alpha = np.array(im.split()[-1], dtype=np.uint8)
        rgb = np.array(im.convert("RGB"), dtype=np.uint8)

        # --- Alpha: small speck cleanup + fringe soften (conservative)
        kernel = max(3, min(9, int(3 + round(4 * s))) | 1)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel, kernel))
        a_work = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, k, iterations=1)
        a_work = cv2.morphologyEx(a_work, cv2.MORPH_CLOSE, k, iterations=1)
        if s > 0.12:
            sig = float(0.35 + 0.55 * s)
            a_smooth = cv2.GaussianBlur(a_work, (0, 0), sigmaX=sig)
            beta = float(0.35 + 0.25 * s)
            alpha_u8 = cv2.addWeighted(
                a_work.astype(np.float32),
                1.0 - beta,
                a_smooth.astype(np.float32),
                beta,
                0.0,
            ).clip(0, 255).astype(np.uint8)
        else:
            alpha_u8 = a_work

        # --- Bilateral RGB (opaque + soft-edge region only; avoids global blur destroying text strokes)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        d = max(5, min(9, int(5 + round(2 * s)))) | 1
        sc = float(18 + 55 * s)
        ss = float(18 + 45 * s)
        den = cv2.bilateralFilter(bgr, d=d, sigmaColor=sc, sigmaSpace=ss)

        # Very gentle edge-preserving smooth on high-frequency noise (no large-kernel blur)
        if s > 0.2:
            mix = float(0.15 + 0.2 * s)
            den = cv2.addWeighted(den.astype(np.float32), 1.0 - mix, bgr.astype(np.float32), mix, 0.0)
            den = np.clip(den, 0, 255).astype(np.uint8)

        rgb2 = cv2.cvtColor(den, cv2.COLOR_BGR2RGB)

        # --- LAB: mild contrast on luminance (local, subtle)
        if s > 0.15:
            lab = cv2.cvtColor(rgb2, cv2.COLOR_RGB2Lab)
            l_ch, a_ch, bb_ch = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=float(1.2 + 0.8 * s), tileGridSize=(8, 8))
            l2 = clahe.apply(l_ch)
            mix_l = float(0.25 + 0.35 * s)
            l_ch = cv2.addWeighted(l_ch.astype(np.float32), 1.0 - mix_l, l2.astype(np.float32), mix_l, 0.0)
            l_ch = np.clip(l_ch, 0, 255).astype(np.uint8)
            lab2 = cv2.merge((l_ch, a_ch, bb_ch))
            rgb2 = cv2.cvtColor(lab2, cv2.COLOR_Lab2RGB)

        # --- Palette nudge: quantize RGB slightly (alpha kept separate)
        if s > 0.18:
            n_colors = max(42, int(220 - 120 * s))
            qim = Image.fromarray(rgb2, mode="RGB")
            qim = qim.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
            rgb2 = np.array(qim.convert("RGB"), dtype=np.uint8)

        pil_rgb = Image.fromarray(rgb2, mode="RGB")

        # --- Saturation / contrast (sticker-like, still conservative)
        sat_f = float(1.0 - (0.08 + 0.14 * s))
        con_f = float(1.0 + (0.04 + 0.08 * s))
        pil_rgb = ImageEnhance.Color(pil_rgb).enhance(sat_f)
        pil_rgb = ImageEnhance.Contrast(pil_rgb).enhance(con_f)

        # --- Mild unsharp (no large-radius blur)
        radius = max(0.6, 0.9 + 0.4 * s)
        percent = int(18 + 45 * s)
        pil_rgb = pil_rgb.filter(
            ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=2)
        )

        # --- Outline emphasis on alpha silhouette (darken 1px band outside fill)
        rgba = Image.merge("RGBA", (*pil_rgb.split(), Image.fromarray(alpha_u8, mode="L")))
        rgba = self._alpha_outline_darken(rgba, strength=s)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pil_save_image(
            rgba, output_path, format="PNG", optimize=True, compress_level=9
        )
        return output_path

    def _alpha_outline_darken(self, im: Image.Image, *, strength: float) -> Image.Image:
        """Slight outer-edge darkening for readable sticker outline."""
        if strength < 0.12:
            return im
        r, g, b, a = im.split()
        alpha = np.array(a, dtype=np.uint8)
        fg = (alpha > 8).astype(np.uint8) * 255
        er = cv2.erode(fg, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
        ring = cv2.subtract(fg, er)
        amount = float(0.08 + 0.12 * strength)
        rgb = np.array(im.convert("RGB"), dtype=np.float32)
        ring3 = (ring.astype(np.float32) / 255.0)[..., None]
        dark = rgb * (1.0 - amount * ring3)
        dark = np.clip(dark, 0, 255).astype(np.uint8)
        out = Image.fromarray(dark, mode="RGB")
        return Image.merge("RGBA", (*out.split(), a))

    def process_batch(
        self,
        input_paths: list[Path],
        output_dir: Path,
        strength: float | None = None,
    ) -> list[Path]:
        """Process many files; skips missing inputs. Returns written paths in stable order."""
        output_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for p in sorted(input_paths, key=lambda x: x.stem):
            if not p.is_file():
                continue
            out = output_dir / p.name
            written.append(self.process_image(p, out, strength))
        return written
