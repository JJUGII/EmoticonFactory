"""OpenPose-style stick maps + ControlNet workflow patching (graceful fallback)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.comfyui_client import ComfyUIClient

# Line segments (x0,y0,x1,y1) in 0..1 normalized coords — OpenPose-ish stick figures
_STICK_POSES: dict[str, tuple[tuple[float, float, float, float], ...]] = {
    "standing": (
        (0.50, 0.18, 0.50, 0.42),
        (0.50, 0.42, 0.38, 0.62),
        (0.50, 0.42, 0.62, 0.62),
        (0.38, 0.62, 0.34, 0.88),
        (0.62, 0.62, 0.66, 0.88),
        (0.50, 0.30, 0.32, 0.48),
        (0.50, 0.30, 0.68, 0.48),
    ),
    "jumping_pose": (
        (0.50, 0.20, 0.50, 0.45),
        (0.50, 0.45, 0.42, 0.58),
        (0.50, 0.45, 0.58, 0.58),
        (0.42, 0.58, 0.30, 0.78),
        (0.58, 0.58, 0.72, 0.78),
        (0.50, 0.32, 0.28, 0.22),
        (0.50, 0.32, 0.72, 0.22),
    ),
    "waving_pose": (
        (0.50, 0.18, 0.50, 0.42),
        (0.50, 0.42, 0.40, 0.64),
        (0.50, 0.42, 0.62, 0.64),
        (0.40, 0.64, 0.38, 0.88),
        (0.62, 0.64, 0.64, 0.88),
        (0.50, 0.30, 0.30, 0.38),
        (0.50, 0.30, 0.72, 0.28),
    ),
    "arms_up_celebration": (
        (0.50, 0.20, 0.50, 0.44),
        (0.50, 0.44, 0.40, 0.64),
        (0.50, 0.44, 0.60, 0.64),
        (0.40, 0.64, 0.38, 0.88),
        (0.60, 0.64, 0.62, 0.88),
        (0.50, 0.32, 0.32, 0.12),
        (0.50, 0.32, 0.68, 0.12),
    ),
    "leaning_pose": (
        (0.52, 0.18, 0.56, 0.42),
        (0.56, 0.42, 0.48, 0.64),
        (0.56, 0.42, 0.66, 0.62),
        (0.48, 0.64, 0.44, 0.88),
        (0.66, 0.62, 0.70, 0.86),
        (0.54, 0.30, 0.40, 0.46),
        (0.54, 0.30, 0.70, 0.50),
    ),
    "sitting_pose": (
        (0.50, 0.22, 0.50, 0.46),
        (0.50, 0.46, 0.42, 0.58),
        (0.50, 0.46, 0.58, 0.58),
        (0.42, 0.58, 0.36, 0.72),
        (0.58, 0.58, 0.64, 0.72),
        (0.50, 0.34, 0.38, 0.52),
        (0.50, 0.34, 0.62, 0.52),
    ),
    "curled_pose": (
        (0.48, 0.52, 0.58, 0.58),
        (0.48, 0.52, 0.38, 0.56),
        (0.38, 0.56, 0.32, 0.68),
        (0.58, 0.58, 0.66, 0.66),
        (0.50, 0.48, 0.44, 0.54),
        (0.50, 0.48, 0.56, 0.54),
    ),
    "slumped_shoulders": (
        (0.50, 0.22, 0.48, 0.46),
        (0.48, 0.46, 0.42, 0.66),
        (0.48, 0.46, 0.58, 0.66),
        (0.42, 0.66, 0.40, 0.88),
        (0.58, 0.66, 0.60, 0.88),
        (0.48, 0.34, 0.36, 0.56),
        (0.48, 0.34, 0.60, 0.56),
    ),
    "pointing_accuse": (
        (0.50, 0.18, 0.50, 0.42),
        (0.50, 0.42, 0.42, 0.64),
        (0.50, 0.42, 0.60, 0.64),
        (0.42, 0.64, 0.40, 0.88),
        (0.60, 0.64, 0.62, 0.88),
        (0.50, 0.30, 0.34, 0.44),
        (0.50, 0.30, 0.78, 0.40),
    ),
    "exaggerated_stomp": (
        (0.50, 0.18, 0.50, 0.42),
        (0.50, 0.42, 0.38, 0.62),
        (0.50, 0.42, 0.62, 0.58),
        (0.38, 0.62, 0.34, 0.88),
        (0.62, 0.58, 0.68, 0.82),
        (0.50, 0.30, 0.36, 0.50),
        (0.50, 0.30, 0.64, 0.48),
    ),
    "hug_self": (
        (0.50, 0.20, 0.50, 0.44),
        (0.50, 0.44, 0.44, 0.64),
        (0.50, 0.44, 0.56, 0.64),
        (0.44, 0.64, 0.42, 0.88),
        (0.56, 0.64, 0.58, 0.88),
        (0.50, 0.36, 0.40, 0.50),
        (0.50, 0.36, 0.60, 0.50),
    ),
    "lying_pose": (
        (0.28, 0.58, 0.72, 0.58),
        (0.72, 0.58, 0.82, 0.54),
        (0.28, 0.58, 0.22, 0.56),
        (0.40, 0.58, 0.38, 0.68),
        (0.60, 0.58, 0.62, 0.68),
        (0.30, 0.56, 0.26, 0.52),
        (0.74, 0.56, 0.78, 0.52),
    ),
}

_POSE_ALIASES: dict[str, str] = {
    "tilted_forward": "leaning_pose",
    "jump_back": "jumping_pose",
    "crossed_arms": "standing",
    "listening_pose": "standing",
    "shrug_pose": "standing",
}


@dataclass(frozen=True)
class PoseControlConfig:
    enabled: bool
    control_type: str
    weight: float
    model_name: str


def _env_bool(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def load_pose_control_config() -> PoseControlConfig:
    enabled = _env_bool("COMFYUI_CONTROLNET_POSE")
    model = (os.getenv("COMFYUI_CONTROLNET_MODEL") or "").strip()
    if not model:
        model = "controlnet-openpose-sdxl-1.0.safetensors"
    return PoseControlConfig(
        enabled=enabled,
        control_type="openpose",
        weight=max(0.0, min(1.0, _env_float("COMFYUI_CONTROLNET_WEIGHT", 0.75))),
        model_name=model,
    )


def pose_control_requested(cfg: PoseControlConfig | None = None) -> bool:
    return (cfg or load_pose_control_config()).enabled


def _comfy_models_dir() -> Path | None:
    raw = (os.getenv("COMFYUI_DIR") or "").strip()
    if raw:
        p = Path(raw) / "models"
        if p.is_dir():
            return p
    sibling = Path(__file__).resolve().parents[2].parent / "ComfyUI" / "models"
    return sibling if sibling.is_dir() else None


def controlnet_model_on_disk(cfg: PoseControlConfig | None = None) -> bool:
    c = cfg or load_pose_control_config()
    models = _comfy_models_dir()
    if models is None:
        return False
    cn = models / "controlnet"
    if not cn.is_dir():
        return False
    name = c.model_name.lower()
    for f in cn.iterdir():
        if not f.is_file():
            continue
        if name in f.name.lower() or "openpose" in f.name.lower():
            return True
    return False


def pose_control_runtime_ready(client: ComfyUIClient | None) -> bool:
    cfg = load_pose_control_config()
    if not cfg.enabled:
        return False
    if client is None:
        return False
    from services.comfyui_workflow_patcher import pick_controlnet_apply_class

    if pick_controlnet_apply_class(client) is None:
        return False
    return controlnet_model_on_disk(cfg)


def resolve_stick_pose_key(pose_type: str) -> str:
    key = (pose_type or "standing").strip().lower()
    if key in _STICK_POSES:
        return key
    if key in _POSE_ALIASES:
        return _POSE_ALIASES[key]
    for hint, mapped in _POSE_ALIASES.items():
        if hint in key:
            return mapped
    return "standing"


def render_stick_pose_image(pose_type: str, size: int = 512):
    from PIL import Image, ImageDraw

    key = resolve_stick_pose_key(pose_type)
    lines = _STICK_POSES.get(key) or _STICK_POSES["standing"]
    img = Image.new("RGB", (size, size), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    w, h = size, size
    for x0, y0, x1, y1 in lines:
        draw.line(
            (x0 * w, y0 * h, x1 * w, y1 * h),
            fill=(0, 0, 0),
            width=max(3, size // 64),
        )
    r = max(4, size // 32)
    hx, hy = lines[0][0] * w, lines[0][1] * h
    draw.ellipse((hx - r, hy - r, hx + r, hy + r), fill=(0, 0, 0))
    return img


def control_dir_for_package(package_dir: Path) -> Path:
    return Path(package_dir) / "control"


def pose_map_path(package_dir: Path, cut_id: str) -> Path:
    cid = str(cut_id).zfill(2)
    return control_dir_for_package(package_dir) / f"pose_{cid}.png"


def ensure_pose_map(
    package_dir: Path,
    cut_id: str,
    pose_type: str,
    *,
    size: int = 512,
) -> Path:
    """Write stick pose placeholder for future ControlNet OpenPose input."""
    out = pose_map_path(package_dir, cut_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    render_stick_pose_image(pose_type, size=size).save(out, format="PNG")
    return out


def package_dir_from_output_path(output_path: Path) -> Path | None:
    """``.../outputs/MySticker/...`` → package root ``MySticker``."""
    p = Path(output_path).resolve()
    parts = p.parts
    if "outputs" not in parts:
        return None
    idx = parts.index("outputs")
    if idx + 1 >= len(parts):
        return None
    return Path(*parts[: idx + 2])


def log_pose_control(
    *,
    applied: bool,
    cut_id: str,
    weight: float | None = None,
    pose_path: Path | None = None,
) -> None:
    if applied:
        pp = f" pose={pose_path.name}" if pose_path else ""
        print(
            f"[POSE_CONTROL] type=openpose weight={weight:.2f} cut={cut_id}{pp}",
            file=sys.stderr,
        )
    else:
        print(
            f"[POSE_CONTROL] unavailable fallback=prompt_only cut={cut_id}",
            file=sys.stderr,
        )


def patch_workflow_for_pose_control(
    workflow: dict[str, Any],
    *,
    bindings: dict[str, Any],
    client: ComfyUIClient,
    uploaded_pose_image: str,
    weight: float | None = None,
    cut_id: str = "",
) -> tuple[dict[str, Any], bool]:
    cfg = load_pose_control_config()
    if not cfg.enabled:
        return workflow, False
    if not pose_control_runtime_ready(client):
        log_pose_control(applied=False, cut_id=cut_id)
        return workflow, False

    from services.comfyui_workflow_patcher import inject_controlnet_openpose

    w = cfg.weight if weight is None else weight
    patched, ok = inject_controlnet_openpose(
        workflow,
        bindings=bindings,
        uploaded_pose_image=uploaded_pose_image,
        controlnet_model=cfg.model_name,
        strength=w,
        client=client,
    )
    if ok:
        log_pose_control(applied=True, cut_id=cut_id, weight=w)
    else:
        log_pose_control(applied=False, cut_id=cut_id)
    return patched, ok
