"""Persist user candidate selection feedback under ``character_candidates/``."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FEEDBACK_FILENAME = "candidate_feedback.json"


def write_candidate_feedback(
    package_dir: Path,
    *,
    selected_candidate: int,
    candidate_count: int = 3,
    reason_tags: list[str] | None = None,
    source_reference: str = "",
    canonical_sheet_used: bool = False,
) -> Path:
    """Write ``candidate_feedback.json`` (v0.5: selected=5 stars, others 0)."""
    n = max(1, min(16, int(candidate_count)))
    scores: dict[str, int] = {str(i): 0 for i in range(1, n + 1)}
    scores[str(int(selected_candidate))] = 5
    payload: dict[str, Any] = {
        "selected_candidate": int(selected_candidate),
        "scores": scores,
        "reason_tags": list(reason_tags or []),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_reference": source_reference,
        "canonical_sheet_used": bool(canonical_sheet_used),
    }
    cdir = package_dir / "character_candidates"
    cdir.mkdir(parents=True, exist_ok=True)
    path = cdir / FEEDBACK_FILENAME
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
