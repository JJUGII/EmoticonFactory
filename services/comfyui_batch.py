"""ComfyUI emoticon cut generation: workflow batching + optional queue concurrency."""

from __future__ import annotations

import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.comfyui_image_generator import ComfyUIImageGenerator
from services.directing.body_visibility import log_body_visibility, score_body_visibility
from services.comfyui_pose_control import ensure_pose_map, package_dir_from_output_path
from services.comfyui_reference import log_comfyui_reference
from services.prompts.prompt_profiles import load_prompt_settings, resolve_source_mode
from services.comfyui_runtime import (
    log_comfyui_runtime_hints,
    resolve_workflow_batch_size,
)
from services.image_generator import OpenAIMissingKeyError


def _log(msg: str) -> None:
    """stderr + stdout so subprocess pipeline log_tail always captures batch diagnostics."""
    line = f"[COMFYUI] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except OSError:
        pass


def log_comfyui_emoticon_entry(
    gen_settings: Any,
    *,
    cut_count: int,
    emoticon_backend: str,
) -> None:
    """Called from app.py immediately before ``run_comfyui_emoticon_cuts``."""
    wf_n, src = resolve_workflow_batch_size(gen_settings.comfyui_batch_size)
    _log(
        "emoticon entry "
        f"backend={emoticon_backend} cuts={cut_count} "
        f"batch_sources env={src['env_raw']} env_n={src['from_env']} "
        f"settings_n={src['from_settings']} param_n={src['param']} resolved_n={wf_n}"
    )


def load_comfyui_batch_concurrency() -> int:
    """``COMFYUI_BATCH_CONCURRENCY`` — parallel queue_prompt workers (default 1)."""
    import os

    raw = (os.getenv("COMFYUI_BATCH_CONCURRENCY") or "1").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 1
    n = max(1, min(n, 16))
    if n >= 5:
        _log(
            "WARNING: COMFYUI_BATCH_CONCURRENCY>=5 — RAM/VRAM 부족으로 실패할 수 있습니다. "
            "Mac mini 권장: CONCURRENCY=1, BATCH_SIZE=2."
        )
    elif n > 3:
        _log(
            "WARNING: COMFYUI_BATCH_CONCURRENCY>3 — VRAM 부족 시 컷 실패가 늘 수 있습니다."
        )
    return n


@dataclass
class _CutWork:
    item: dict[str, Any]
    prompt: str
    negative: str
    cut_id: str
    text: str
    raw_png: Path
    denoise: float | None = None
    identity_weight: float | None = None
    prompt_meta: dict[str, Any] | None = None
    body_visibility_rerender: bool = False


@dataclass
class _CutOutcome:
    cut_id: str
    success: bool
    package_row: dict[str, Any] | None
    meta_path: Path | None
    cut_log: dict[str, Any]
    exc: BaseException | None


def _finalize_cut_files(
    work: _CutWork,
    *,
    processor: Any,
    no_ai_text: bool,
    emoticon_subdir: str,
    png_no_text_dir: Path,
    sticker_dir: Path,
) -> dict[str, Any]:
    if no_ai_text:
        nt = png_no_text_dir / f"{work.cut_id}.png"
        processor.normalize_emoticon_to(work.raw_png, nt)
        out_final = sticker_dir / f"{work.cut_id}.png"
        tpos = str(work.item.get("text_position", "bottom"))
        processor.add_text_overlay(nt, out_final, work.text, tpos)
    else:
        processor.normalize_emoticon(work.raw_png)
    return {
        **{k: v for k, v in work.item.items() if not str(k).startswith("_")},
        "png": f"{emoticon_subdir}/{work.cut_id}.png",
        "icon": f"icon/{work.cut_id}.png",
        "prompt": work.prompt,
    }


