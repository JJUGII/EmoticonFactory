"""ComfyUI-backed emoticon cut generator (canonical reference img2img)."""

from __future__ import annotations

import copy
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.comfyui_checkpoints import (
    ComfyUICheckpointNotFoundError,
    select_checkpoint_name,
    patch_workflow_checkpoint,
)
from services.comfyui_workflow_batch import (
    WorkflowCutInput,
    build_multi_cut_img2img_workflow,
    save_node_order,
    strip_internal_keys,
)
from services.comfyui_identity_adapter import (
    load_identity_adapter_config,
    log_identity_strategy,
    patch_workflow_for_identity,
)
from services.comfyui_pose_control import (
    ensure_pose_map,
    package_dir_from_output_path,
    patch_workflow_for_pose_control,
    pose_control_requested,
)
from services.comfyui_workflow_resolve import resolve_comfyui_workflow_path
from services.comfyui_reference import log_comfyui_reference
from services.directing.adaptive_sampler import sampler_params_with_denoise
from services.prompts.comfyui_style_presets import (
    ComfyUIStylePreset,
    apply_sampler_preset,
    load_comfyui_style_preset,
    log_comfyui_style_preset,
)
from services.prompts.prompt_profiles import load_prompt_settings, resolve_source_mode
from services.comfyui_client import ComfyUIClient, ComfyUIError
from services.generator_config import load_generator_settings
from services.image_generator import BaseImageGenerator
from services.image_io import pil_open_image, pil_save_image


