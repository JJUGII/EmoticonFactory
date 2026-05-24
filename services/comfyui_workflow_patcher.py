"""Inject IPAdapter / ControlNet nodes when ComfyUI custom nodes are available."""

from __future__ import annotations

import copy
from typing import Any

from services.comfyui_client import ComfyUIClient

_OBJECT_INFO_CACHE: dict[str, Any] | None = None

_IPADAPTER_LOADER_CLASSES = (
    "IPAdapterUnifiedLoader",
    "IPAdapterModelLoader",
    "IPAdapterLoader",
)
_IPADAPTER_APPLY_CLASSES = (
    "IPAdapterAdvanced",
    "IPAdapter",
    "IPAdapterApply",
)
_CONTROLNET_LOADER_CLASSES = ("ControlNetLoader",)
_CONTROLNET_APPLY_CLASSES = (
    "ControlNetApplyAdvanced",
    "ControlNetApply",
)


def get_object_info(client: ComfyUIClient) -> dict[str, Any]:
    global _OBJECT_INFO_CACHE
    if _OBJECT_INFO_CACHE is not None:
        return _OBJECT_INFO_CACHE
    _OBJECT_INFO_CACHE = client.fetch_object_info()
    return _OBJECT_INFO_CACHE


def clear_object_info_cache() -> None:
    global _OBJECT_INFO_CACHE
    _OBJECT_INFO_CACHE = None


def _pick_class(client: ComfyUIClient, candidates: tuple[str, ...]) -> str | None:
    info = get_object_info(client)
    for name in candidates:
        if name in info:
            return name
    return None


def pick_ipadapter_loader_class(client: ComfyUIClient) -> str | None:
    return _pick_class(client, _IPADAPTER_LOADER_CLASSES)


def pick_ipadapter_apply_class(client: ComfyUIClient) -> str | None:
    return _pick_class(client, _IPADAPTER_APPLY_CLASSES)


def pick_controlnet_loader_class(client: ComfyUIClient) -> str | None:
    return _pick_class(client, _CONTROLNET_LOADER_CLASSES)


def pick_controlnet_apply_class(client: ComfyUIClient) -> str | None:
    return _pick_class(client, _CONTROLNET_APPLY_CLASSES)


def _ksampler_ids(workflow: dict[str, Any]) -> list[str]:
    return [
        k
        for k, v in workflow.items()
        if isinstance(v, dict) and str(v.get("class_type") or "") == "KSampler"
    ]


def _first_clip_encode_id(workflow: dict[str, Any]) -> str | None:
    for k, v in workflow.items():
        if isinstance(v, dict) and str(v.get("class_type") or "") == "CLIPTextEncode":
            return str(k)
    return None


def inject_ipadapter(
    workflow: dict[str, Any],
    *,
    bindings: dict[str, Any],
    client: ComfyUIClient,
    uploaded_reference: str,
    weight: float,
    checkpoint_node: str = "4",
    ref_load_node: str | None = None,
) -> tuple[dict[str, Any], bool]:
    loader_cls = pick_ipadapter_loader_class(client)
    apply_cls = pick_ipadapter_apply_class(client)
    if not loader_cls or not apply_cls:
        return workflow, False

    wf = copy.deepcopy(workflow)
    ref_node = ref_load_node
    if ref_node is None and bindings.get("load_image"):
        ref_node = str(bindings["load_image"]["node"])
    if ref_node is None:
        ref_node = "11"

    if ref_node in wf and uploaded_reference:
        wf[ref_node]["inputs"]["image"] = uploaded_reference

    loader_id, apply_id = "901", "902"
    loader_inputs: dict[str, Any] = {}
    if loader_cls == "IPAdapterUnifiedLoader":
        loader_inputs = {
            "model": [checkpoint_node, 0],
            "preset": "PLUS (high strength)",
        }
    else:
        loader_inputs = {"ipadapter_file": "ip-adapter_sdxl_vit-h.safetensors"}

    wf[loader_id] = {"class_type": loader_cls, "inputs": loader_inputs}

    apply_inputs: dict[str, Any] = {
        "model": [checkpoint_node, 0],
        "image": [ref_node, 0],
        "weight": float(weight),
    }
    if apply_cls == "IPAdapterAdvanced":
        apply_inputs.update(
            {
                "ipadapter": [loader_id, 0],
                "weight_type": "linear",
                "start_at": 0.0,
                "end_at": 1.0,
            }
        )
    elif apply_cls == "IPAdapter":
        apply_inputs["ipadapter"] = [loader_id, 0]
    else:
        apply_inputs["ipadapter"] = [loader_id, 0]

    wf[apply_id] = {"class_type": apply_cls, "inputs": apply_inputs}

    for sid in _ksampler_ids(wf):
        wf[sid]["inputs"]["model"] = [apply_id, 0]

    return wf, True


def inject_controlnet_openpose(
    workflow: dict[str, Any],
    *,
    bindings: dict[str, Any],
    uploaded_pose_image: str,
    controlnet_model: str,
    strength: float,
    client: ComfyUIClient,
    checkpoint_node: str = "4",
    positive_node: str | None = None,
) -> tuple[dict[str, Any], bool]:
    loader_cls = pick_controlnet_loader_class(client)
    apply_cls = pick_controlnet_apply_class(client)
    if not loader_cls or not apply_cls:
        return workflow, False

    wf = copy.deepcopy(workflow)
    pos_id = positive_node
    if pos_id is None and bindings.get("positive_prompt"):
        pos_id = str(bindings["positive_prompt"]["node"])
    if pos_id is None:
        pos_id = _first_clip_encode_id(wf)
    if pos_id is None:
        return workflow, False

    pose_load = "911"
    cn_load = "912"
    cn_apply = "913"

    wf[pose_load] = {
        "class_type": "LoadImage",
        "inputs": {"image": uploaded_pose_image},
    }
    wf[cn_load] = {
        "class_type": loader_cls,
        "inputs": {"control_net_name": controlnet_model},
    }

    apply_inputs: dict[str, Any] = {
        "positive": [pos_id, 0],
        "control_net": [cn_load, 0],
        "image": [pose_load, 0],
        "strength": float(strength),
    }
    if apply_cls == "ControlNetApplyAdvanced":
        apply_inputs["negative"] = ["7", 0] if "7" in wf else [pos_id, 0]
        apply_inputs["start_percent"] = 0.0
        apply_inputs["end_percent"] = 1.0
    wf[cn_apply] = {"class_type": apply_cls, "inputs": apply_inputs}

    for sid in _ksampler_ids(wf):
        wf[sid]["inputs"]["positive"] = [cn_apply, 0]

    _ = checkpoint_node
    return wf, True
