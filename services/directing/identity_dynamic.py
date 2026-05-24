"""Dynamic IPAdapter / identity weight by framing and expression intensity."""

from __future__ import annotations

import os
import sys

from services.pose.expression_override import ExpressionStrength


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def resolve_dynamic_identity_weight(
    framing: str,
    *,
    layout_type: str = "",
    expression_intensity: ExpressionStrength | str = "strong",
) -> float:
    """
    closeup / neutral → 0.60–0.65
    action_pose / reaction_burst → 0.35–0.50
    full_body → 0.30–0.45
    extreme expression → -0.05
    """
    key = (framing or "").strip().lower()
    lt = (layout_type or "").strip().lower()
    if lt == "reaction_burst":
        key = "reaction_burst"
    base = _env_float("COMFYUI_IPADAPTER_WEIGHT", 0.65)

    if key in ("closeup", "upper_body"):
        w = 0.62
    elif key in ("action_pose", "reaction_burst", "diagonal_pose"):
        w = 0.42
    elif key in ("full_body", "sitting_pose", "lying_pose"):
        w = 0.38
    elif key in ("side_pose", "leaning_pose"):
        w = 0.45
    else:
        w = 0.50

    intens = str(expression_intensity or "").strip().lower()
    if intens == "extreme":
        w -= 0.05
    elif intens == "low":
        w += 0.03

    return max(0.25, min(0.72, w))


def log_identity_dynamic(cut_id: str, framing: str, weight: float) -> None:
    print(
        f"[IDENTITY_DYNAMIC] cut={cut_id} framing={framing} weight={weight:.2f}",
        file=sys.stderr,
    )
