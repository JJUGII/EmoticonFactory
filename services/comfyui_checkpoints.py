"""ComfyUI checkpoint discovery, workflow patching, and startup logging."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT

CHECKPOINT_EXTENSIONS = frozenset({".safetensors", ".ckpt", ".pt"})

# Prefer SDXL-style names when COMFYUI_CHECKPOINT is unset.
_PREFERRED_CHECKPOINTS = (
    "animagineXLV31.safetensors",
    "dreamshaperXL_v21TurboDPMSDE.safetensors",
    "dreamshaperXL.safetensors",
    "juggernautXL_v9RdphotoLightning.safetensors",
    "juggernautXL.safetensors",
)


class ComfyUICheckpointNotFoundError(RuntimeError):
    """No usable checkpoint in ComfyUI/models/checkpoints."""


def find_comfyui_root() -> Path | None:
    env = (os.getenv("COMFYUI_DIR") or "").strip()
    if env:
        root = Path(env).expanduser()
        if (root / "main.py").is_file():
            return root.resolve()
    candidates = [
        PROJECT_ROOT.parent / "ComfyUI",
        Path.home() / "ComfyUI",
        Path.home() / "Documents" / "ComfyUI",
        Path.home() / "Projects" / "ComfyUI",
    ]
    seen: set[str] = set()
    for c in candidates:
        key = str(c.resolve()) if c.exists() else str(c)
        if key in seen:
            continue
        seen.add(key)
        if c.is_dir() and (c / "main.py").is_file():
            return c.resolve()
    return None


def checkpoints_dir() -> Path | None:
    root = find_comfyui_root()
    if not root:
        return None
    d = root / "models" / "checkpoints"
    return d if d.is_dir() else None


def list_checkpoint_files(models_dir: Path | None = None) -> list[str]:
    """Sorted basenames of checkpoint files under ``models/checkpoints``."""
    d = models_dir or checkpoints_dir()
    if d is None or not d.is_dir():
        return []
    names: list[str] = []
    for p in d.iterdir():
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() in CHECKPOINT_EXTENSIONS:
            names.append(p.name)
    return sorted(names, key=str.lower)


def _log(msg: str) -> None:
    print(f"[COMFYUI] {msg}", file=sys.stderr)


def select_checkpoint_name(
    *,
    env_override: str | None = None,
    models_dir: Path | None = None,
) -> str:
    """Pick checkpoint: ``COMFYUI_CHECKPOINT`` env, else preferred name, else first sorted."""
    detected = list_checkpoint_files(models_dir)
    override = (env_override if env_override is not None else os.getenv("COMFYUI_CHECKPOINT") or "").strip()

    if override:
        if override not in detected:
            raise ComfyUICheckpointNotFoundError(
                "ComfyUI checkpoint not found.\n"
                f"COMFYUI_CHECKPOINT={override!r} is not in ComfyUI/models/checkpoints.\n"
                f"Install a model under: {_checkpoints_hint_path(models_dir)}\n"
                f"Detected checkpoints: {detected!r}"
            )
        return override

    if not detected:
        raise ComfyUICheckpointNotFoundError(
            "ComfyUI checkpoint not found.\n"
            "Install a model under:\n"
            f"  {_checkpoints_hint_path(models_dir)}\n"
            f"Detected checkpoints: {detected!r}"
        )

    lower_map = {n.lower(): n for n in detected}
    for pref in _PREFERRED_CHECKPOINTS:
        hit = lower_map.get(pref.lower())
        if hit:
            return hit

    return detected[0]


def _checkpoints_hint_path(models_dir: Path | None = None) -> str:
    d = models_dir or checkpoints_dir()
    if d:
        return str(d.resolve())
    root = find_comfyui_root()
    if root:
        return str((root / "models" / "checkpoints").resolve())
    return "ComfyUI/models/checkpoints (set COMFYUI_DIR in .env)"


def patch_workflow_checkpoint(
    workflow: dict[str, Any],
    checkpoint_name: str,
    *,
    bindings: dict[str, Any] | None = None,
) -> int:
    """Set ``ckpt_name`` on all ``CheckpointLoaderSimple`` nodes. Returns nodes patched."""
    patched = 0
    if bindings and bindings.get("checkpoint"):
        node_id = str(bindings["checkpoint"]["node"])
        field = str(bindings["checkpoint"].get("field") or "ckpt_name")
        if node_id in workflow and "inputs" in workflow[node_id]:
            workflow[node_id]["inputs"][field] = checkpoint_name
            patched += 1
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "CheckpointLoaderSimple":
            inputs = node.setdefault("inputs", {})
            if inputs.get("ckpt_name") != checkpoint_name:
                inputs["ckpt_name"] = checkpoint_name
                patched += 1
    return patched


def log_comfyui_checkpoints(*, env_override: str | None = None) -> str:
    """Log detected checkpoints and selection; returns selected basename."""
    models = checkpoints_dir()
    detected = list_checkpoint_files(models)
    hint = _checkpoints_hint_path(models)

    _log(f"checkpoints dir={hint}")
    if detected:
        _log("detected checkpoints:")
        for name in detected:
            _log(f"  - {name}")
    else:
        _log("detected checkpoints: (none)")

    selected = select_checkpoint_name(env_override=env_override, models_dir=models)
    _log(f"selected checkpoint={selected}")
    return selected


def ensure_checkpoint_available(*, env_override: str | None = None) -> str:
    """Validate at least one checkpoint exists; return selected name."""
    return select_checkpoint_name(env_override=env_override)
