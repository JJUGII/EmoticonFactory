"""v0.3 heuristic character consistency checks (replaceable with Vision API later)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from services.character_profile import CharacterProfile
from services.image_io import ImageReadError, cv_imread


def _load_bgra(path: Path) -> tuple[np.ndarray | None, str | None]:
    try:
        arr = cv_imread(path, cv2.IMREAD_UNCHANGED)
    except ImageReadError as exc:
        return None, str(exc)
    if arr.ndim != 3:
        return None, f"지원하지 않는 이미지 배열 차원(ndim={arr.ndim}) — {path.resolve()}"
    if arr.shape[2] == 3:
        alpha = np.full((arr.shape[0], arr.shape[1], 1), 255, dtype=arr.dtype)
        arr = np.concatenate([arr, alpha], axis=2)
    elif arr.shape[2] == 4:
        pass
    else:
        return None, f"지원하지 않는 채널 수({arr.shape[2]}) — {path.resolve()}"
    return arr, None


def _foreground_mask_alpha(bgra: np.ndarray, alpha_thresh: int = 28) -> np.ndarray:
    return bgra[:, :, 3] > alpha_thresh


def _bbox_xywh(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask)
    if ys.size == 0:
        return None
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    return x0, y0, x1 - x0 + 1, y1 - y0 + 1


def _hue_hist_normalized(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if not np.any(mask):
        return np.ones(8, dtype=np.float64) / 8.0
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hh = hsv[:, :, 0][mask]
    if hh.size < 24:
        return np.ones(8, dtype=np.float64) / 8.0
    hist, _ = np.histogram(hh, bins=8, range=(0, 180))
    hist = hist.astype(np.float64)
    s = float(hist.sum())
    if s < 1e-6:
        return np.ones(8, dtype=np.float64) / 8.0
    return hist / s


def _eye_span_fraction(eye_fg: np.ndarray) -> float:
    if eye_fg.size == 0 or not np.any(eye_fg):
        return 0.38
    col = eye_fg.sum(axis=0).astype(np.float64)
    if float(col.max()) <= 0.0:
        return 0.38
    k = np.ones(3, dtype=np.float64) / 3.0
    col = np.convolve(col, k, mode="same")
    w = int(col.shape[0])
    mid = max(1, w // 2)
    li = int(np.argmax(col[:mid]))
    r0 = mid + max(1, int(0.12 * w))
    if r0 >= w:
        r0 = mid + 1
    ri = r0 + int(np.argmax(col[r0:]))
    span = (ri - li) / float(max(w, 1))
    return float(max(0.12, min(0.72, span)))


def _ear_asymmetry_ratio(fg: np.ndarray, x0: int, y0: int, bw: int, bh: int) -> float:
    yt = y0 + int(0.05 * bh)
    yb = y0 + int(0.30 * bh)
    region = fg[yt:yb, x0 : x0 + bw]
    if region.size == 0 or not np.any(region):
        return 0.0
    hm = max(1, bw // 2)
    L = float(region[:, :hm].sum())
    R = float(region[:, hm:].sum())
    return float(abs(L - R) / (L + R + 1e-6))


@dataclass
class _ImageMetrics:
    mean_bgr_core: np.ndarray
    transparency_ratio: float
    bbox_cx_norm: float
    bbox_cy_norm: float
    bbox_area_ratio: float
    dark_mask_ratio: float
    blue_eye_ratio: float
    edge_density: float
    laplacian_var: float
    bbox_aspect_ratio: float = 1.0
    eye_span_norm: float = 0.38
    ear_asymmetry: float = 0.0
    hue_hist: tuple[float, ...] = field(default_factory=lambda: (0.125,) * 8)
    local_contrast_std: float = 0.0
    sat_variance: float = 0.0
    brush_noise_level: float = 0.0
    edge_smoothness: float = 0.0

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "mean_bgr_core": [float(x) for x in self.mean_bgr_core],
            "transparency_ratio": round(self.transparency_ratio, 5),
            "bbox_cx_norm": round(self.bbox_cx_norm, 5),
            "bbox_cy_norm": round(self.bbox_cy_norm, 5),
            "bbox_area_ratio": round(self.bbox_area_ratio, 5),
            "bbox_aspect_ratio": round(self.bbox_aspect_ratio, 4),
            "eye_span_norm": round(self.eye_span_norm, 4),
            "ear_asymmetry": round(self.ear_asymmetry, 4),
            "hue_hist": [round(float(x), 5) for x in self.hue_hist],
            "dark_mask_ratio": round(self.dark_mask_ratio, 5),
            "blue_eye_ratio": round(self.blue_eye_ratio, 5),
            "edge_density": round(self.edge_density, 5),
            "laplacian_var": round(self.laplacian_var, 3),
            "local_contrast_std": round(self.local_contrast_std, 5),
            "sat_variance": round(self.sat_variance, 5),
            "brush_noise_level": round(self.brush_noise_level, 5),
            "edge_smoothness": round(self.edge_smoothness, 5),
        }


def _hsv_from_bgr(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)


def analyze_image(path: Path) -> tuple[_ImageMetrics | None, str | None]:
    """Compute heuristic metrics for one RGBA PNG. Returns (metrics, error_message)."""
    bgra, load_err = _load_bgra(path)
    if bgra is None:
        return None, load_err or "이미지를 열 수 없거나 지원하지 않는 형식입니다."

    h, w = bgra.shape[:2]
    fg = _foreground_mask_alpha(bgra)
    if not np.any(fg):
        return None, "전경(알파) 마스크가 비었습니다."

    bbox = _bbox_xywh(fg)
    assert bbox is not None
    x0, y0, bw, bh = bbox
    bbox_aspect_ratio = float(bw) / float(max(bh, 1))

    # Character core ( 텍스트·가장자리 완화): bbox 내부 세로 중·상단 쪽 위주
    core_y0 = y0 + int(0.10 * bh)
    core_y1 = y0 + int(0.82 * bh)
    core_x0 = x0 + int(0.06 * bw)
    core_x1 = x0 + int(0.94 * bw)
    core_mask = np.zeros_like(fg, dtype=bool)
    core_mask[core_y0:core_y1, core_x0:core_x1] = fg[core_y0:core_y1, core_x0:core_x1]

    bgr = bgra[:, :, :3]
    if np.any(core_mask):
        cores = bgr[core_mask]
        mean_bgr_core = np.mean(cores, axis=0)
    else:
        mean_bgr_core = np.mean(bgr[fg], axis=0)

    transp = float(np.mean(bgra[:, :, 3] < 25))
    area_ratio = float(bw * bh) / float(h * w)
    bbox_cx = (x0 + bw / 2) / w
    bbox_cy = (y0 + bh / 2) / h

    # Upper face ROI (dark Siamese mask heuristic)
    face_y1 = y0 + int(0.55 * bh)
    face_roi = fg[y0:face_y1, x0 : x0 + bw]
    face_bgr = bgr[y0:face_y1, x0 : x0 + bw]
    if face_roi.size > 0 and np.any(face_roi):
        hsv_face = _hsv_from_bgr(face_bgr)
        v = hsv_face[:, :, 2][face_roi]
        dark_mask_ratio = float(np.mean((v < 95) & (v > 8)))
    else:
        dark_mask_ratio = 0.0

    # Eye-ish band (blue channels / HSV hue)
    eye_y0 = y0 + max(1, int(0.06 * bh))
    eye_y1 = y0 + int(0.48 * bh)
    eye_slice = fg[eye_y0:eye_y1, x0 : x0 + bw]
    eye_bgr = bgr[eye_y0:eye_y1, x0 : x0 + bw]
    eye_span_norm = 0.38
    if eye_slice.size > 0 and np.any(eye_slice):
        ehsv = _hsv_from_bgr(eye_bgr)
        hh, ss, vv = cv2.split(ehsv)
        ee = eye_slice
        blue_hsv = (
            ((hh.astype(int) >= 95) & (hh.astype(int) <= 138))
            & (ss > 38)
            & (vv > 42)
        )
        bb, gg, rr = cv2.split(eye_bgr)
        blue_rgb = (bb.astype(int) > rr + 22) & (bb.astype(int) > gg + 12) & (bb > 90)
        blue_eye_ratio = float(np.mean((blue_hsv | blue_rgb) & ee))
        eye_span_norm = _eye_span_fraction(eye_slice)
    else:
        blue_eye_ratio = 0.0

    ear_asymmetry = _ear_asymmetry_ratio(fg, x0, y0, bw, bh)

    hue_hist_arr = _hue_hist_normalized(bgr, core_mask)
    hue_hist_t = tuple(float(x) for x in hue_hist_arr.tolist())

    gray = cv2.cvtColor(bgra[:, :, :3], cv2.COLOR_BGR2GRAY)
    gray = np.where(fg, gray, 0)
    edges = cv2.Canny(gray, 45, 120)
    edge_density = float(np.mean(edges[fg] > 0)) if np.any(fg) else 0.0
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    laplacian_var = float(np.var(lap[fg])) if np.any(fg) else 0.0

    if np.any(core_mask):
        gcore = gray[core_mask].astype(np.float64)
        local_contrast_std = float(np.std(gcore)) / 128.0
    else:
        local_contrast_std = 0.0

    hsv_fg = _hsv_from_bgr(bgr)
    sat_ch = hsv_fg[:, :, 1][fg]
    sat_variance = float(np.var(sat_ch)) / 6500.0 if sat_ch.size > 8 else 0.0

    brush_noise_level = float(np.log1p(max(laplacian_var, 0.0))) / 12.0
    edge_smoothness = _clamp01(1.0 - min(edge_density / 0.14, 1.0))

    metrics = _ImageMetrics(
        mean_bgr_core=mean_bgr_core,
        transparency_ratio=transp,
        bbox_cx_norm=bbox_cx,
        bbox_cy_norm=bbox_cy,
        bbox_area_ratio=area_ratio,
        dark_mask_ratio=dark_mask_ratio,
        blue_eye_ratio=blue_eye_ratio,
        edge_density=edge_density,
        laplacian_var=laplacian_var,
        bbox_aspect_ratio=bbox_aspect_ratio,
        eye_span_norm=eye_span_norm,
        ear_asymmetry=ear_asymmetry,
        hue_hist=hue_hist_t,
        local_contrast_std=local_contrast_std,
        sat_variance=sat_variance,
        brush_noise_level=brush_noise_level,
        edge_smoothness=edge_smoothness,
    )
    return metrics, None


def _texture_similarity(ref: _ImageMetrics, cut: _ImageMetrics) -> tuple[float, list[str]]:
    """0–1 texture match vs reference (higher = more painterly detail preserved)."""
    issues: list[str] = []
    rl = max(ref.laplacian_var, 25.0)
    lap_r = cut.laplacian_var / rl
    brush_sim = _clamp01(min(lap_r, 2.2) / 2.2)

    rsat = max(ref.sat_variance, 0.008)
    sat_r = cut.sat_variance / rsat
    sat_sim = _clamp01(1.0 - abs(np.log(max(sat_r, 0.12))) / 1.35)

    rlc = max(ref.local_contrast_std, 0.02)
    lc_r = cut.local_contrast_std / rlc
    contrast_sim = _clamp01(1.0 - abs(np.log(max(lc_r, 0.15))) / 1.25)

    re = max(ref.edge_density, 0.015)
    ed_r = cut.edge_density / re
    edge_sim = _clamp01(1.0 - abs(np.log(max(ed_r, 0.15))) / 1.5)

    rb = max(ref.brush_noise_level, 0.05)
    brush_lvl_r = cut.brush_noise_level / rb
    brush_lvl_sim = _clamp01(1.0 - abs(np.log(max(brush_lvl_r, 0.12))) / 1.4)

    flat_vector = (
        lap_r < 0.40
        and brush_lvl_r < 0.48
        and sat_r < 0.55
        and lc_r < 0.55
        and cut.edge_smoothness > ref.edge_smoothness + 0.12
    )
    if flat_vector:
        issues.append(
            "texture_flattening_detected: 컷이 참조 대비 과도하게 평탄한 벡터/이모지 느낌 "
            f"(lap×{lap_r:.2f}, sat×{sat_r:.2f}, contrast×{lc_r:.2f})"
        )
        brush_sim *= 0.55
        sat_sim *= 0.75

    sim = (
        0.30 * brush_sim
        + 0.22 * brush_lvl_sim
        + 0.20 * sat_sim
        + 0.16 * contrast_sim
        + 0.12 * edge_sim
    )
    return _clamp01(sim), issues


def _style_similarity(ref: _ImageMetrics, cut: _ImageMetrics) -> float:
    rh = np.array(ref.hue_hist, dtype=np.float64)
    ch = np.array(cut.hue_hist, dtype=np.float64)
    hue_sim = _clamp01(1.0 - 0.5 * float(np.sum(np.abs(rh - ch))))
    rsat = max(ref.sat_variance, 0.008)
    sat_r = cut.sat_variance / rsat
    sat_sim = _clamp01(1.0 - abs(np.log(max(sat_r, 0.12))) / 1.35)
    return _clamp01(0.62 * hue_sim + 0.38 * sat_sim)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _score_vs_reference(
    ref: _ImageMetrics,
    cut: _ImageMetrics,
    profile: CharacterProfile,
) -> tuple[float, list[str]]:
    issues: list[str] = []

    diff = np.linalg.norm(ref.mean_bgr_core - cut.mean_bgr_core)
    color_sim = _clamp01(1.0 - diff / 120.0)
    if color_sim < 0.55:
        issues.append(f"주요 영역 평균 색상이 참조와 다름 (BGR L2≈{diff:.1f})")

    ref_dm = max(ref.dark_mask_ratio, 0.02)
    ratio_dm = cut.dark_mask_ratio / ref_dm
    if ratio_dm < 0.45:
        issues.append(
            "얼굴 상부 어두운(마스크) 픽셀 비율이 참조 대비 너무 낮음 "
            f"(컷={cut.dark_mask_ratio:.3f}, 참조≈{ref.dark_mask_ratio:.3f})"
        )
        dark_score = ratio_dm / 0.45
    else:
        dark_score = _clamp01(min(ratio_dm, 1.8) / 1.8)

    ref_blue = max(ref.blue_eye_ratio, 0.008)
    ratio_blue = cut.blue_eye_ratio / ref_blue if ref_blue > 1e-6 else 1.0
    if ratio_blue < 0.35 and profile.eye_color.lower().find("blue") >= 0:
        issues.append(
            "파란 눈 후보 픽셀이 참조 대비 부족 "
            f"(컷={cut.blue_eye_ratio:.4f}, 참조≈{ref.blue_eye_ratio:.4f})"
        )
        blue_score = ratio_blue / 0.35
    else:
        blue_score = _clamp01(min(ratio_blue, 2.0) / 2.0)

    dt = abs(cut.transparency_ratio - ref.transparency_ratio)
    trans_score = _clamp01(1.0 - dt / max(ref.transparency_ratio, 0.12, dt + 1e-6))
    if cut.transparency_ratio < ref.transparency_ratio - 0.18:
        issues.append(
            "투명 배경 비율이 참조보다 낮음 (불필요한 배경 채움 가능) "
            f"(컷={cut.transparency_ratio:.2f}, 참조≈{ref.transparency_ratio:.2f})"
        )
        trans_score *= 0.7

    dcx = abs(cut.bbox_cx_norm - ref.bbox_cx_norm)
    dcy = abs(cut.bbox_cy_norm - ref.bbox_cy_norm)
    pos_score = _clamp01(1.0 - 4.0 * (dcx + dcy))
    if pos_score < 0.55:
        issues.append(
            "캐릭터 바운딩 박스 위치가 참조와 어긋남 "
            f"(Δcx={dcx:.2f}, Δcy={dcy:.2f})"
        )

    ra = max(ref.bbox_area_ratio, 0.05)
    ar_ratio = cut.bbox_area_ratio / ra
    if ar_ratio < 0.55 or ar_ratio > 1.55:
        issues.append(
            "캐릭터 상대 크기가 참조와 많이 다름 "
            f"(컷 area_ratio={cut.bbox_area_ratio:.2f}, 참조≈{ref.bbox_area_ratio:.2f})"
        )
    size_score = _clamp01(1.0 - abs(np.log(max(ar_ratio, 0.2))) / 1.2)

    ref_asp = max(ref.bbox_aspect_ratio, 0.35)
    asp_r = cut.bbox_aspect_ratio / ref_asp if ref_asp > 1e-6 else 1.0
    aspect_score = _clamp01(1.0 - abs(np.log(max(asp_r, 0.2))) / 0.65)
    if asp_r < 0.72 or asp_r > 1.42:
        issues.append(
            "실루엣 가로세로 비율이 참조와 달라 보임 (머리·몸 비중) "
            f"(컷 aspect={cut.bbox_aspect_ratio:.3f}, 참조≈{ref.bbox_aspect_ratio:.3f})"
        )

    ref_es = max(ref.eye_span_norm, 0.14)
    es_ratio = cut.eye_span_norm / ref_es if ref_es > 1e-6 else 1.0
    eye_span_score = _clamp01(1.0 - abs(np.log(max(es_ratio, 0.2))) / 0.85)
    if es_ratio < 0.62 or es_ratio > 1.55:
        issues.append(
            "눈 주변 가로 분포(눈 간격 추정)가 참조와 많이 다름 "
            f"(컷={cut.eye_span_norm:.3f}, 참조≈{ref.eye_span_norm:.3f})"
        )

    d_ear = abs(cut.ear_asymmetry - ref.ear_asymmetry)
    ear_score = _clamp01(1.0 - d_ear / 0.55)
    if d_ear > 0.32:
        issues.append(
            "귀·상부 좌우 실루엣 비대칭이 참조 대비 크게 변함 "
            f"(컷={cut.ear_asymmetry:.3f}, 참조≈{ref.ear_asymmetry:.3f})"
        )

    rh = np.array(ref.hue_hist, dtype=np.float64)
    ch = np.array(cut.hue_hist, dtype=np.float64)
    pal_hist_score = _clamp01(1.0 - 0.5 * float(np.sum(np.abs(rh - ch))))
    if pal_hist_score < 0.62:
        issues.append("털·바디 팔레트(색상 분포)가 참조와 다름 (hue histogram 유사도 낮음)")

    tex_sim, tex_issues = _texture_similarity(ref, cut)
    if tex_issues:
        issues.extend(tex_issues)
    painterly_tex_score = tex_sim / 0.48 if tex_sim < 0.48 else 1.0

    ref_lap = max(ref.laplacian_var, 80.0)
    ref_ed = max(ref.edge_density, 0.03)
    lap_rel = cut.laplacian_var / ref_lap
    ed_rel = cut.edge_density / ref_ed
    photo_detail_score = 1.0
    if lap_rel > 2.3 and ed_rel > 1.75:
        issues.append(
            "에지/라플라시안 복잡도가 높음 — 실사·고주파 텍스처 의심 "
            f"(lap×{lap_rel:.2f}, edge×{ed_rel:.2f})"
        )
        photo_detail_score = 0.35
    elif lap_rel > 1.75 or ed_rel > 1.45:
        issues.append(
            "에지 밀도가 참조보다 다소 높음 (스타일 편차 가능)"
        )
        photo_detail_score = 0.72

    # Weights sum to 1.0 — tuned for cartoon sticker vs reference + silhouette/palette heuristics
    w = {
        "color": 0.16,
        "dark": 0.14,
        "blue": 0.08,
        "trans": 0.10,
        "pos": 0.10,
        "size": 0.08,
        "texture": 0.12,
        "aspect": 0.08,
        "eye_span": 0.06,
        "ear": 0.04,
        "palhist": 0.03,
        "tex": 0.05,
    }
    total = (
        w["color"] * color_sim
        + w["dark"] * _clamp01(dark_score)
        + w["blue"] * _clamp01(blue_score)
        + w["trans"] * trans_score
        + w["pos"] * pos_score
        + w["size"] * size_score
        + w["texture"] * photo_detail_score
        + w["aspect"] * aspect_score
        + w["eye_span"] * eye_span_score
        + w["ear"] * ear_score
        + w["palhist"] * pal_hist_score
        + w["tex"] * painterly_tex_score
    )
    return _clamp01(total), issues


def _drift_similarity(ref: _ImageMetrics, cut: _ImageMetrics) -> tuple[float, list[str]]:
    """Lightweight 0–1 similarity vs reference (higher = less drift). v0.5 heuristic."""
    issues: list[str] = []

    diff = float(np.linalg.norm(ref.mean_bgr_core - cut.mean_bgr_core))
    pal_sim = _clamp01(1.0 - diff / 130.0)
    if pal_sim < 0.5:
        issues.append(f"dominant palette distance high (BGR L2≈{diff:.1f})")

    ra = max(ref.bbox_area_ratio, 0.05)
    ar_ratio = cut.bbox_area_ratio / ra
    bbox_sim = _clamp01(1.0 - abs(np.log(max(ar_ratio, 0.15))) / 1.35)
    if ar_ratio < 0.5 or ar_ratio > 1.65:
        issues.append(
            f"foreground bbox area ratio differs (cut={cut.bbox_area_ratio:.3f} vs ref={ref.bbox_area_ratio:.3f})"
        )

    rd = max(ref.dark_mask_ratio, 0.02)
    ld_ratio = cut.dark_mask_ratio / rd if rd > 1e-6 else 1.0
    lum_sim = _clamp01(1.0 - abs(np.log(max(ld_ratio, 0.2))) / 1.5)

    re = max(ref.edge_density, 0.02)
    ed_ratio = cut.edge_density / re if re > 1e-6 else 1.0
    edge_sim = _clamp01(1.0 - abs(np.log(max(ed_ratio, 0.2))) / 1.6)
    if ed_ratio > 1.85 or ed_ratio < 0.45:
        issues.append(
            f"edge density shift (cut={cut.edge_density:.4f} vs ref={ref.edge_density:.4f})"
        )

    rl = max(ref.laplacian_var, 50.0)
    lap_ratio = cut.laplacian_var / rl if rl > 1e-6 else 1.0
    shape_sim = _clamp01(1.0 - abs(np.log(max(lap_ratio, 0.15))) / 1.7)

    rh = np.array(ref.hue_hist, dtype=np.float64)
    ch = np.array(cut.hue_hist, dtype=np.float64)
    hue_drift = _clamp01(1.0 - 0.5 * float(np.sum(np.abs(rh - ch))))
    if hue_drift < 0.55:
        issues.append("hue histogram drift (fur palette families)")

    eye_d = abs(ref.eye_span_norm - cut.eye_span_norm)
    eye_sim = _clamp01(1.0 - eye_d / 0.22)
    if eye_sim < 0.55:
        issues.append("estimated eye-span layout drift vs reference")

    refa = max(ref.bbox_aspect_ratio, 0.3)
    ar_rel = cut.bbox_aspect_ratio / refa if refa > 1e-6 else 1.0
    asp_sim = _clamp01(1.0 - abs(np.log(max(ar_rel, 0.18))) / 0.9)

    w = (0.20, 0.16, 0.14, 0.12, 0.12, 0.12, 0.07, 0.07)
    sim = (
        w[0] * pal_sim
        + w[1] * bbox_sim
        + w[2] * lum_sim
        + w[3] * edge_sim
        + w[4] * shape_sim
        + w[5] * hue_drift
        + w[6] * eye_sim
        + w[7] * asp_sim
    )
    return _clamp01(sim), issues


def _canonical_identity_score(identity_sim: float, drift_sim: float) -> float:
    """Combined 0–1 score: silhouette/palette identity + drift resistance."""
    return _clamp01(0.58 * identity_sim + 0.42 * drift_sim)


def _identity_drift_heatmap_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in items:
        cid = str(row.get("id", ""))
        if not cid or cid == "_reference":
            continue
        rows.append(
            {
                "id": cid,
                "canonical_identity_score": row.get("canonical_identity_score"),
                "identity_similarity": row.get("identity_similarity"),
                "drift_similarity": row.get("drift_similarity"),
                "drift_score": row.get("drift_score"),
                "status": row.get("status"),
                "drift_status": row.get("drift_status"),
            }
        )
    return rows


def _perceptual_hash_similarity(path_a: Path, path_b: Path) -> float | None:
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return None
    try:
        a = Image.open(path_a).convert("RGB")
        b = Image.open(path_b).convert("RGB")
        ha = imagehash.phash(a, hash_size=12)
        hb = imagehash.phash(b, hash_size=12)
        dist = float(ha - hb)
        return _clamp01(1.0 - dist / 64.0)
    except (OSError, ValueError, TypeError):
        return None


class CharacterConsistencyChecker:
    """Heuristic sticker consistency vs a reference PNG; swap for Vision/CLIP later."""

    def __init__(
        self,
        threshold: float = 0.72,
        *,
        drift_threshold: float = 0.68,
        strict_drift: bool = False,
    ) -> None:
        self.threshold = float(threshold)
        self.drift_threshold = float(drift_threshold)
        self.strict_drift = bool(strict_drift)

    def check(
        self,
        reference_path: Path,
        image_paths: list[Path],
        profile: CharacterProfile,
    ) -> dict[str, Any]:
        ref_m, ref_err = analyze_image(reference_path)
        meta_ref: dict[str, Any]
        if ref_m is None:
            meta_ref = {"error": ref_err or "unknown"}
            return {
                "ok": False,
                "threshold": self.threshold,
                "reference_path": str(reference_path.resolve()),
                "reference_metrics": meta_ref,
                "checker_version": "0.6-heuristic-texture",
                "items": [],
                "failed": [
                    {
                        "id": "_reference",
                        "score": 0.0,
                        "path": str(reference_path),
                        "issues": [ref_err or "reference analyze failed"],
                    }
                ],
            }

        items: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for pth in sorted(image_paths, key=lambda p: p.stem):
            cut_id = pth.stem
            if not pth.is_file():
                row = {
                    "id": cut_id,
                    "path": str(pth),
                    "score": 0.0,
                    "status": "fail",
                    "issues": ["파일 없음"],
                }
                items.append(row)
                failed.append(
                    {"id": cut_id, "score": 0.0, "path": str(pth), "issues": row["issues"]}
                )
                continue

            cut_m, err = analyze_image(pth)
            if cut_m is None:
                msg = err or "분석 실패"
                row = {
                    "id": cut_id,
                    "path": str(pth.resolve()),
                    "score": 0.0,
                    "status": "fail",
                    "issues": [msg],
                    "metrics": None,
                }
                items.append(row)
                failed.append(
                    {"id": cut_id, "score": 0.0, "path": str(pth), "issues": [msg]}
                )
                continue

            score, issues = _score_vs_reference(ref_m, cut_m, profile)
            status = "pass" if score >= self.threshold else "fail"

            identity_similarity = round(score, 4)
            tex_sim_row, _ = _texture_similarity(ref_m, cut_m)
            texture_similarity = round(tex_sim_row, 4)
            style_similarity = round(_style_similarity(ref_m, cut_m), 4)

            drift_sim, drift_issues = _drift_similarity(ref_m, cut_m)
            ph = _perceptual_hash_similarity(reference_path, pth)
            if ph is not None:
                drift_sim = _clamp01(0.55 * drift_sim + 0.45 * ph)
            drift_score = round(1.0 - drift_sim, 4)
            if drift_sim >= self.drift_threshold:
                drift_status = "pass"
            elif drift_sim >= max(0.0, self.drift_threshold - 0.12):
                drift_status = "warn"
            else:
                drift_status = "fail"
            if self.strict_drift and drift_status == "warn":
                drift_status = "fail"

            canon_id_score = round(
                _canonical_identity_score(identity_similarity, drift_sim), 4
            )
            drift_reason = "; ".join(drift_issues[:4]) if drift_issues else ""
            if canon_id_score < 0.62 and "identity_drift_detected" not in " ".join(issues):
                issues = list(issues) + [
                    f"identity_drift_detected: canonical_identity_score={canon_id_score:.3f}"
                ]

            row = {
                "id": cut_id,
                "path": str(pth.resolve()),
                "score": round(score, 4),
                "identity_similarity": identity_similarity,
                "texture_similarity": texture_similarity,
                "style_similarity": style_similarity,
                "canonical_identity_score": canon_id_score,
                "status": status,
                "issues": issues,
                "metrics": cut_m.to_json_dict(),
                "drift_similarity": round(drift_sim, 4),
                "drift_score": drift_score,
                "drift_status": drift_status,
                "drift_issues": drift_issues,
                "drift_reason": drift_reason,
            }
            items.append(row)

            cons_fail = status == "fail"
            drift_fail = drift_status == "fail"
            if cons_fail or drift_fail:
                merged: list[str] = []
                if cons_fail:
                    merged.extend(issues)
                    merged.append(f"임계값 {self.threshold} 미만")
                if drift_fail:
                    merged.extend(drift_issues)
                    merged.append(
                        f"드리프트 판정 실패 (drift_similarity={drift_sim:.3f} < {self.drift_threshold})"
                    )
                failed.append(
                    {
                        "id": cut_id,
                        "score": round(score, 4),
                        "path": str(pth.resolve()),
                        "issues": merged,
                    }
                )

        ok = len(failed) == 0
        return {
            "ok": ok,
            "threshold": self.threshold,
            "drift_threshold": self.drift_threshold,
            "strict_drift": self.strict_drift,
            "reference_path": str(reference_path.resolve()),
            "reference_metrics": ref_m.to_json_dict(),
            "checker_version": "0.7-universal-identity",
            "notes": (
                "휴리스틱 v0.7: identity/texture/style + canonical_identity_score + drift. "
                "Face proportion, eye geometry, ear position, silhouette, palette, fur mask heuristics. "
                "texture_flattening_detected when overly flat vs reference. "
                "추후 Vision API 또는 CLIP 유사도로 교체 예정."
            ),
            "identity_drift_heatmap": _identity_drift_heatmap_rows(items),
            "items": items,
            "failed": failed,
        }


def copy_failed_consistency(
    package_dir: Path,
    report: dict[str, Any],
) -> list[Path]:
    """Copy PNGs scoring below threshold into ``failed_consistency/``."""
    dest = package_dir / "failed_consistency"
    dest.mkdir(parents=True, exist_ok=True)
    # Clear previous copies (same stem)
    for old in dest.glob("*.png"):
        if old.name.startswith("._"):
            continue
        try:
            old.unlink()
        except OSError:
            pass

    copied: list[Path] = []
    for row in report.get("failed", []):
        sid = row.get("id")
        src_s = row.get("path")
        if not sid or sid == "_reference" or not isinstance(src_s, str):
            continue
        src = Path(src_s)
        if src.is_file():
            out = dest / f"{sid}.png"
            shutil.copy2(src, out)
            copied.append(out)
    return copied