def _load_workflow_doc(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "prompt" in raw and isinstance(raw["prompt"], dict):
        return raw["prompt"], dict(raw.get("_kakao_bindings") or {})
    return raw, {}


def _set_binding(workflow: dict[str, Any], binding: dict[str, str], value: Any) -> None:
    node_id = str(binding["node"])
    field = str(binding["field"])
    workflow[node_id]["inputs"][field] = value


class ComfyUIImageGenerator(BaseImageGenerator):
    """Run ComfyUI workflow per cut; requires reference_path (canonical character)."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        workflow_path: Path | str | None = None,
        checkpoint_override: str | None = None,
    ) -> None:
        settings = load_generator_settings()
        self.base_url = (base_url or settings.comfyui_url).rstrip("/")
        self.client = ComfyUIClient(self.base_url)
        if workflow_path is not None:
            self.workflow_path = Path(workflow_path).resolve()
            self._workflow_mode = "custom"
        else:
            self.workflow_path, self._workflow_mode = resolve_comfyui_workflow_path(
                settings.factory_root,
                client=self.client,
            )
        self.checkpoint_override = (checkpoint_override or os.getenv("COMFYUI_CHECKPOINT") or "").strip()
        self.last_attempt_logs: list[dict[str, Any]] = []
        self._generate_lock = threading.Lock()
        self._upload_lock = threading.Lock()
        self._cached_ref_upload: str | None = None
        self._workflow_template, self._bindings = _load_workflow_doc(self.workflow_path)
        try:
            self._selected_checkpoint = select_checkpoint_name(
                env_override=self.checkpoint_override or None
            )
        except ComfyUICheckpointNotFoundError as exc:
            raise ComfyUIError(str(exc)) from exc
        prompt_settings = load_prompt_settings()
        self._source_mode = resolve_source_mode(None, settings=prompt_settings)
        self._style_preset = load_comfyui_style_preset(source_mode=self._source_mode)
        self._identity_adapter = load_identity_adapter_config()
        log_comfyui_style_preset(self._style_preset, source_mode=self._source_mode)
        log_identity_strategy(source_mode=self._source_mode, config=self._identity_adapter)

    def _log(self, msg: str) -> None:
        print(f"[COMFYUI] {msg}", file=sys.stderr)

    def _upload_reference(self, reference_path: Path) -> str:
        with self._upload_lock:
            if self._cached_ref_upload:
                return self._cached_ref_upload
            name = self.client.upload_image(reference_path)
            self._cached_ref_upload = name
            return name

    def generate(
        self,
        prompt: str,
        output_path: Path,
        text: str,
        item_id: str,
        reference_path: Path | None = None,
        item: dict | None = None,
        *,
        log_workflow: bool = True,
        negative_prompt: str | None = None,
        denoise_override: float | None = None,
        identity_weight: float | None = None,
    ) -> Path:
        item = item or {}
        st = time.perf_counter()
        with self._generate_lock:
            self.last_attempt_logs = []
        if reference_path is None or not reference_path.is_file():
            raise ComfyUIError(
                "ComfyUI 16컷 생성에는 canonical/reference 이미지가 필요합니다 "
                f"(reference_path={reference_path})."
            )
        if not self.client.health_ok():
            raise ComfyUIError(
                f"ComfyUI 서버에 연결할 수 없습니다: {self.base_url} "
                "(서버 실행 및 COMFYUI_URL 확인)"
            )

        log_comfyui_reference(reference_path, source_mode=self._source_mode)

        if log_workflow:
            self._log(
                f"single-cut queue_prompt cut={item_id} workflow={self.workflow_path.name} "
                f"mode={self._workflow_mode}"
            )
        workflow = copy.deepcopy(self._workflow_template)
        bindings = self._bindings

        pose_type = str(item.get("pose_type") or item.get("_pose_type") or "standing")
        pkg_dir = item.get("_package_dir")
        if pkg_dir:
            package_dir = Path(str(pkg_dir))
        else:
            package_dir = package_dir_from_output_path(output_path)
        if package_dir is not None:
            ensure_pose_map(package_dir, item_id, pose_type)

        uploaded = self._upload_reference(reference_path)
        uploaded_pose = ""
        if package_dir is not None and pose_control_requested():
            pmap = package_dir / "control" / f"pose_{str(item_id).zfill(2)}.png"
            if pmap.is_file():
                uploaded_pose = self.client.upload_image(pmap)
        if bindings.get("load_image"):
            _set_binding(workflow, bindings["load_image"], uploaded)
        if bindings.get("positive_prompt"):
            composed = prompt.strip()
            if text.strip():
                composed += f"\nSticker text context (overlay later, do not draw text): {text.strip()}"
            composed += f"\nCut id: {item_id}."
            _set_binding(workflow, bindings["positive_prompt"], composed)
        if bindings.get("negative_prompt"):
            neg_in = (negative_prompt or "").strip()
            if neg_in:
                _set_binding(workflow, bindings["negative_prompt"], neg_in)
            else:
                neg = workflow[str(bindings["negative_prompt"]["node"])]["inputs"].get(
                    str(bindings["negative_prompt"]["field"])
                )
                if not str(neg or "").strip():
                    _set_binding(
                        workflow,
                        bindings["negative_prompt"],
                        "text, watermark, logo, blurry, photorealistic",
                    )
        if bindings.get("seed"):
            _set_binding(workflow, bindings["seed"], self.client.random_seed())
        ckpt = self._selected_checkpoint
        n_patched = patch_workflow_checkpoint(workflow, ckpt, bindings=bindings)
        if log_workflow:
            self._log(f"workflow patched checkpoint={ckpt} (nodes={n_patched})")
        denoise = denoise_override
        if denoise is None and item.get("_sampler_denoise") is not None:
            denoise = float(item["_sampler_denoise"])
        id_w = identity_weight
        if id_w is None and item.get("_identity_weight") is not None:
            id_w = float(item["_identity_weight"])
        sampler = self._style_preset.sampler
        if denoise is not None:
            sampler = sampler_params_with_denoise(sampler, float(denoise))
        run_preset = ComfyUIStylePreset(
            name=self._style_preset.name,
            positive_core=self._style_preset.positive_core,
            negative_core=self._style_preset.negative_core,
            sampler=sampler,
            positive_suffix=self._style_preset.positive_suffix,
            negative_suffix=self._style_preset.negative_suffix,
        )
        n_sampler = apply_sampler_preset(
            workflow,
            run_preset,
            source_mode=self._source_mode,
        )
        if log_workflow and n_sampler:
            s = run_preset.sampler
            self._log(
                f"denoise={s.denoise} cfg={s.cfg} steps={s.steps} "
                f"identity_weight={id_w if id_w is not None else self._identity_adapter.weight:.2f} "
                f"(sampler nodes={n_sampler})"
            )
        workflow = patch_workflow_for_identity(
            workflow,
            reference_image=uploaded,
            config=self._identity_adapter,
            weight_override=id_w,
            bindings=bindings,
            client=self.client,
            cut_id=item_id,
        )
        if uploaded_pose:
            workflow, _ = patch_workflow_for_pose_control(
                workflow,
                bindings=bindings,
                client=self.client,
                uploaded_pose_image=uploaded_pose,
                cut_id=item_id,
            )

        try:
            prompt_id = self.client.queue_prompt(workflow)
            hist = self.client.wait_history(prompt_id)
            meta = self.client.first_output_image(hist)
            tmp = output_path.with_suffix(".comfyui.png")
            self.client.download_image(meta, tmp)
            img = pil_open_image(tmp).convert("RGBA")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pil_save_image(img, output_path, format="PNG")
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        except ComfyUIError:
            raise
        except Exception as exc:
            raise ComfyUIError(f"ComfyUI 생성 실패 (cut {item_id}): {exc}") from exc

        wall = round(time.perf_counter() - st, 4)
        with self._generate_lock:
            self.last_attempt_logs = [
            {
                "attempt": 1,
                "phase": "comfyui_workflow",
                "success": True,
                "latency_ms": round(wall * 1000, 2),
                "wall_seconds": wall,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "comfyui_url": self.base_url,
                "workflow": str(self.workflow_path),
                "usage": None,
                "error": None,
            }
            ]
        return output_path

    def generate_batch(
        self,
        cuts: list[dict[str, Any]],
        reference_path: Path,
        *,
        log_workflow: bool = True,
    ) -> list[tuple[str, Path]]:
        """
        Run one workflow execution for multiple cuts (shared model load).

        Each entry: ``cut_id``, ``prompt``, ``negative``, ``text``, ``output_path``.
        """
        if not cuts:
            return []
        if reference_path is None or not reference_path.is_file():
            raise ComfyUIError(
                "ComfyUI batch 생성에는 canonical/reference 이미지가 필요합니다 "
                f"(reference_path={reference_path})."
            )
        if not self.client.health_ok():
            raise ComfyUIError(
                f"ComfyUI 서버에 연결할 수 없습니다: {self.base_url} "
                "(서버 실행 및 COMFYUI_URL 확인)"
            )

        log_comfyui_reference(reference_path, source_mode=self._source_mode)

        st = time.perf_counter()
        with self._generate_lock:
            self.last_attempt_logs = []

        wf_cuts = []
        for c in cuts:
            den = c.get("denoise")
            if den is None:
                den = c.get("sampler_denoise")
            wf_cuts.append(
                WorkflowCutInput(
                    cut_id=str(c["cut_id"]).zfill(2),
                    positive=str(c.get("prompt") or ""),
                    negative=str(c.get("negative") or ""),
                    text=str(c.get("text") or ""),
                    denoise=float(den) if den is not None else None,
                )
            )
        seeds = [self.client.random_seed() for _ in wf_cuts]
        uploaded = self._upload_reference(reference_path)
        ckpt = self._selected_checkpoint
        package_dir = package_dir_from_output_path(Path(cuts[0]["output_path"]))
        if package_dir is not None:
            for c in cuts:
                pose_type = str(c.get("pose_type") or "standing")
                ensure_pose_map(package_dir, str(c["cut_id"]), pose_type)

        workflow = build_multi_cut_img2img_workflow(
            self._workflow_template,
            self._bindings,
            cuts=wf_cuts,
            uploaded_image=uploaded,
            checkpoint=ckpt,
            seeds=seeds,
            sampler=self._style_preset.sampler,
        )
        workflow = patch_workflow_for_identity(
            workflow,
            reference_image=uploaded,
            config=self._identity_adapter,
            bindings=self._bindings,
            client=self.client,
        )
        if (
            package_dir is not None
            and pose_control_requested()
            and len(cuts) == 1
        ):
            pmap = package_dir / "control" / f"pose_{str(cuts[0]['cut_id']).zfill(2)}.png"
            if pmap.is_file():
                up_pose = self.client.upload_image(pmap)
                workflow, _ = patch_workflow_for_pose_control(
                    workflow,
                    bindings=self._bindings,
                    client=self.client,
                    uploaded_pose_image=up_pose,
                    cut_id=str(cuts[0]["cut_id"]),
                )
        elif pose_control_requested() and len(cuts) > 1:
            print(
                "[POSE_CONTROL] unavailable fallback=prompt_only reason=batch_multi_cut",
                file=sys.stderr,
            )

        order = save_node_order(workflow)
        prompt_wf = strip_internal_keys(workflow)

        cut_ids = ",".join(x.cut_id for x in wf_cuts)
        self._log(
            f"using batch workflow=true workflow batch_size={len(wf_cuts)} "
            f"executing cuts={cut_ids}"
        )
        if log_workflow:
            self._log(
                f"workflow={self.workflow_path.name} mode={self._workflow_mode} "
                f"multi_cut_arms={len(wf_cuts)}"
            )

        prompt_id = self.client.queue_prompt(prompt_wf)
        hist = self.client.wait_history(prompt_id)
        metas = self.client.output_images(hist, save_node_order=order)
        if len(metas) < len(cuts):
            raise ComfyUIError(
                f"ComfyUI batch 출력 부족: expected {len(cuts)} images, got {len(metas)}"
            )

        results: list[tuple[str, Path]] = []
        for i, c in enumerate(cuts):
            cut_id = str(c["cut_id"]).zfill(2)
            out_path = Path(c["output_path"])
            meta = metas[i]
            tmp = out_path.with_suffix(".comfyui.png")
            self.client.download_image(meta, tmp)
            img = pil_open_image(tmp).convert("RGBA")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            pil_save_image(img, out_path, format="PNG")
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            results.append((cut_id, out_path))

        wall = round(time.perf_counter() - st, 4)
        with self._generate_lock:
            self.last_attempt_logs = [
                {
                    "attempt": 1,
                    "phase": "comfyui_workflow_batch",
                    "success": True,
                    "latency_ms": round(wall * 1000, 2),
                    "wall_seconds": wall,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "comfyui_url": self.base_url,
                    "workflow": str(self.workflow_path),
                    "batch_cuts": [x.cut_id for x in wf_cuts],
                    "usage": None,
                    "error": None,
                }
            ]
        return results
