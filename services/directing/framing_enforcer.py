"""Forbid repeating camera + framing + body_direction within recent cuts."""

from __future__ import annotations

import sys
from collections import deque


class FramingDiversityEnforcer:
    def __init__(self, *, history_len: int = 4) -> None:
        self._history: deque[tuple[str, str, str]] = deque(maxlen=history_len)

    def would_duplicate(self, camera: str, framing: str, body_direction: str) -> bool:
        key = (
            (camera or "").strip().lower(),
            (framing or "").strip().lower(),
            (body_direction or "").strip().lower(),
        )
        return key in self._history

    def register(self, camera: str, framing: str, body_direction: str) -> None:
        self._history.append(
            (
                (camera or "").strip().lower(),
                (framing or "").strip().lower(),
                (body_direction or "").strip().lower(),
            )
        )


def log_framing_reroll(
    cut_id: str,
    *,
    camera: str,
    framing: str,
    body_direction: str,
    attempt: int,
) -> None:
    print(
        f"[FRAMING_REROLL] cut={cut_id} attempt={attempt} "
        f"camera={camera} framing={framing} body_direction={body_direction}",
        file=sys.stderr,
    )
