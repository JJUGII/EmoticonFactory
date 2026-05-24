"""Keep all typography out of diffusion; render via Pillow post-process."""

from __future__ import annotations

import sys


def no_text_generation_positive() -> str:
    return (
        "NO TEXT, NO LETTERS, NO TYPOGRAPHY, no caption area drawn, "
        "no speech bubble text, empty space reserved for caption overlay later"
    )


def no_text_generation_negative() -> str:
    return (
        "text, letters, words, typography, korean characters, hangul, "
        "watermark, caption, subtitle, logo text, speech bubble letters, "
        "written words, font, signage, UI text"
    )


def log_text_render_plan(
    cut_id: str,
    *,
    text: str,
    position: str,
    enabled: bool,
) -> None:
    if not enabled or not (text or "").strip():
        print(
            f"[TEXT_RENDER] cut={cut_id} enabled=false (no overlay)",
            file=sys.stderr,
        )
        return
    pos = (position or "bottom").strip().lower()
    print(
        f"[TEXT_RENDER] cut={cut_id} enabled=true position={pos} "
        f"font=Pretendard-Bold pipeline=pillow_overlay",
        file=sys.stderr,
    )
