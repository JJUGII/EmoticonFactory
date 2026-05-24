"""Post-run sticker directing metrics report."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def build_directing_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Each record: cut_id, framing, camera, body_direction, body_visibility_score, rerolls..."""
    n = max(1, len(records))
    framings = [str(r.get("directing_framing") or r.get("framing") or "") for r in records]
    framing_counts = Counter(fr for fr in framings if fr)
    closeup_n = framing_counts.get("closeup", 0) + framing_counts.get("upper_body", 0)
    full_body_n = framing_counts.get("full_body", 0) + framing_counts.get("sitting_pose", 0)
    action_n = framing_counts.get("action_pose", 0) + framing_counts.get("reaction_burst", 0)

    vis_scores = [
        float(r["body_visibility_score"])
        for r in records
        if r.get("body_visibility_score") is not None
    ]
    avg_vis = sum(vis_scores) / len(vis_scores) if vis_scores else 0.0

    reroll_framing = sum(1 for r in records if r.get("framing_reroll"))
    reroll_directing = sum(1 for r in records if r.get("directing_reroll"))
    body_rerender = sum(1 for r in records if r.get("body_visibility_rerender"))

    unique_framing = len(set(fr for fr in framings if fr))
    unique_camera = len(
        {str(r.get("directing_camera") or r.get("camera") or "") for r in records}
        - {""}
    )

    return {
        "cut_count": len(records),
        "closeup_upper_ratio": round(closeup_n / n, 3),
        "full_body_ratio": round(full_body_n / n, 3),
        "action_pose_ratio": round(action_n / n, 3),
        "framing_diversity_unique": unique_framing,
        "camera_diversity_unique": unique_camera,
        "framing_distribution": dict(framing_counts),
        "avg_body_visibility_score": round(avg_vis, 3),
        "framing_reroll_count": reroll_framing,
        "directing_reroll_count": reroll_directing,
        "body_visibility_rerender_count": body_rerender,
    }


def log_directing_report(report: dict[str, Any]) -> None:
    print("[DIRECTING_REPORT] " + json.dumps(report, ensure_ascii=False), file=sys.stderr)


def write_directing_report(package_dir: Path, report: dict[str, Any]) -> Path:
    path = Path(package_dir) / "meta" / "directing_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