def _run_comfy_generate(
    work: _CutWork,
    *,
    generator: ComfyUIImageGenerator,
    generation_reference_path: Path,
    no_ai_text: bool,
    log_workflow: bool,
    denoise: float | None = None,
) -> None:
    pkg = package_dir_from_output_path(work.raw_png)
    meta = work.prompt_meta or {}
    pose_type = str(meta.get("pose_type") or "standing")
    item_run = {
        **work.item,
        "_no_ai_text": no_ai_text,
        "_sampler_denoise": denoise if denoise is not None else work.denoise,
        "_identity_weight": work.identity_weight,
        "pose_type": pose_type,
    }
    if pkg is not None:
        item_run["_package_dir"] = str(pkg)
        ensure_pose_map(pkg, work.cut_id, pose_type)
    generator.generate(
        work.prompt,
        work.raw_png,
        text=work.text,
        item_id=work.cut_id,
        reference_path=generation_reference_path,
        item=item_run,
        log_workflow=log_workflow,
        negative_prompt=work.negative or None,
        denoise_override=denoise if denoise is not None else work.denoise,
        identity_weight=work.identity_weight,
    )


def _maybe_rerender_low_body_visibility(
    work: _CutWork,
    *,
    generator: ComfyUIImageGenerator,
    processor: Any,
    generation_reference_path: Path,
    no_ai_text: bool,
    png_no_text_dir: Path,
    log_workflow: bool,
) -> tuple[float | None, bool]:
    """Return (body visibility score, did_rerender)."""
    check = png_no_text_dir / f"{work.cut_id}.png" if no_ai_text else work.raw_png
    if no_ai_text and not check.is_file():
        processor.normalize_emoticon_to(work.raw_png, check)
    if not check.is_file():
        check = work.raw_png
    vis = score_body_visibility(check)
    log_body_visibility(work.cut_id, vis)
    rerendered = False
    if vis.rerender:
        rerendered = True
        base = work.denoise if work.denoise is not None else 0.32
        boosted = min(0.55, float(base) + 0.1)
        _log(f"body_visibility rerender cut={work.cut_id} denoise={boosted:.2f}")
        _run_comfy_generate(
            work,
            generator=generator,
            generation_reference_path=generation_reference_path,
            no_ai_text=no_ai_text,
            log_workflow=log_workflow,
            denoise=boosted,
        )
        if no_ai_text:
            processor.normalize_emoticon_to(work.raw_png, check)
        vis = score_body_visibility(check)
        log_body_visibility(work.cut_id, vis)
    return vis.score, rerendered


def _process_one_cut(
    work: _CutWork,
    *,
    generator: ComfyUIImageGenerator,
    processor: Any,
    generation_reference_path: Path,
    no_ai_text: bool,
    emoticon_subdir: str,
    raw_out_dir: Path,
    png_no_text_dir: Path,
    sticker_dir: Path,
    failed_dir: Path,
    log_workflow: bool,
) -> _CutOutcome:
    cut_id = work.cut_id
    gen_t0 = time.perf_counter()
    _log(f"using batch workflow=false single-cut queue_prompt cut={cut_id}")
    attempts_snapshot: list[dict] = []
    try:
        _run_comfy_generate(
            work,
            generator=generator,
            generation_reference_path=generation_reference_path,
            no_ai_text=no_ai_text,
            log_workflow=log_workflow,
        )
        attempts_snapshot = [
            dict(x) for x in getattr(generator, "last_attempt_logs", []) or []
        ]
        if no_ai_text:
            processor.normalize_emoticon_to(
                work.raw_png, png_no_text_dir / f"{cut_id}.png"
            )
        vis_score, body_rerendered = _maybe_rerender_low_body_visibility(
            work,
            generator=generator,
            processor=processor,
            generation_reference_path=generation_reference_path,
            no_ai_text=no_ai_text,
            png_no_text_dir=png_no_text_dir,
            log_workflow=False,
        )
        prow = _finalize_cut_files(
            work,
            processor=processor,
            no_ai_text=no_ai_text,
            emoticon_subdir=emoticon_subdir,
            png_no_text_dir=png_no_text_dir,
            sticker_dir=sticker_dir,
        )
        wall_s = round(time.perf_counter() - gen_t0, 4)
        _log(f"completed cut {cut_id}")
        return _CutOutcome(
            cut_id=cut_id,
            success=True,
            package_row=prow,
            meta_path=sticker_dir / f"{cut_id}.png",
            cut_log={
                "id": cut_id,
                "success": True,
                "wall_seconds": wall_s,
                "prompt": work.prompt,
                "attempt_logs": attempts_snapshot,
                "execution_mode": "queue_single",
                "body_visibility_score": vis_score,
                "body_visibility_rerender": body_rerendered,
                "sampler_denoise": work.denoise,
                "identity_weight": work.identity_weight,
            },
            exc=None,
        )
    except Exception as exc:
        return _failed_outcome(
            work,
            exc=exc,
            gen_t0=gen_t0,
            attempts_snapshot=attempts_snapshot
            or [dict(x) for x in getattr(generator, "last_attempt_logs", []) or []],
            failed_dir=failed_dir,
            execution_mode="queue_single",
        )


