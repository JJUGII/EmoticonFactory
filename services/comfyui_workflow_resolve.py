"""Resolve ComfyUI workflow path (base img2img vs IPAdapter+ControlNet extension)."""

from __future__ import annotations

import sys
from pathlib import Path

from services.comfyui_client import ComfyUIClient
from services.comfyui_identity_adapter import (
    identity_adapter_requested,
    ipadapter_runtime_ready,
    load_identity_adapter_config,
)
from services.comfyui_pose_control import (
    load_pose_control_config,
    pose_control_requested,
    pose_control_runtime_ready,
)

BASE_WORKFLOW = "workflows/comfyui/canonical_to_emoticon_sdxl.json"
EXT_WORKFLOW = "workflows/comfyui/canonical_to_emoticon_sdxl_ipadapter_controlnet.json"


def resolve_comfyui_workflow_path(
    factory_root: Path,
    *,
    client: ComfyUIClient | None = None,
) -> tuple[Path, str]:
    """
    Return (workflow_path, mode_tag).

    mode_tag: ``img2img`` | ``ipadapter_controlnet`` | ``ipadapter_controlnet_partial``
    """
    root = Path(factory_root).resolve()
    base = (root / BASE_WORKFLOW).resolve()
    ext = (root / EXT_WORKFLOW).resolve()

    id_cfg = load_identity_adapter_config()
    pose_cfg = load_pose_control_config()
    want_ext = identity_adapter_requested(id_cfg) or pose_control_requested(pose_cfg)

    if not want_ext or not ext.is_file():
        return base, "img2img"

    id_ready = ipadapter_runtime_ready(client) if identity_adapter_requested(id_cfg) else False
    pose_ready = pose_control_runtime_ready(client) if pose_control_requested(pose_cfg) else False

    if identity_adapter_requested(id_cfg) and not id_ready:
        print(
            "[IDENTITY_ADAPTER] unavailable fallback=img2img",
            file=sys.stderr,
        )
    if pose_control_requested(pose_cfg) and not pose_ready:
        print(
            "[POSE_CONTROL] unavailable fallback=prompt_only",
            file=sys.stderr,
        )

    if id_ready or pose_ready:
        mode = "ipadapter_controlnet" if (id_ready and pose_ready) else "ipadapter_controlnet_partial"
        print(
            f"[COMFYUI] workflow={ext.name} mode={mode}",
            file=sys.stderr,
        )
        return ext, mode

    return base, "img2img"
