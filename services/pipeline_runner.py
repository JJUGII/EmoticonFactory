"""Run ``app.py`` pipeline steps from Python (GUI) with streamed logs.

Initial implementation shells out to ``app.py`` for stability. A future refactor may
import ``app.main`` directly — see TODO in ``run_emoticon_pipeline``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from config import PROJECT_ROOT

_APP = PROJECT_ROOT / "app.py"


def _safe_folder_name(series_name: str) -> str:
    s = series_name.strip().replace(" ", "_")
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    s = s.strip("._") or "package"
    return s[:200]


def _emit(line: str, sink: Callable[[str], None] | None) -> None:
    if sink:
        sink(line.rstrip("\n"))


def _run_app(
    argv: list[str],
    *,
    cwd: Path,
    log: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    env = os.environ.copy()
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    buf: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        buf.append(line)
        _emit(line, log)
    proc.wait()
    return proc.returncode, "".join(buf)


@dataclass
class PipelineOptions:
    """Options mirrored from CLI (subset used by GUI)."""

    character_path: str
    series_name: str
    theme: str
    species_hint: str = ""
    personality_hint: str = ""
    reference_type: str = "auto"
    stylizer: str = "none"
    generator: str = "mock"
    test_ids: str = ""
    test_one: bool = False
    full_pipeline: bool = False
    make_preview: bool = False
    overwrite: bool = False
    full_reset: bool = False
    reset_candidates: bool = False
    reset_canonical: bool = False
    reset_only: bool = False
    output_root: str | None = None
    no_ai_text: bool = True
    make_webp: bool = False
    canonical_character: str | None = None
    make_candidates: bool = False
    candidate_count: int = 3
    select_candidate: int | None = None
    use_character_sheet: bool = False
    make_character_sheet: bool = False
    sheet_generator: str = "mock"
    sheet_openai_model: str = "gpt-image-1"
    sheet_openai_mode: str = "auto"
    character_sheet: str | None = None
    style_intensity: float = 0.5
    pose_variation_strength: float = 1.0
    expression_strength: float = 1.0
    require_character_sheet: bool = False
    auto_regenerate: bool = False
    cut_templates: str | None = None
    candidate_openai_model: str = "gpt-image-1"
    candidate_openai_mode: str = "auto"
    grid_mode: bool = False
    art_style: str = "illustration"  # "illustration" | "realistic"
    no_text_overlay: bool = False  # True → 최종 PNG에 텍스트 오버레이 없음


@dataclass
class PipelineResult:
    returncode: int
    package_dir: Path | None
    stdout_tail: str = ""


@dataclass
class CandidateResult:
    returncode: int
    package_dir: Path
    stdout_tail: str = ""


class PipelineRunner:
    """Thin wrapper around ``python app.py ...``."""

    def __init__(self, *, project_root: Path | None = None) -> None:
        self.root = Path(project_root) if project_root else PROJECT_ROOT

    def _base_argv(self, options: PipelineOptions) -> list[str]:
        exe = sys.executable
        argv: list[str] = [
            exe,
            str(self.root / "app.py"),
            "--character",
            options.character_path,
            "--series",
            options.series_name,
            "--theme",
            options.theme,
            "--reference-type",
            options.reference_type,
            "--stylizer",
            options.stylizer,
            "--generator",
            options.generator,
        ]
        sh = (options.species_hint or "").strip()
        argv += ["--species-hint", sh if sh else "unknown"]
        if options.personality_hint.strip():
            argv += ["--personality-hint", options.personality_hint.strip()]
        if options.output_root:
            argv += ["--output-root", options.output_root]
        if options.overwrite:
            argv.append("--overwrite")
        if options.full_reset:
            argv.append("--full-reset")
        if options.reset_candidates:
            argv.append("--reset-candidates")
        if options.reset_canonical:
            argv.append("--reset-canonical")
        if options.reset_only:
            argv.append("--reset-only")
        if options.full_pipeline:
            argv.append("--full-pipeline")
        if options.make_preview:
            argv.append("--make-preview")
        if options.make_webp:
            argv.append("--make-webp")
        if options.test_ids.strip():
            argv += ["--test-ids", options.test_ids.strip()]
        elif options.test_one:
            argv.append("--test-one")
        if not options.no_ai_text:
            argv.append("--ai-text")
        if options.canonical_character:
            argv += ["--canonical-character", options.canonical_character]
        if options.make_candidates:
            argv.append("--make-candidates")
            argv += ["--candidate-count", str(max(1, int(options.candidate_count)))]
        if options.select_candidate is not None:
            argv += ["--select-candidate", str(int(options.select_candidate))]
        if options.use_character_sheet:
            argv.append("--use-character-sheet")
        if options.character_sheet:
            argv += ["--character-sheet", options.character_sheet]
        if options.make_character_sheet:
            argv.append("--make-character-sheet")
            argv += ["--sheet-generator", str(options.sheet_generator or "mock").strip().lower()]
            argv += ["--sheet-openai-model", str(options.sheet_openai_model or "gpt-image-1").strip()]
            argv += ["--sheet-openai-mode", str(options.sheet_openai_mode or "auto").strip().lower()]
        argv += ["--style-intensity", str(float(options.style_intensity))]
        argv += ["--pose-variation-strength", str(float(options.pose_variation_strength))]
        argv += ["--expression-strength", str(float(options.expression_strength))]
        if options.require_character_sheet:
            argv.append("--require-character-sheet")
        if options.auto_regenerate:
            argv.append("--auto-regenerate")
        if options.cut_templates:
            argv += ["--cut-templates", str(options.cut_templates)]
        if getattr(options, "candidate_openai_model", None):
            argv += [
                "--candidate-openai-model",
                str(options.candidate_openai_model).strip(),
            ]
        if getattr(options, "candidate_openai_mode", None):
            argv += [
                "--candidate-openai-mode",
                str(options.candidate_openai_mode).strip().lower(),
            ]
        if getattr(options, "grid_mode", False):
            argv.append("--grid-mode")
        if getattr(options, "no_text_overlay", False):
            argv.append("--no-text-overlay")
        art_style = str(getattr(options, "art_style", "illustration")).strip().lower()
        if art_style == "realistic":
            argv += ["--art-style", "realistic"]
        return argv

    def _package_dir(self, options: PipelineOptions) -> Path:
        folder = _safe_folder_name(options.series_name)
        if options.output_root:
            return Path(options.output_root) / folder
        return self.root / "outputs" / folder

    def generate_candidates(
        self,
        options: PipelineOptions,
        *,
        log: Callable[[str], None] | None = None,
    ) -> CandidateResult:
        opts = PipelineOptions(**{**options.__dict__, "make_candidates": True})
        rc, out = _run_app(self._base_argv(opts), cwd=self.root, log=log)
        tail = out[-8000:] if out else ""
        return CandidateResult(returncode=rc, package_dir=self._package_dir(options), stdout_tail=tail)

    def generate_character_sheet(
        self,
        options: PipelineOptions,
        *,
        log: Callable[[str], None] | None = None,
    ) -> CandidateResult:
        """Run ``--make-character-sheet`` only."""
        od = {
            **options.__dict__,
            "make_character_sheet": True,
            "make_candidates": False,
            "make_preview": False,
            "test_ids": "",
            "test_one": False,
            "full_pipeline": False,
            "select_candidate": None,
        }
        opts = PipelineOptions(**od)
        rc, out = _run_app(self._base_argv(opts), cwd=self.root, log=log)
        tail = out[-8000:] if out else ""
        return CandidateResult(returncode=rc, package_dir=self._package_dir(options), stdout_tail=tail)

    def run_emoticon_pipeline(
        self,
        options: PipelineOptions,
        *,
        canonical_character_path: str | None = None,
        log: Callable[[str], None] | None = None,
    ) -> PipelineResult:
        # TODO: import app.main(argv) directly for in-process runs (no subprocess).
        od = {**options.__dict__, "make_candidates": False}
        if canonical_character_path:
            od["canonical_character"] = canonical_character_path
        opts = PipelineOptions(**od)
        rc, out = _run_app(self._base_argv(opts), cwd=self.root, log=log)
        tail = out[-8000:] if out else ""
        return PipelineResult(returncode=rc, package_dir=self._package_dir(options), stdout_tail=tail)
