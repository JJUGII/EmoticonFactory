"""Build single-execution ComfyUI workflows for multiple emoticon cuts."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from services.prompts.comfyui_style_presets import ComfyUISamplerParams, load_comfyui_style_preset


@dataclass(frozen=True)
class WorkflowCutInput:
    cut_id: str
    positive: str
    negative: str
    text: str = ""
    denoise: float | None = None


def patch_workflow_batch_size(workflow: dict[str, Any], batch_size: int) -> int:
    """
    Set ``batch_size`` / ``amount`` on known batch-capable nodes.

    Returns number of nodes patched.
    """
    n = max(1, int(batch_size))
    patched = 0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        cls = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if cls == "EmptyLatentImage" and "batch_size" in inputs:
            inputs["batch_size"] = n
            patched += 1
        elif cls in ("RepeatImageBatch", "RepeatLatentBatch") and "amount" in inputs:
            inputs["amount"] = n
            patched += 1
        elif cls == "KSampler" and "batch_size" in inputs:
            inputs["batch_size"] = n
            patched += 1
    return patched


def _compose_positive(cut: WorkflowCutInput) -> str:
    parts = [cut.positive.strip()]
    if cut.text.strip():
        parts.append(
            f"Sticker text context (overlay later, do not draw text): {cut.text.strip()}"
        )
    parts.append(f"Cut id: {cut.cut_id}.")
    return "\n".join(p for p in parts if p)


def build_multi_cut_img2img_workflow(
    template: dict[str, Any],
    bindings: dict[str, Any],
    *,
    cuts: list[WorkflowCutInput],
    uploaded_image: str,
    checkpoint: str,
    seeds: list[int] | None = None,
    sampler: ComfyUISamplerParams | None = None,
) -> dict[str, Any]:
    """
    One ComfyUI prompt graph: shared checkpoint + reference encode, per-cut sampler arms.

    Each arm runs img2img from the same latent with different conditioning — one graph
    execution (model loaded once), which is efficient on MPS vs multiple queue_prompt calls.
    """
    if not cuts:
        raise ValueError("cuts must not be empty")
    if len(cuts) > 8:
        raise ValueError("workflow batch supports at most 8 cuts per execution")

    t3 = template.get("3") or {}
    t4 = template.get("4") or {}
    inp3 = dict((t3.get("inputs") or {}))
    sp = sampler or load_comfyui_style_preset().sampler
    steps = int(sp.steps)
    cfg = float(sp.cfg)
    default_denoise = float(sp.denoise)
    sampler_name = str(sp.sampler_name)
    scheduler = str(sp.scheduler)

    neg_default = "text, watermark, logo, blurry, photorealistic, different character"
    if bindings.get("negative_prompt"):
        neg_node = str(bindings["negative_prompt"]["node"])
        neg_field = str(bindings["negative_prompt"]["field"])
        neg_default = str((template.get(neg_node) or {}).get("inputs", {}).get(neg_field) or neg_default)

    workflow: dict[str, Any] = {
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "11": {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_image},
        },
        "12": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["11", 0], "vae": ["4", 2]},
        },
    }

    save_node_ids: list[str] = []
    for i, cut in enumerate(cuts):
        sid = str(100 + i)
        pid = str(200 + i)
        nid = str(300 + i)
        kid = str(400 + i)
        did = str(500 + i)
        save_node_ids.append(sid)

        workflow[pid] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": _compose_positive(cut)},
        }
        neg_text = (cut.negative or "").strip() or neg_default
        workflow[nid] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": neg_text},
        }
        seed = (
            int(seeds[i])
            if seeds and i < len(seeds)
            else int(inp3.get("seed") or 0)
        )
        cut_denoise = float(cut.denoise) if cut.denoise is not None else default_denoise
        workflow[kid] = {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": cut_denoise,
                "model": ["4", 0],
                "positive": [pid, 0],
                "negative": [nid, 0],
                "latent_image": ["12", 0],
            },
        }
        workflow[did] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": [kid, 0], "vae": ["4", 2]},
        }
        workflow[sid] = {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": f"kakao_emoticon_{cut.cut_id}",
                "images": [did, 0],
            },
        }

    workflow["_kakao_save_nodes"] = save_node_ids  # stripped before queue
    return workflow


def strip_internal_keys(workflow: dict[str, Any]) -> dict[str, Any]:
    wf = copy.deepcopy(workflow)
    wf.pop("_kakao_save_nodes", None)
    wf.pop("_kakao_extensions", None)
    return wf


def save_node_order(workflow: dict[str, Any]) -> list[str]:
    order = workflow.get("_kakao_save_nodes")
    if isinstance(order, list):
        return [str(x) for x in order]
    return sorted(
        (k for k, v in workflow.items() if isinstance(v, dict) and v.get("class_type") == "SaveImage"),
        key=lambda x: int(x) if x.isdigit() else 9999,
    )
