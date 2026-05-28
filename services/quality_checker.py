"""Basic static checks for a generated big-emoticon folder layout."""

from __future__ import annotations

import json
from pathlib import Path

from config import (
    EMOTICON_SIZE,
    ICON_SIZE,
    MAX_EMOTICON_BYTES,
    MAX_ICON_BYTES,
    MAX_SHARE_BYTES,
    MAX_WEBP_ANIM_BYTES,
    MAX_WEBP_ANIM_FRAMES,
    SHARE_SIZE,
)
from services.image_io import ImageReadError, pil_open_buffer


class QualityChecker:
    """Validates file presence, dimensions, mode, and byte size budgets."""

    def check_big_emoticon_package(
        self,
        package_dir: Path,
        *,
        emoticon_subdir: str = "png",
        expected_cut_ids: list[str] | None = None,
    ) -> dict:
        """Run checks for big emoticons (default ``png/``), ``icon/``, ``share/``, ``package_info``.

        Args:
            package_dir: Series output root.
            emoticon_subdir: Subdirectory under ``package_dir`` holding 540×540 RGBA sticker PNGs.
                Typical values: ``png``, ``processed``, ``png_raw``.
            expected_cut_ids: ``None`` 이면 ``package_info.json`` 의 ``test_mode`` 가 참이면
                ``items`` 의 id만 검사(부분 패키지). 그 외에는 01–16 전체 기대.
                명시적으로 ``["01"]`` 등을 넘기면 해당 id만 검사합니다.

        Returns:
            Dict with keys ``ok``, ``errors``, ``warnings``, ``checks``.
        """
        errors: list[str] = []
        warnings: list[str] = []
        checks: dict[str, object] = {}

        png_dir = package_dir / emoticon_subdir
        icon_dir = package_dir / "icon"
        share_dir = package_dir / "share"
        meta_path = package_dir / "meta" / "package_info.json"

        data: dict | None = None
        if not meta_path.is_file():
            errors.append(f"메타 파일이 없습니다: {meta_path}")
        else:
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                checks["package_info_keys"] = sorted(list(data.keys()))
            except json.JSONDecodeError as exc:
                errors.append(f"package_info.json 파싱 실패: {exc}")

        expected_ids: list[str]
        partial_package = False

        if expected_cut_ids:
            expected_ids = []
            for raw in expected_cut_ids:
                s = str(raw).strip().zfill(2)
                if len(s) == 2 and s.isdigit():
                    expected_ids.append(s)
                else:
                    expected_ids.append(str(raw))
            expected_ids = sorted(set(expected_ids))
            partial_package = True
            checks["expected_cut_ids"] = expected_ids
        elif isinstance(data, dict) and bool(data.get("test_mode")):
            got: list[str] = []
            for it in data.get("items") or []:
                if not isinstance(it, dict) or it.get("id") is None:
                    continue
                s = str(it["id"]).strip().zfill(2)
                if len(s) == 2 and s.isdigit():
                    got.append(s)
            if got:
                expected_ids = sorted(set(got))
                partial_package = True
                checks["expected_cut_ids"] = expected_ids
            else:
                expected_ids = [f"{i:02d}" for i in range(1, 17)]
        else:
            expected_ids = [f"{i:02d}" for i in range(1, 17)]

        checks["partial_package"] = partial_package
        png_paths = [png_dir / f"{i}.png" for i in expected_ids]
        missing_png = [str(p) for p in png_paths if not p.is_file()]
        if missing_png:
            errors.append(f"PNG 누락({len(missing_png)}): 예) {missing_png[:3]}")

        icon_paths = [icon_dir / f"{i}.png" for i in expected_ids]
        missing_icon = [str(p) for p in icon_paths if not p.is_file()]
        if missing_icon:
            errors.append(f"아이콘 누락({len(missing_icon)}): 예) {missing_icon[:3]}")

        share_candidates = sorted(
            p for p in (share_dir.glob("*.png") if share_dir.is_dir() else [])
            if not p.name.startswith("._")
        )
        if not share_candidates:
            errors.append(f"공유 이미지가 없습니다: {share_dir}")
        elif len(share_candidates) > 1:
            warnings.append(
                f"공유 PNG가 여러 개입니다(첫 파일만 검사): {[p.name for p in share_candidates]}"
            )

        per_cut_png_errors: dict[str, list[str]] = {}
        per_cut_icon_errors: dict[str, list[str]] = {}

        ew, eh = EMOTICON_SIZE
        for p in png_paths:
            if not p.is_file():
                continue
            err = self._check_rgba_image(p, ew, eh, MAX_EMOTICON_BYTES, "big_emoticon")
            if err:
                errors.append(err)
                per_cut_png_errors.setdefault(p.stem, []).append(err)

        iw, ih = ICON_SIZE
        for p in icon_paths:
            if not p.is_file():
                continue
            err = self._check_rgba_image(p, iw, ih, MAX_ICON_BYTES, "icon")
            if err:
                errors.append(err)
                per_cut_icon_errors.setdefault(p.stem, []).append(err)

        if share_candidates:
            sw, sh = SHARE_SIZE
            err = self._check_rgba_image(
                share_candidates[0], sw, sh, MAX_SHARE_BYTES, "share"
            )
            if err:
                errors.append(err)

        expected_id_set = set(expected_ids)

        if isinstance(data, dict):
            animated = data.get("animated_items")
            if isinstance(animated, list) and animated:
                checks["animated_webp"] = []
                for entry in animated:
                    if not isinstance(entry, dict):
                        continue
                    eid = str(entry.get("id", "")).strip().zfill(2)
                    if partial_package and eid not in expected_id_set:
                        continue
                    rel = entry.get("webp")
                    if not isinstance(rel, str) or not rel.strip():
                        errors.append("animated_items 항목에 webp 경로가 없습니다.")
                        continue
                    p = package_dir / rel.replace("\\", "/")
                    if not p.is_file():
                        errors.append(f"WebP 파일 없음: {rel}")
                        continue
                    size_b = p.stat().st_size
                    if size_b > MAX_WEBP_ANIM_BYTES:
                        errors.append(
                            f"[webp] 용량 초과: {p.name} = {size_b} bytes "
                            f"(max {MAX_WEBP_ANIM_BYTES})"
                        )
                    try:
                        with pil_open_buffer(p) as wim:
                            if wim.format != "WEBP":
                                errors.append(f"[webp] WEBP가 아님: {p.name} format={wim.format}")
                            wim.seek(0)
                            if wim.size != EMOTICON_SIZE:
                                errors.append(
                                    f"[webp] 해상도 불일치: {p.name} {wim.size} "
                                    f"(expected {EMOTICON_SIZE})"
                                )
                            nfr = getattr(wim, "n_frames", 1)
                            if nfr > MAX_WEBP_ANIM_FRAMES:
                                errors.append(
                                    f"[webp] 프레임 수 초과: {p.name} n_frames={nfr} "
                                    f"(max {MAX_WEBP_ANIM_FRAMES})"
                                )
                            checks["animated_webp"].append(
                                {
                                    "path": rel,
                                    "bytes": size_b,
                                    "n_frames": nfr,
                                }
                            )
                    except (OSError, ImageReadError) as exc:
                        errors.append(f"[webp] 열기 실패: {p.resolve()} ({exc})")

        ok = len(errors) == 0
        checks["expected_ids"] = expected_ids
        checks["emoticon_subdir"] = emoticon_subdir
        checks["package_dir"] = str(package_dir.resolve())
        return {
            "ok": ok,
            "errors": errors,
            "warnings": warnings,
            "checks": checks,
            "per_cut_png_errors": per_cut_png_errors,
            "per_cut_icon_errors": per_cut_icon_errors,
        }

    def _check_rgba_image(
        self, path: Path, exp_w: int, exp_h: int, max_bytes: int, label: str
    ) -> str | None:
        """Return an error message string or None if OK."""
        size = path.stat().st_size
        if size > max_bytes:
            return (
                f"[{label}] 용량 초과: {path.name} = {size} bytes "
                f"(max {max_bytes})"
            )
        try:
            with pil_open_buffer(path) as im:
                if im.format != "PNG":
                    return f"[{label}] PNG가 아님: {path.name} format={im.format}"
                if im.mode != "RGBA":
                    return f"[{label}] RGBA가 아님: {path.name} mode={im.mode}"
                if im.size != (exp_w, exp_h):
                    return (
                        f"[{label}] 해상도 불일치: {path.name} "
                        f"{im.size} (expected {(exp_w, exp_h)})"
                    )
        except (OSError, ImageReadError) as exc:
            return f"[{label}] 이미지 열기 실패: {path.resolve()} ({exc})"
        return None
