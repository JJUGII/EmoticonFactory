"""API request/response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

JobPhase = Literal[
    "created",
    "uploaded",
    "candidates_running",
    "candidates_ready",
    "canonical_selected",
    "emoticons_running",
    "completed",
    "failed",
]

CutStatus = Literal["pending", "running", "done", "failed"]


class JobCreateResponse(BaseModel):
    job_id: str


class UploadResponse(BaseModel):
    job_id: str
    preview_url: str
    filename: str


class GenerateCandidatesRequest(BaseModel):
    job_id: str
    generator: str = "openai"
    species_hint: str = ""
    theme: str = "사랑"
    art_style: str = "illustration"  # "illustration" | "realistic"


class CandidateItem(BaseModel):
    index: int
    url: str
    style_hint: str | None = None


class CandidatesResponse(BaseModel):
    job_id: str
    candidates: list[CandidateItem]


class SelectCandidateRequest(BaseModel):
    job_id: str
    candidate_index: int = Field(ge=1, le=8)


class GenerateEmoticonsRequest(BaseModel):
    job_id: str
    emotions: list[str] = Field(min_length=16, max_length=16)
    generator: str = "openai"
    theme: str = "사랑"
    species_hint: str = ""
    grid_mode: bool = False
    art_style: str = "illustration"  # "illustration" | "realistic"


class CutProgressItem(BaseModel):
    id: str
    text: str
    status: CutStatus
    url: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    phase: JobPhase
    progress: int
    message: str
    current_cut: str | None = None
    cuts: list[CutProgressItem] = Field(default_factory=list)
    error: str | None = None
    log_tail: str | None = None


class ResultResponse(BaseModel):
    job_id: str
    package_dir: str
    preview: dict[str, Any] | None = None
    cuts: list[CutProgressItem]
    canonical_url: str | None = None


class EmotionsDefaultsResponse(BaseModel):
    emotions: list[str]
