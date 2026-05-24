"""Prototype animated WebP export for Kakao-style big-emoticons (v0.4).

카카오 제출용 최종 검수·변환은 전용 안내 및 제작 도구를 따르세요. 이 모듈은 사전 검토·프로토타입입니다."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw

from config import EMOTICON_SIZE, MAX_WEBP_ANIM_BYTES, MAX_WEBP_ANIM_FRAMES
from services.image_io import (
    ImageReadError,
    pil_animation_frame_rgba,
    pil_open_image,
    pil_save_image,
)

# 순서대로 선택: 기본 3개는 01/03/10, 네 번째 필요 시 blink(04).
WEBP_ANIMATION_TARGETS: list[tuple[str, str]] = [
    ("01", "heart_pop"),
    ("03", "bounce"),
    ("10", "sleep"),
    ("04", "blink"),
]


def safe_webp_filename(cut_id: str, sticker_text: str) -> str:
    t = (sticker_text or "").strip() or "cut"
    for ch in '<>:"/\\|?*':
        t = t.replace(ch, "_")
    t = re.sub(r"\s+", "_", t).strip("_") or "cut"
    return f"{cut_id}_{t}.webp"


class WebPAnimator:
    """Pillow 네이티브 WebP 애니메이션. 마지막 프레임은 항상 정지 원본(source)과 동일."""

    def __init__(
        self,
        max_bytes: int = MAX_WEBP_ANIM_BYTES,
        max_frames_including_still: int = MAX_WEBP_ANIM_FRAMES,
    ) -> None:
        self.max_bytes = max_bytes
        self.max_frames_including_still = max_frames_including_still
        self.last_encode_meta: dict[str, Any] = {}

    def _load_base(self, source_path: Path) -> Image.Image:
        base = pil_open_image(source_path).convert("RGBA")
        tw, th = EMOTICON_SIZE
        if base.size != (tw, th):
            base = base.resize((tw, th), Image.Resampling.LANCZOS)
        return base

    def _cap_motion(self, motion_len: int) -> int:
        """Motion 길이(정지 포함 전 길이 - 1) 상한."""
        return max(2, min(motion_len, self.max_frames_including_still - 1))

    def _save_animation(
        self,
        frames: list[Image.Image],
        output_path: Path,
        *,
        duration_ms: int,
        loops: int,
        quality: int,
    ) -> None:
        if not frames:
            raise ValueError("no frames")
        if len(frames) == 1:
            pil_save_image(
                frames[0],
                output_path,
                format="WEBP",
                lossless=False,
                quality=quality,
                method=6,
            )
            return
        pil_save_image(
            frames[0],
            output_path,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            duration=[duration_ms] * len(frames),
            loop=loops,
            lossless=False,
            quality=quality,
            method=6,
        )

    def _thin_motion_preserving_still(self, frames: list[Image.Image]) -> list[Image.Image]:
        """frames[-1] 은 정지 원본으로 유지. motion 구간만 듬."""
        if len(frames) <= 4:
            return frames
        still = frames[-1]
        motion = frames[:-1]
        if len(motion) <= 3:
            return frames
        inner = motion[1:-1]
        inner_t = inner[::2] if inner else []
        new_motion = [motion[0]] + inner_t + [motion[-1]]
        return new_motion + [still]

    def _encode_until_budget(
        self,
        frames: list[Image.Image],
        output_path: Path,
        *,
        loops: int,
        quality_start: int,
        duration_ms: int,
    ) -> dict[str, Any]:
        work = [f.copy().convert("RGBA") for f in frames]
        q = max(40, min(100, int(quality_start)))
        meta: dict[str, Any] = {}
        for _ in range(48):
            self._save_animation(work, output_path, duration_ms=duration_ms, loops=loops, quality=q)
            sz = output_path.stat().st_size
            ok_size = sz <= self.max_bytes
            ok_len = len(work) <= self.max_frames_including_still
            meta = {
                "bytes": sz,
                "frames": len(work),
                "quality": q,
                "loops": loops,
                "duration_ms": duration_ms,
            }
            if ok_size and ok_len:
                meta["ok"] = True
                self.last_encode_meta = meta
                return meta
            if not ok_len and len(work) > 3:
                work = self._thin_motion_preserving_still(work)
                q = min(92, q + 4)
                continue
            if not ok_size and q > 42:
                q -= 6
                continue
            if not ok_size and len(work) > 3:
                work = self._thin_motion_preserving_still(work)
                q = min(92, q + 3)
                continue
            break
        meta["ok"] = output_path.stat().st_size <= self.max_bytes
        if not meta["ok"]:
            meta["warn"] = "over_budget_after_reduction"
        self.last_encode_meta = meta
        return meta

    def optimize_webp(
        self,
        output_path: Path,
        max_bytes: int | None = None,
        *,
        quality_floor: int = 38,
    ) -> dict[str, Any]:
        """이미 저장된 WebP를 다시 읽어 용량 맞춤(품질↓ → 프레임 듬)."""
        budget = max_bytes if max_bytes is not None else self.max_bytes
        meta: dict[str, Any] = {"path": str(output_path)}
        if not output_path.is_file():
            meta["error"] = "file_missing"
            return meta

        frames = pil_animation_frame_rgba(output_path)

        q = 85
        duration_ms = 90
        loops = 4
        for _ in range(40):
            self._save_animation(
                frames, output_path, duration_ms=duration_ms, loops=loops, quality=q
            )
            sz = output_path.stat().st_size
            meta.update({"bytes": sz, "frames": len(frames), "quality": q})
            if sz <= budget:
                meta["ok"] = True
                return meta
            if q > quality_floor:
                q -= 6
                continue
            if len(frames) > 4:
                frames = self._thin_motion_preserving_still(frames)
                q = min(90, q + 4)
                continue
            break
        meta["ok"] = output_path.stat().st_size <= budget
        if not meta["ok"]:
            meta["warn"] = "may_exceed_budget"
        return meta

    def create_bounce_animation(
        self,
        source_path: Path,
        output_path: Path,
        frames: int = 12,
        loops: int = 4,
        *,
        quality: int = 85,
        duration_ms: int = 85,
    ) -> Path:
        base = self._load_base(source_path)
        still = base.copy()
        w, h = base.size

        fm = self._cap_motion(frames)
        motion: list[Image.Image] = []
        amp = 7
        for i in range(fm):
            t = (i / max(fm - 1, 1)) * 2 * math.pi
            dy = int(round(amp * math.sin(t)))
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.paste(base, (0, dy), base)
            motion.append(canvas)

        all_fr = motion + [still]
        self._encode_until_budget(
            all_fr,
            output_path,
            loops=loops,
            quality_start=quality,
            duration_ms=duration_ms,
        )
        return output_path

    def _heart_overlay(self, frm: Image.Image, cx: int, cy: int, scale: float, pulse: float) -> None:
        drw = ImageDraw.Draw(frm)
        alpha = int(140 + pulse * 110)
        pink = (255, 135, 180, alpha)
        self._heart_shape(drw, float(cx), float(cy), scale, pink)

    def _heart_shape(
        self,
        draw: ImageDraw.ImageDraw,
        cx: float,
        cy: float,
        scale: float,
        fill: tuple[int, int, int, int],
    ) -> None:
        rr = scale * 0.22
        ox1 = cx - rr * 0.9
        oy1 = cy - rr * 0.45
        ox2 = cx + rr * 0.9
        oy2 = cy - rr * 0.45
        bbox1 = [ox1 - rr, oy1 - rr, ox1 + rr, oy1 + rr]
        bbox2 = [ox2 - rr, oy2 - rr, ox2 + rr, oy2 + rr]
        draw.ellipse(bbox1, fill=fill)
        draw.ellipse(bbox2, fill=fill)
        tri = [
            (cx, cy + scale * 0.78),
            (cx - scale * 0.86, cy - rr * 0.2),
            (cx + scale * 0.86, cy - rr * 0.2),
        ]
        draw.polygon(tri, fill=fill)

    def create_heart_pop_animation(
        self,
        source_path: Path,
        output_path: Path,
        frames: int = 16,
        loops: int = 4,
        *,
        quality: int = 85,
        duration_ms: int = 85,
    ) -> Path:
        base = self._load_base(source_path)
        still = base.copy()
        w, h = base.size

        fm = max(3, self._cap_motion(frames))
        cx, cy = int(w * 0.52), int(h * 0.74)
        motion: list[Image.Image] = []
        for i in range(fm):
            u = i / max(fm - 1, 1)
            pulse = math.sin(u * math.pi)
            scale = float(24 + pulse * 72)
            frm = base.copy()
            self._heart_overlay(frm, cx, cy, scale, pulse)
            lite = float(34 + pulse * 40)
            self._heart_overlay(frm, cx + int(42 * pulse), cy - int(28 * pulse), lite, pulse * 0.6)
            motion.append(frm)

        all_fr = motion + [still]
        self._encode_until_budget(
            all_fr,
            output_path,
            loops=loops,
            quality_start=quality,
            duration_ms=duration_ms,
        )
        return output_path

    def create_sleep_animation(
        self,
        source_path: Path,
        output_path: Path,
        frames: int = 16,
        loops: int = 4,
        *,
        quality: int = 85,
        duration_ms: int = 90,
    ) -> Path:
        base = self._load_base(source_path)
        still = base.copy()
        w, h = base.size
        fm = max(3, self._cap_motion(frames))
        cx = int(w * 0.55)

        motion: list[Image.Image] = []
        for i in range(fm):
            t = i / max(fm - 1, 1)
            ang = 1.1 * math.sin(t * 2 * math.pi)
            squ = base.rotate(ang, resample=Image.Resampling.BICUBIC, expand=False)
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.paste(squ, (0, 0), squ)
            drw = ImageDraw.Draw(canvas)
            drift = int(18 * math.sin(math.pi * t))
            zalpha = int(110 + 90 * math.sin(t * math.pi * 2))
            zblue = (95, 95, 180, zalpha)
            drw.text((cx - 8, 22 + drift), "Z", fill=zblue)
            drw.text((cx + 10, 8 + drift), "z", fill=(95, 95, 160, max(35, zalpha // 3)))
            drw.text((cx + 24, drift), "z", fill=(110, 110, 175, max(35, zalpha // 4)))
            motion.append(canvas)

        all_fr = motion + [still]
        self._encode_until_budget(
            all_fr,
            output_path,
            loops=loops,
            quality_start=quality,
            duration_ms=duration_ms,
        )
        return output_path

    def create_blink_animation(
        self,
        source_path: Path,
        output_path: Path,
        frames: int = 12,
        loops: int = 4,
        *,
        quality: int = 85,
        duration_ms: int = 85,
    ) -> Path:
        base = self._load_base(source_path)
        still = base.copy()
        w, h = base.size
        fm = max(3, self._cap_motion(frames))
        motion: list[Image.Image] = []

        for i in range(fm):
            u = math.sin((i / max(fm - 1, 1)) * math.pi)
            sy = 1.0 - u * 0.065
            nh = max(8, int(h * sy))
            squashed = base.resize((w, nh), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            oy = (h - nh) // 2
            canvas.paste(squashed, (0, oy), squashed)
            motion.append(canvas)

        all_fr = motion + [still]
        self._encode_until_budget(
            all_fr,
            output_path,
            loops=loops,
            quality_start=quality,
            duration_ms=duration_ms,
        )
        return output_path

    def dispatch(
        self,
        animation: str,
        source_path: Path,
        output_path: Path,
        *,
        loops: int = 4,
        quality: int = 85,
        motion_frames: int | None = None,
    ) -> dict[str, Any]:
        by_name: dict[str, Callable[..., Path]] = {
            "bounce": self.create_bounce_animation,
            "heart_pop": self.create_heart_pop_animation,
            "sleep": self.create_sleep_animation,
            "blink": self.create_blink_animation,
        }
        fn = by_name.get(animation)
        if fn is None:
            return {"ok": False, "error": f"unknown_animation:{animation}"}
        mf = motion_frames
        defaults = {"bounce": 12, "heart_pop": 16, "sleep": 16, "blink": 12}
        nf = mf if mf is not None else defaults.get(animation, 12)
        fn(source_path, output_path, frames=nf, loops=loops, quality=quality)
        enc = dict(self.last_encode_meta)
        sz = output_path.stat().st_size if output_path.is_file() else enc.get("bytes", 0)
        ok = bool(enc.get("ok")) and output_path.is_file()
        nf_enc = enc.get("frames", 0)
        if nf_enc > self.max_frames_including_still:
            ok = False
        return {
            "ok": ok,
            "path": str(output_path.resolve()),
            "bytes": sz,
            "frames": nf_enc,
            "quality": enc.get("quality"),
            "loops": enc.get("loops", loops),
        }


def build_default_webp_pack(
    *,
    items_by_id: dict[str, dict[str, Any]],
    sticker_dir: Path,
    webp_dir: Path,
    webp_count: int,
    loops: int,
    quality: int,
    animator: WebPAnimator | None = None,
) -> dict[str, Any]:
    """기본 컷 목록에서 ``webp_count`` 개 WebP 생성; ``meta/webp_report`` 용 dict 반환."""
    anim = animator or WebPAnimator()
    webp_dir.mkdir(parents=True, exist_ok=True)
    report_items: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx, (cut_id, anim_name) in enumerate(WEBP_ANIMATION_TARGETS):
        if idx >= max(1, min(webp_count, len(WEBP_ANIMATION_TARGETS))):
            break
        item = items_by_id.get(cut_id)
        text = str(item.get("text", "")) if item else cut_id
        src = sticker_dir / f"{cut_id}.png"
        if not src.is_file():
            errors.append(f"missing_sticker:{cut_id}")
            report_items.append(
                {
                    "id": cut_id,
                    "animation": anim_name,
                    "error": "missing_source_png",
                    "expected_source": str(src),
                }
            )
            continue
        fn = safe_webp_filename(cut_id, text)
        out = webp_dir / fn
        meta = anim.dispatch(anim_name, src, out, loops=loops, quality=quality)
        sz = out.stat().st_size if out.is_file() else 0
        nfr = int(meta.get("frames") or 0)
        wh_ok = False
        if out.is_file():
            try:
                verify = pil_open_image(out)
                wh_ok = verify.size == EMOTICON_SIZE
            except ImageReadError:
                wh_ok = False

        report_items.append(
            {
                "id": cut_id,
                "text": text,
                "animation": anim_name,
                "relative_path": f"webp/{fn}",
                "bytes": sz,
                "frame_count": nfr,
                "loops": loops,
                "quality_final": meta.get("quality"),
                "ok": bool(meta.get("ok")) and sz <= anim.max_bytes and wh_ok,
                "last_frame_is_exact_source_png": True,
            }
        )

    return {
        "webp_dir": str(webp_dir.resolve()),
        "loops": loops,
        "quality_start": quality,
        "max_bytes": anim.max_bytes,
        "max_frames": anim.max_frames_including_still,
        "items": report_items,
        "errors": errors,
    }
