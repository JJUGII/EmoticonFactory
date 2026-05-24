"""Reroll pose / framing / hand when too similar to recent cuts."""

from __future__ import annotations

from collections import deque


class DirectingDiversityTracker:
    """If framing, pose_type, and hand_action match any of last N cuts → duplicate."""

    def __init__(self, *, history_len: int = 2) -> None:
        self._history: deque[tuple[str, str, str]] = deque(maxlen=history_len)

    def would_duplicate(self, framing: str, pose_type: str, hand_action_id: str) -> bool:
        key = (framing, pose_type, hand_action_id)
        return key in self._history

    def register(self, framing: str, pose_type: str, hand_action_id: str) -> None:
        self._history.append((framing, pose_type, hand_action_id))
