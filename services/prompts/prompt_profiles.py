"""Environment-driven prompt pipeline settings (engine × source × output)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from config import PROJECT_ROOT

SourceMode = Literal["photo", "illustration", "character", "auto"]
OutputMode = Literal["sticker", "illustration"]
StrengthLevel = Literal["low", "medium", "strong"]
EngineName = Literal["openai", "comfyui", "mock"]

_STRENGTH_FLOAT = {"low": 0.35, "medium": 0.65, "strong": 0.92}


def _norm_mode(raw: str | None, allowed: frozenset[str], default: str) -> str:
    v = (raw or "").strip().lower() or default
    return v if v in allowed else default


def _norm_strength(raw: str | None, default: str = "medium") -> StrengthLevel:
    v = (raw or "").strip().lower() or default
    if v not in _STRENGTH_FLOAT:
        return "medium"  # type: ignore[return-value]
    return v  # type: ignore[return-value]


@dataclass(frozen=True)
class EnginePromptTuning:
    emotion_strength: float
    pose_variation: float
    identity_lock: float


@dataclass(frozen=True)
class PromptPipelineSettings:
    source_mode: SourceMode
    output_mode: OutputMode
    openai: EnginePromptTuning
    comfyui: EnginePromptTuning
    comfyui_mode: OutputMode
    sticker_drift_threshold: float
    illustration_drift_threshold: float

    def drift_threshold(self) -> float:
        if self.output_mode == "illustration":
            return self.illustration_drift_threshold
        return self.sticker_drift_threshold

    def tuning_for(self, engine: str) -> EnginePromptTuning:
        if engine == "comfyui":
            return self.comfyui
        return self.openai


def resolve_source_mode(
    reference_type: str | None,
    override: str | None = None,
    *,
    settings: PromptPipelineSettings | None = None,
) -> SourceMode:
    o = (override or "").strip().lower()
    if o in ("photo", "illustration", "character"):
        return o  # type: ignore[return-value]
    base = settings.source_mode if settings else "auto"
    if base != "auto":
        return base  # type: ignore[return-value]
    rt = str(reference_type or "").strip().lower()
    if rt == "character_art":
        return "illustration"
    if rt == "photo":
        return "photo"
    return "photo"


def resolve_output_mode(
    override: str | None = None,
    *,
    settings: PromptPipelineSettings | None = None,
    engine: str | None = None,
) -> OutputMode:
    o = (override or "").strip().lower()
    if o in ("sticker", "illustration"):
        return o  # type: ignore[return-value]
    if settings and engine == "comfyui" and settings.comfyui_mode:
        return settings.comfyui_mode
    if settings:
        return settings.output_mode
    return "sticker"


def load_prompt_settings(factory_root: str | None = None) -> PromptPipelineSettings:
    root = Path(factory_root).resolve() if factory_root else PROJECT_ROOT.resolve()
    env_path = root / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    else:
        load_dotenv()

    source = _norm_mode(
        os.getenv("EMOTICON_SOURCE_MODE"),
        frozenset({"photo", "illustration", "character", "auto"}),
        "auto",
    )
    output = _norm_mode(
        os.getenv("EMOTICON_OUTPUT_MODE"),
        frozenset({"sticker", "illustration"}),
        "sticker",
    )
    comfy_mode = _norm_mode(
        os.getenv("COMFYUI_MODE"),
        frozenset({"sticker", "illustration"}),
        output,
    )
    if comfy_mode not in ("sticker", "illustration"):
        comfy_mode = output

    def _tuning(prefix: str) -> EnginePromptTuning:
        return EnginePromptTuning(
            emotion_strength=_STRENGTH_FLOAT[
                _norm_strength(os.getenv(f"{prefix}_EMOTION_STRENGTH"), "medium")
            ],
            pose_variation=_STRENGTH_FLOAT[
                _norm_strength(os.getenv(f"{prefix}_POSE_VARIATION"), "medium")
            ],
            identity_lock=_STRENGTH_FLOAT[
                _norm_strength(os.getenv(f"{prefix}_IDENTITY_LOCK"), "medium")
            ],
        )

    def _drift(name: str, default: float) -> float:
        raw = (os.getenv(name) or "").strip()
        try:
            return max(0.0, min(1.0, float(raw)))
        except ValueError:
            return default

    return PromptPipelineSettings(
        source_mode=source,  # type: ignore[arg-type]
        output_mode=output,  # type: ignore[arg-type]
        openai=_tuning("OPENAI"),
        comfyui=_tuning("COMFYUI"),
        comfyui_mode=comfy_mode,  # type: ignore[arg-type]
        sticker_drift_threshold=_drift("STICKER_DRIFT_THRESHOLD", 0.60),
        illustration_drift_threshold=_drift("ILLUSTRATION_DRIFT_THRESHOLD", 0.72),
    )


def log_prompt_config(settings: PromptPipelineSettings) -> None:
    from services.directing.acting_intensity import load_comfyui_acting_intensity
    from services.pose.expression_override import load_comfyui_expression_strength

    for line in (
        f"[CONFIG] emoticon_source_mode={settings.source_mode}",
        f"[CONFIG] emoticon_output_mode={settings.output_mode}",
        f"[CONFIG] comfyui_mode={settings.comfyui_mode}",
        f"[CONFIG] comfyui_expression_strength={load_comfyui_expression_strength()}",
        f"[CONFIG] comfyui_acting_intensity={load_comfyui_acting_intensity()}",
        f"[CONFIG] sticker_drift_threshold={settings.sticker_drift_threshold}",
        f"[CONFIG] illustration_drift_threshold={settings.illustration_drift_threshold}",
    ):
        print(line, file=sys.stderr)
