"""Assemble per-cut Comfy execution profile (prompt + sampler + identity)."""

from __future__ import annotations

from dataclasses import dataclass

from services.directing.adaptive_sampler import resolve_adaptive_denoise
from services.directing.composition_constraints import (
    composition_hard_negative,
    composition_hard_positive,
)
from services.directing.identity_dynamic import resolve_dynamic_identity_weight
from services.directing.pose_strength import load_comfyui_pose_strength, pose_strength_positive_block
from services.directing.text_safe_zone import text_safe_zone_negative, text_safe_zone_positive
from services.pose.expression_override import ExpressionStrength


@dataclass(frozen=True)
class CutExecutionProfile:
    framing: str
    layout_type: str
    identity_weight: float
    denoise: float
    hard_positive: str
    hard_negative: str
    pose_strength_block: str
    text_safe_positive: str
    text_safe_negative: str


def build_cut_execution_profile(
    *,
    framing: str,
    layout_type: str = "",
    expression_intensity: ExpressionStrength | str = "strong",
    text_position: str = "bottom",
    pose_token: str = "dynamic pose and body acting",
) -> CutExecutionProfile:
    hard_pos = composition_hard_positive(framing, layout_type)
    hard_neg = composition_hard_negative()
    pose_block = pose_strength_positive_block(pose_token)
    return CutExecutionProfile(
        framing=framing,
        layout_type=layout_type,
        identity_weight=resolve_dynamic_identity_weight(
            framing,
            layout_type=layout_type,
            expression_intensity=expression_intensity,
        ),
        denoise=resolve_adaptive_denoise(framing, layout_type=layout_type),
        hard_positive=hard_pos,
        hard_negative=hard_neg,
        pose_strength_block=pose_block,
        text_safe_positive=text_safe_zone_positive(text_position=text_position),
        text_safe_negative=text_safe_zone_negative(),
    )
