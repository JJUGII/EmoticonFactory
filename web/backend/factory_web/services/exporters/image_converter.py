"""플랫폼별 이미지 변환 유틸리티.

Kakao PNG (360×360, 투명배경) → 각 플랫폼 규격으로 변환.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image


# ── 플랫폼 규격 ──────────────────────────────────────────────────────────────
PLATFORM_SPECS: dict[str, dict] = {
    "telegram": {"size": 512, "format": "WEBP", "max_bytes": 512 * 1024,  "quality": 90},
    "signal":   {"size": 512, "format": "WEBP", "max_bytes": 300 * 1024,  "quality": 85},
    "discord":  {"size": 320, "format": "PNG",  "max_bytes": 500 * 1024,  "quality": None},
    "line":     {"size": 370, "format": "PNG",  "max_bytes": 1024 * 1024, "quality": None},
    "kakao":    {"size": 360, "format": "PNG",  "max_bytes": 1024 * 1024, "quality": None},
}


def convert_png_for_platform(
    png_path: Path,
    platform: str,
) -> bytes:
    """PNG 파일 → 플랫폼 규격 이미지 bytes 반환.

    Args:
        png_path: Kakao 생성 PNG 경로 (360×360, RGBA)
        platform: "telegram" | "signal" | "discord" | "line" | "kakao"

    Returns:
        변환된 이미지 bytes (WebP or PNG)
    """
    spec = PLATFORM_SPECS.get(platform)
    if not spec:
        raise ValueError(f"지원하지 않는 플랫폼: {platform}")

    img = Image.open(png_path).convert("RGBA")

    # 정사각형 리사이즈 (투명도 유지)
    target = spec["size"]
    if img.size != (target, target):
        img = img.resize((target, target), Image.Resampling.LANCZOS)

    fmt = spec["format"]
    max_bytes = spec["max_bytes"]
    quality = spec.get("quality")

    # 1차 인코딩
    buf = io.BytesIO()
    if fmt == "WEBP":
        img.save(buf, "WEBP", quality=quality or 90, method=6)
    else:
        img.save(buf, "PNG", optimize=True)
    data = buf.getvalue()

    # 파일 크기 초과 시 품질 낮춰 재시도 (WebP만)
    if fmt == "WEBP" and len(data) > max_bytes:
        for q in (80, 70, 60, 50):
            buf = io.BytesIO()
            img.save(buf, "WEBP", quality=q, method=6)
            data = buf.getvalue()
            if len(data) <= max_bytes:
                break

    return data


def convert_all_pngs(
    png_dir: Path,
    platform: str,
    ids: list[str] | None = None,
) -> list[tuple[str, bytes]]:
    """PNG 디렉토리의 모든 스티커를 변환.

    Args:
        png_dir: Kakao PNG 폴더 (01.png ~ 16.png)
        platform: 변환 대상 플랫폼
        ids: 특정 ID만 변환 (None이면 전체)

    Returns:
        [(cut_id, image_bytes), ...] 정렬된 리스트
    """
    results: list[tuple[str, bytes]] = []
    pngs = sorted(p for p in png_dir.glob("*.png") if not p.name.startswith("."))

    for png in pngs:
        cut_id = png.stem  # "01", "02", ...
        if ids and cut_id not in ids:
            continue
        try:
            data = convert_png_for_platform(png, platform)
            results.append((cut_id, data))
        except Exception as e:
            print(f"[image_converter] {png.name} 변환 실패: {e}")

    return results
