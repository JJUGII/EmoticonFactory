"""Shared cut planning fields (engine-neutral; sourced from custom_templates.json)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CutSpec:
    id: str
    text: str
    emotion: str
    facial_expression: str
    body_pose: str
    prop: str
    action: str
    motion_hint: str
    layout_type: str
    text_position: str
    importance: str
    risk_notes: str

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> CutSpec:
        return cls(
            id=str(row.get("id", "")).strip().zfill(2),
            text=str(row.get("text", "")),
            emotion=str(row.get("emotion", "")),
            facial_expression=str(row.get("facial_expression", "")),
            body_pose=str(row.get("body_pose", "")),
            prop=str(row.get("prop", "none")),
            action=str(row.get("action", "")),
            motion_hint=str(row.get("motion_hint", "")),
            layout_type=str(row.get("layout_type", "square_full_body")),
            text_position=str(row.get("text_position", "bottom")),
            importance=str(row.get("importance", "")),
            risk_notes=str(row.get("risk_notes", "")),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "text": self.text,
            "emotion": self.emotion,
            "facial_expression": self.facial_expression,
            "body_pose": self.body_pose,
            "prop": self.prop,
            "action": self.action,
            "motion_hint": self.motion_hint,
            "layout_type": self.layout_type,
            "text_position": self.text_position,
            "importance": self.importance,
            "risk_notes": self.risk_notes,
        }