def _failed_outcome(
    work: _CutWork,
    *,
    exc: Exception,
    gen_t0: float,
    attempts_snapshot: list[dict],
    failed_dir: Path,
    execution_mode: str,
) -> _CutOutcome:
    cut_id = work.cut_id
    wall_s = round(time.perf_counter() - gen_t0, 4)
    tb = traceback.format_exc()
    if work.raw_png.exists():
        try:
            work.raw_png.unlink()
        except OSError:
            pass
    err_payload = {
        "id": cut_id,
        "error": repr(exc),
        "traceback": tb,
        "wall_seconds": wall_s,
        "attempt_logs": attempts_snapshot,
        "prompt_excerpt": work.prompt[:500],
        "execution_mode": execution_mode,
    }
    failed_dir.mkdir(parents=True, exist_ok=True)
    (failed_dir / f"{cut_id}_error.json").write_text(
        json.dumps(err_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"[실패] 컷 {cut_id} 이미지 생성 실패 → failed/{cut_id}_error.json\n{tb}",
        file=sys.stderr,
    )
    _log(f"failed cut {cut_id}")
    return _CutOutcome(
        cut_id=cut_id,
        success=False,
        package_row=None,
        meta_path=None,
        cut_log={
            "id": cut_id,
            "success": False,
            "wall_seconds": wall_s,
            "prompt": work.prompt,
            "error": repr(exc),
            "attempt_logs": attempts_snapshot,
            "execution_mode": execution_mode,
        },
        exc=exc,
    )


def _process_workflow_batch(
    group: list[_CutWork],
    *,
    generator: ComfyUIImageGenerator,
    processor: Any,
    generation_reference_path: Path,
    no_ai_text: bool,
    emoticon_subdir: str,
    png_no_text_dir: Path,
    sticker_dir: Path,
    failed_dir: Path,
    log_workflow: bool,
) -> list[_CutOutcome]:
    ids = ",".join(w.cut_id for w in group)
    _log(f"using batch workflow=true workflow batch_size={len(group)} executing cuts={ids}")
    gen_t0 = time.perf_counter()
    attempts_snapshot: list[dict] = []
    try:
        batch_payload = []
        for w in group:
            meta = w.prompt_meta or {}
            batch_payload.append(
                {
                    "cut_id": w.cut_id,
                    "prompt": w.prompt,
                    "negative": w.negative,
                    "text": w.text,
                    "output_path": w.raw_png,
                    "denoise": w.denoise,
                    "pose_type": str(meta.get("pose_type") or "standing"),
                }
            )
        generator.generate_batch(
            batch_payload,
            generation_reference_path,
            log_workflow=log_workflow,
        )
        attempts_snapshot = [
            dict(x) for x in getattr(generator, "last_attempt_logs", []) or []
        ]
        outcomes: list[_CutOutcome] = []
        wall_batch = round(time.perf_counter() - gen_t0, 4)
        for work in group:
            try:
                prow = _finalize_cut_files(
                    work,
                    processor=processor,
                    no_ai_text=no_ai_text,
                    emoticon_subdir=emoticon_subdir,
                    png_no_text_dir=png_no_text_dir,
                    sticker_dir=sticker_dir,
                )
                outcomes.append(
                    _CutOutcome(
                        cut_id=work.cut_id,
                        success=True,
                        package_row=prow,
                        meta_path=sticker_dir / f"{work.cut_id}.png",
                        cut_log={
                            "id": work.cut_id,
                            "success": True,
                            "wall_seconds": wall_batch,
                            "prompt": work.prompt,
                            "attempt_logs": attempts_snapshot,
                            "execution_mode": "workflow_batch",
                            "batch_cuts": ids,
                        },
                        exc=None,
                    )
                )
            except Exception as exc:
                outcomes.append(
                    _failed_outcome(
                        work,
                        exc=exc,
                        gen_t0=gen_t0,
                        attempts_snapshot=attempts_snapshot,
                        failed_dir=failed_dir,
                        execution_mode="workflow_batch_post",
                    )
                )
        _log(f"completed cuts={ids}")
        return outcomes
    except Exception as batch_exc:
        _log(f"batch fallback to single-cut: reason={batch_exc!r}")
        outcomes: list[_CutOutcome] = []
        for work in group:
            out = _process_one_cut(
                work,
                generator=generator,
                processor=processor,
                generation_reference_path=generation_reference_path,
                no_ai_text=no_ai_text,
                emoticon_subdir=emoticon_subdir,
                raw_out_dir=work.raw_png.parent,
                png_no_text_dir=png_no_text_dir,
                sticker_dir=sticker_dir,
                failed_dir=failed_dir,
                log_workflow=False,
            )
            if not out.cut_log.get("execution_mode"):
                out.cut_log["execution_mode"] = "queue_single_fallback"
            out.cut_log["batch_retry_after"] = repr(batch_exc)
            outcomes.append(out)
        return outcomes


def _chunk_works(works: list[_CutWork], batch_size: int) -> list[list[_CutWork]]:
    n = max(1, batch_size)
    return [works[i : i + n] for i in range(0, len(works), n)]


def run_comfyui_emoticon_cuts(
    cut_payloads: list[dict[str, object]],
    *,
    generator: ComfyUIImageGenerator,
    processor: Any,
    generation_reference_path: Path,
    no_ai_text: bool,
    emoticon_subdir: str,
    raw_out_dir: Path,
    png_no_text_dir: Path,
    sticker_dir: Path,
    failed_dir: Path,
    package_rows: list[dict[str, Any]],
    cuts_log_ref: list[dict[str, Any]],
    meta_paths: list[Path],
    concurrency: int | None = None,
    batch_size: int | None = None,
    continue_on_error: bool = True,
) -> tuple[BaseException | None, bool]:
    """
    Generate cuts via ComfyUI.

    * ``batch_size`` > 1: group cuts into one workflow execution (diffusion batching).
    * ``concurrency`` > 1: parallel queue workers for single-cut / fallback paths only.
    """
    src_mode = resolve_source_mode(None, settings=load_prompt_settings())
    log_comfyui_reference(generation_reference_path, source_mode=src_mode)

    queue_n = concurrency if concurrency is not None else load_comfyui_batch_concurrency()
    wf_batch_n, batch_src = resolve_workflow_batch_size(batch_size)
    use_batch_workflow = wf_batch_n > 1
    log_comfyui_runtime_hints(batch_size=wf_batch_n, queue_concurrency=queue_n)
    _log(f"using batch workflow={str(use_batch_workflow).lower()}")
    _log(f"workflow batch_size={wf_batch_n}")
    _log(
        f"batch_size sources env={batch_src['env_raw']} from_env={batch_src['from_env']} "
        f"settings={batch_src['from_settings']} param={batch_src['param']}"
    )
    _log(f"queue concurrency={queue_n}")

    works: list[_CutWork] = []
    for row in cut_payloads:
        item = dict(row)["item"]
        assert isinstance(item, dict)
        prompt = str(dict(row).get("positive") or dict(row)["prompt"])
        negative = str(dict(row).get("negative") or "")
        cut_id = str(item["id"]).zfill(2)
        meta = dict(row).get("prompt_meta") or {}
        den = meta.get("sampler_denoise")
        idw = meta.get("identity_weight")
        works.append(
            _CutWork(
                item=item,
                prompt=prompt,
                negative=negative,
                cut_id=cut_id,
                text=str(item.get("text", "")),
                raw_png=raw_out_dir / f"{cut_id}.png",
                denoise=float(den) if den is not None else None,
                identity_weight=float(idw) if idw is not None else None,
                prompt_meta=meta if isinstance(meta, dict) else None,
            )
        )
    if works:
        pkg_all = package_dir_from_output_path(works[0].raw_png)
        if pkg_all is not None:
            for w in works:
                meta = w.prompt_meta or {}
                ensure_pose_map(
                    pkg_all,
                    w.cut_id,
                    str(meta.get("pose_type") or "standing"),
                )

    total = len(works)
    n_groups = max(1, (total + wf_batch_n - 1) // wf_batch_n) if total else 0
    planned_exec = n_groups if use_batch_workflow else total
    _log(f"planned_comfyui_prompt_executions={planned_exec} (cuts={total})")

    if not use_batch_workflow and max(
        batch_src["from_env"], batch_src["from_settings"]
    ) > 1:
        _log(
            "WARNING: COMFYUI_BATCH_SIZE>1 in env but using batch workflow=false — "
            f"resolved workflow batch_size={wf_batch_n}"
        )

    gen_aborted: BaseException | None = None
    generation_stopped = False
    done_count = 0

    def _apply_outcomes(outcomes: list[_CutOutcome]) -> None:
        nonlocal done_count, gen_aborted, generation_stopped
        for out in outcomes:
            cuts_log_ref.append(out.cut_log)
            if out.success and out.package_row is not None:
                package_rows.append(out.package_row)
                if out.meta_path is not None:
                    meta_paths.append(out.meta_path)
            done_count += 1
            print(f"[PIPELINE] progress cuts={done_count}/{total}", file=sys.stderr)
            if not out.success and out.exc is not None:
                if isinstance(out.exc, OpenAIMissingKeyError):
                    gen_aborted = out.exc
                if not continue_on_error:
                    gen_aborted = gen_aborted or out.exc
                    generation_stopped = True

    groups = _chunk_works(works, wf_batch_n)

    if not use_batch_workflow:
        _log("routing=single-cut queue_prompt per cut (workflow batch_size<=1)")
        if queue_n <= 1:
            for i, work in enumerate(works):
                out = _process_one_cut(
                    work,
                    generator=generator,
                    processor=processor,
                    generation_reference_path=generation_reference_path,
                    no_ai_text=no_ai_text,
                    emoticon_subdir=emoticon_subdir,
                    raw_out_dir=raw_out_dir,
                    png_no_text_dir=png_no_text_dir,
                    sticker_dir=sticker_dir,
                    failed_dir=failed_dir,
                    log_workflow=(i == 0),
                )
                _apply_outcomes([out])
                if generation_stopped:
                    break
            return gen_aborted, generation_stopped

        with ThreadPoolExecutor(max_workers=queue_n) as pool:
            futures = [
                pool.submit(
                    _process_one_cut,
                    work,
                    generator=generator,
                    processor=processor,
                    generation_reference_path=generation_reference_path,
                    no_ai_text=no_ai_text,
                    emoticon_subdir=emoticon_subdir,
                    raw_out_dir=raw_out_dir,
                    png_no_text_dir=png_no_text_dir,
                    sticker_dir=sticker_dir,
                    failed_dir=failed_dir,
                    log_workflow=(idx == 0),
                )
                for idx, work in enumerate(works)
            ]
            for fut in as_completed(futures):
                if generation_stopped:
                    continue
                try:
                    out = fut.result()
                except Exception as exc:
                    out = _CutOutcome(
                        cut_id="??",
                        success=False,
                        package_row=None,
                        meta_path=None,
                        cut_log={"success": False, "error": repr(exc)},
                        exc=exc,
                    )
                _apply_outcomes([out])
        return gen_aborted, generation_stopped

    _log(f"routing=workflow batch groups={len(groups)} batch_size={wf_batch_n}")
    for gi, group in enumerate(groups):
        _log(f"batch group {gi + 1}/{len(groups)} size={len(group)}")

    # workflow batching: process groups serially (one diffusion graph per group)
    if queue_n > 1:
        _log(
            "NOTE: queue concurrency ignored while workflow batch_size>1 "
            "(serial batch groups; set COMFYUI_BATCH_CONCURRENCY=1)"
        )

    for gi, group in enumerate(groups):
        outs = _process_workflow_batch(
            group,
            generator=generator,
            processor=processor,
            generation_reference_path=generation_reference_path,
            no_ai_text=no_ai_text,
            emoticon_subdir=emoticon_subdir,
            png_no_text_dir=png_no_text_dir,
            sticker_dir=sticker_dir,
            failed_dir=failed_dir,
            log_workflow=(gi == 0),
        )
        _apply_outcomes(outs)
        if generation_stopped:
            break

    return gen_aborted, generation_stopped
