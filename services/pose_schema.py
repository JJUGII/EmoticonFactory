"""Pydantic schema for each big-emoticon cut (pose / prop / layout)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class LayoutType(str, Enum):
    """Framing archetype per cut."""

    square_full_body = "square_full_body"
    face_closeup = "face_closeup"
    half_body = "half_body"
    lying_pose = "lying_pose"
    reaction_burst = "reaction_burst"


class TextPosition(str, Enum):
    """Caption placement."""

    top = "top"
    bottom = "bottom"
    left = "left"
    right = "right"
    none = "none"


class BigEmoticonPose(BaseModel):
    """Structured shot plan: pose, props, typography, QA hints."""

    id: str
    text: str
    emotion: str
    facial_expression: str = Field(description="얼굴 연기 키워드")
    body_pose: str = Field(description="전신 포즈 묘사")
    prop: str = Field(description="소품 ID 또는 none")
    action: str
    motion_hint: str = Field(description="애니/모션 참고용")
    layout_type: LayoutType
    text_position: TextPosition
    importance: str = "medium"
    risk_notes: str = ""

    model_config = {"extra": "ignore"}
