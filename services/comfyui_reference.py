"""ComfyUI reference image logging (canonical character vs photo)."""

from __future__ import annotations

import sys
from pathlib import Path


def log_comfyui_reference(
    canonical_path: Path,
    *,
    source_mode: str,
    reference_kind: str = "canonical_character",
) -> None:
    resolved = canonical_path.resolve()
    print(f"[REFERENCE] source={reference_kind}", file=sys.stderr)
    print(f"[REFERENCE] source_mode={source_mode}", file=sys.stderr)
    print(f"[REFERENCE] canonical_path={resolved}", file=sys.stderr)
