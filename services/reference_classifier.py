"""Heuristic classifier: real pet photo vs existing character artwork (v1).

Replace ``ReferenceClassifier.analyze`` with a vision model later; keep
``ReferenceClassification`` field names stable for ``package_info`` / logs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from pydantic import BaseModel, Field

from services.image_io import ImageReadError, cv_imread

ReferenceType = Literal["photo", "character_art", "unknown"]


class ReferenceClassification(BaseModel):
    """Outcome of ``ReferenceClassifier.analyze``."""

    reference_type: ReferenceType
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ReferenceClassifier:
    """Light-weight RGBA / texture / edge heuristics (no ML)."""

    _MAX_SIDE = 512

    def analyze(self, path: Path) -> ReferenceClassification:
        p = Path(path)
        if not p.is_file():
            return ReferenceClassification(
                reference_type="unknown",
                confidence=0.0,
                reasons=["파일이 없어 분류할 수 없습니다."],
                metrics={"error": "missing_file"},
            )

        try:
            bgra = cv_imread(p, cv2.IMREAD_UNCHANGED)
        except ImageReadError as exc:
            return ReferenceClassification(
                reference_type="unknown",
                confidence=0.0,
                reasons=[f"이미지를 읽지 못했습니다: {exc.detail}"],
                metrics={"error": "read_failed"},
            )

        if bgra.ndim != 2 and bgra.ndim != 3:
            return ReferenceClassification(
                reference_type="unknown",
                confidence=0.0,
                reasons=["지원하지 않는 채널 구성입니다."],
                metrics={},
            )

        if bgra.ndim == 2:
            bgr = cv2.cvtColor(bgra, cv2.COLOR_GRAY2BGR)
            alpha = None
        elif bgra.shape[2] == 4:
            bgr = bgra[:, :, :3]
            alpha = bgra[:, :, 3].astype(np.float32)
        else:
            bgr = bgra[:, :, :3]
            alpha = None

        bgr, alpha = self._resize_max_side(bgr, alpha)
        comp = self._composite_on_white(bgr, alpha)

        metrics = self._all_metrics(comp, alpha)
        photo_s, char_s, reasons = self._score(metrics)

        diff = abs(photo_s - char_s)
        if max(photo_s, char_s) < 1.2 and diff < 0.9:
            ref_type: ReferenceType = "unknown"
            conf = float(min(0.55, 0.25 + diff * 0.15))
            reasons = (
                ["사진 vs 캐릭터 아트 신호가 엇갈려 unknown 으로 분류했습니다."]
                + reasons[:5]
            )
        elif photo_s > char_s + 0.35:
            ref_type = "photo"
            conf = float(min(1.0, 0.45 + min(photo_s - char_s, 4.0) * 0.18))
        elif char_s > photo_s + 0.35:
            ref_type = "character_art"
            conf = float(min(1.0, 0.45 + min(char_s - photo_s, 4.0) * 0.18))
        else:
            ref_type = "unknown"
            conf = float(min(0.6, 0.35 + diff * 0.12))
            reasons = ["신호 차이가 작아 unknown 으로 분류했습니다."] + reasons[:5]

        metrics_out: dict[str, Any] = {k: _json_safe(v) for k, v in metrics.items()}
        metrics_out["score_photo"] = round(photo_s, 3)
        metrics_out["score_character_art"] = round(char_s, 3)

        return ReferenceClassification(
            reference_type=ref_type,
            confidence=round(conf, 4),
            reasons=reasons[:10],
            metrics=metrics_out,
        )

    def _resize_max_side(
        self, bgr: np.ndarray, alpha: np.ndarray | None
    ) -> tuple[np.ndarray, np.ndarray | None]:
        h, w = bgr.shape[:2]
        m = max(h, w)
        if m <= self._MAX_SIDE:
            return bgr, alpha
        scale = self._MAX_SIDE / float(m)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        bgr_r = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)
        if alpha is None:
            return bgr_r, None
        alpha_r = cv2.resize(alpha, (nw, nh), interpolation=cv2.INTER_AREA)
        return bgr_r, alpha_r

    def _composite_on_white(self, bgr: np.ndarray, alpha: np.ndarray | None) -> np.ndarray:
        if alpha is None:
            return bgr
        a = np.clip(alpha / 255.0, 0.0, 1.0)[..., None]
        white = np.full_like(bgr, 255, dtype=np.uint8)
        out = (bgr.astype(np.float32) * a + white.astype(np.float32) * (1.0 - a)).astype(
            np.uint8
        )
        return out

    def _all_metrics(
        self, comp_bgr: np.ndarray, alpha: np.ndarray | None
    ) -> dict[str, Any]:
        gray = cv2.cvtColor(comp_bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        area = float(h * w)

        lap = cv2.Laplacian(gray, cv2.CV_64F)
        lap_var = float(lap.var())

        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 40, 120)
        edge_density = float(np.mean(edges > 0))

        small = cv2.resize(comp_bgr, (72, 72), interpolation=cv2.INTER_AREA)
        q = (small.reshape(-1, 3) // 28).astype(np.int32)
        uniq = int(np.unique(q @ np.array([1, 32, 1024], dtype=np.int32)).size)

        transparent_ratio = 0.0
        has_alpha = alpha is not None
        if alpha is not None:
            transparent_ratio = float(np.mean(alpha < 18))

        border_mask = np.zeros((h, w), dtype=np.uint8)
        t = max(2, min(h, w) // 32)
        border_mask[:t, :] = 1
        border_mask[-t:, :] = 1
        border_mask[:, :t] = 1
        border_mask[:, -t:] = 1
        bpx = comp_bgr[border_mask > 0]
        border_std = float(np.std(bpx)) if bpx.size > 40 else 0.0

        step = max(8, min(h, w) // 32)
        flat_blocks = 0
        total_blocks = 0
        for y in range(0, h - step, step):
            for x in range(0, w - step, step):
                patch = gray[y : y + step, x : x + step]
                if patch.size < 16:
                    continue
                total_blocks += 1
                if float(np.std(patch)) < 6.5:
                    flat_blocks += 1
        flat_ratio = float(flat_blocks / max(1, total_blocks))

        if alpha is not None:
            fg = alpha > 40
        else:
            _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            fg = blur < th if float(np.mean(gray)) > 127 else gray > th
        ys, xs = np.where(fg)
        if ys.size < 50:
            central_ratio = 0.35
        else:
            y0, y1 = int(ys.min()), int(ys.max())
            x0, x1 = int(xs.min()), int(xs.max())
            central_ratio = float((y1 - y0 + 1) * (x1 - x0 + 1) / area)

        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        grad = np.sqrt(gx * gx + gy * gy)
        strong_outline = float(np.mean((grad > 35) & (grad < 120)))

        # Local texture: std of 5x5 std map (coarse)
        k = np.ones((5, 5), np.float32) / 25.0
        local_mean = cv2.filter2D(gray.astype(np.float32), -1, k)
        local_sq = cv2.filter2D((gray.astype(np.float32)) ** 2, -1, k)
        local_var = np.clip(local_sq - local_mean**2, 0, None)
        texture_mean = float(np.sqrt(local_var).mean())

        return {
            "has_meaningful_alpha": bool(has_alpha and transparent_ratio > 0.02),
            "transparent_pixel_ratio": transparent_ratio,
            "quantized_unique_colors_72": uniq,
            "laplacian_variance": lap_var,
            "edge_density": edge_density,
            "border_rgb_std": border_std,
            "large_flat_region_ratio": flat_ratio,
            "foreground_bbox_area_ratio": central_ratio,
            "outline_band_ratio": strong_outline,
            "texture_mean_grad_mag": texture_mean,
        }

    def _score(self, m: dict[str, Any]) -> tuple[float, float, list[str]]:
        photo = 0.0
        char = 0.0
        reasons: list[str] = []

        tr = float(m["transparent_pixel_ratio"])
        lap = float(m["laplacian_variance"])
        colors = int(m["quantized_unique_colors_72"])
        edge = float(m["edge_density"])
        bstd = float(m["border_rgb_std"])
        flat = float(m["large_flat_region_ratio"])
        tex = float(m["texture_mean_grad_mag"])
        outline = float(m["outline_band_ratio"])
        fg = float(m["foreground_bbox_area_ratio"])

        if tr > 0.06:
            char += 2.1
            reasons.append(f"투명·컷아웃 비율이 높음({tr:.2f}) → 스티커/캐릭터 후보")
        elif tr < 0.01:
            photo += 1.1
            reasons.append("불투명 배경 위주 → 실사 사진 후보")

        if lap > 420:
            photo += 2.0
            reasons.append(f"라플라시안 분산이 큼({lap:.0f}) → 질감·실사 후보")
        elif lap < 180:
            char += 1.4
            reasons.append(f"라플라시안 분산이 낮음({lap:.0f}) → 단순화·일러스트 후보")
        if lap > 650:
            photo += 1.3
            reasons.append("고주파 질감이 매우 큼 → 실사 가중")

        if colors > 260:
            photo += 1.5
            reasons.append(f"색상 다양도 높음(≥{colors}) → 실사 후보")
        elif colors < 110:
            char += 1.6
            reasons.append(f"색상 다양도 낮음({colors}) → 평면 캐릭터 후보")

        if edge > 0.11 and lap < 260:
            char += 1.0
            reasons.append("외곽선 밀도가 높고 질감은 상대적으로 낮음 → 벡터형 후보")

        if bstd < 16:
            char += 1.2
            reasons.append(f"가장자리 배경 단순(std={bstd:.1f}) → 일러스트 배경 후보")
        elif bstd > 38:
            photo += 0.9
            reasons.append(f"가장자리 색 변화 큼(std={bstd:.1f}) → 실사 배경 후보")

        if flat > 0.38 and lap < 360:
            char += 0.9
            reasons.append(f"평탄 블록 비율 높음({flat:.2f}) → 단색 면 후보")

        if tex > 14:
            photo += 1.1
            reasons.append(f"국소 질감 강함({tex:.1f}) → 실사 후보")
        elif tex < 8:
            char += 0.7
            reasons.append("국소 질감이 낮음 → 단순 채색 후보")

        if outline > 0.045 and colors < 200 and lap < 380:
            char += 0.8
            reasons.append("중간 강도 외곽선 밴드가 두드러짐 → 라인아트 후보")

        if 0.22 < fg < 0.72 and lap < 420:
            char += 0.35
            reasons.append("전경 바운딩 비율이 스티커형에 가까움")

        return photo, char, reasons


def _json_safe(v: Any) -> Any:
    if isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        if np.isnan(v) or np.isinf(v):
            return None
        return round(v, 6)
    if isinstance(v, np.generic):
        return _json_safe(v.item())
    return v
