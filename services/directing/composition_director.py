"""Per-cut composition / framing diversity (max 3 identical framings per 16-cut job)."""

from __future__ import annotations

import sys
from dataclasses import dataclass

# User-facing framing ids (logged as framing=)
FRAMING_TYPES: tuple[str, ...] = (
    "closeup",
    "upper_body",
    "full_body",
    "side_pose",
    "diagonal_pose",
    "action_pose",
    "sitting_pose",
    "leaning_pose",
    "lying_pose",
)

# Spread across 16 cuts — each type appears twice except closeup/upper_body (3x max enforced by counter)
FRAMING_SCHEDULE: tuple[str, ...] = (
    "upper_body",
    "full_body",
    "diagonal_pose",
    "closeup",
    "action_pose",
    "side_pose",
    "sitting_pose",
    "leaning_pose",
    "upper_body",
    "full_body",
    "diagonal_pose",
    "action_pose",
    "side_pose",
    "sitting_pose",
    "leaning_pose",
    "closeup",
)

_CAMERA_BY_FRAMING: dict[str, str] = {
    "closeup": "straight",
    "upper_body": "straight",
    "full_body": "medium_wide",
    "side_pose": "side_three_quarter",
    "diagonal_pose": "diagonal",
    "action_pose": "diagonal_low",
    "sitting_pose": "low_front",
    "leaning_pose": "diagonal_high",
}

_POSE_BY_FRAMING: dict[str, str] = {
    "closeup": "expressive_face_turn",
    "upper_body": "gesture_forward",
    "full_body": "standing_full_silhouette",
    "side_pose": "profile_stance",
    "diagonal_pose": "lean_diagonal",
    "action_pose": "dynamic_action_line",
    "sitting_pose": "seated_floor_or_chair",
    "leaning_pose": "lean_forward",
    "lying_pose": "horizontal_sprawl",
}

# Map directing framing → legacy pose_director camera_framing key
_TO_CAMERA_FRAMING: dict[str, str] = {
    "closeup": "closeup",
    "upper_body": "upper_body",
    "full_body": "medium_shot",
    "side_pose": "side_view",
    "diagonal_pose": "dynamic_angle",
    "action_pose": "dynamic_angle",
    "sitting_pose": "medium_shot",
    "leaning_pose": "tilted_pose",
    "lying_pose": "medium_shot",
}


@dataclass(frozen=True)
class CompositionAssignment:
    framing: str
    camera: str
    pose: str
    camera_framing: str
    composition_hint: str


class CompositionDirector:
    """Assign diverse framing; cap identical framing at 3 per job."""

    def __init__(self, *, max_same_framing: int = 3) -> None:
        self._max_same = max_same_framing
        self._counts: dict[str, int] = {}

    def iter_framing_candidates(
        self,
        cut_index: int,
        *,
        layout_type: str = "",
    ) -> list[str]:
        lt = (layout_type or "").strip().lower()
        preferred = _layout_override(lt)
        candidates: list[str] = []
        if preferred:
            candidates.append(preferred)
        start = cut_index % len(FRAMING_SCHEDULE)
        for i in range(len(FRAMING_SCHEDULE) * 2):
            candidates.append(FRAMING_SCHEDULE[(start + i) % len(FRAMING_SCHEDULE)])
        seen: set[str] = set()
        ordered: list[str] = []
        for f in candidates:
            if f not in seen:
                seen.add(f)
                ordered.append(f)
        return ordered

    def _build_assignment(self, framing: str) -> CompositionAssignment:
        camera = _CAMERA_BY_FRAMING.get(framing, "diagonal")
        pose = _POSE_BY_FRAMING.get(framing, "gesture_forward")
        cam_f = _TO_CAMERA_FRAMING.get(framing, "upper_body")
        hint = _composition_hint(framing)
        return CompositionAssignment(
            framing=framing,
            camera=camera,
            pose=pose,
            camera_framing=cam_f,
            composition_hint=hint,
        )

    def assign(
        self,
        cut_id: str,
        cut_index: int,
        *,
        layout_type: str = "",
        emotion_category: str = "",
    ) -> CompositionAssignment:
        _ = emotion_category
        ordered = self.iter_framing_candidates(cut_index, layout_type=layout_type)
        framing = ordered[0]
        for cand in ordered:
            if self._counts.get(cand, 0) < self._max_same:
                framing = cand
                break
        else:
            framing = min(self._counts, key=self._counts.get) if self._counts else ordered[0]
        self._counts[framing] = self._counts.get(framing, 0) + 1
        return self._build_assignment(framing)

    def preview_framing(self, framing: str) -> CompositionAssignment:
        """Build assignment without incrementing per-job framing counts."""
        return self._build_assignment(framing)

    def commit_framing(self, framing: str) -> CompositionAssignment:
        """Commit framing after diversity enforcer accepts."""
        self._counts[framing] = self._counts.get(framing, 0) + 1
        return self._build_assignment(framing)

    def assign_framing(self, framing: str) -> CompositionAssignment:
        """Preview + commit (use preview/commit in reroll loops)."""
        return self.commit_framing(framing)


def _layout_override(layout_type: str) -> str | None:
    if layout_type in ("face_closeup",):
        return "closeup"
    if layout_type in ("half_body",):
        return "upper_body"
    if layout_type in ("square_full_body",):
        return "full_body"
    if layout_type in ("lying_pose",):
        return "sitting_pose"
    if layout_type in ("reaction_burst",):
        return "action_pose"
    return None


def _composition_hint(framing: str) -> str:
    """Short framing keywords only (no camera arc / staging prose)."""
    hints = {
        "closeup": "face closeup, off center",
        "upper_body": "waist up, arms visible",
        "full_body": "full body, feet visible",
        "side_pose": "side view, turned body",
        "diagonal_pose": "diagonal pose",
        "action_pose": "action pose, limbs out",
        "sitting_pose": "sitting pose, knees visible",
        "leaning_pose": "leaning pose",
        "lying_pose": "lying down",
    }
    return hints.get(framing, "waist up, arms visible")


def log_composition_director(cut_id: str, assignment: CompositionAssignment) -> None:
    print(
        f"[COMPOSITION_DIRECTOR] cut={cut_id} framing={assignment.framing} "
        f"camera={assignment.camera} pose={assignment.pose}",
        file=sys.stderr,
    )
