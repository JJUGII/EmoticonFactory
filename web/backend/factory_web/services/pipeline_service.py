"""Wrap KakaoEmoticonFactory ``PipelineRunner`` + canonical manager."""

from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from factory_web.config import FACTORY_ROOT
from factory_web.services.job_store import JobStore

if str(FACTORY_ROOT) not in sys.path:
    sys.path.insert(0, str(FACTORY_ROOT))

from services.base_character_prompt import CANONICAL_BASE_POLICY_KO  # noqa: E402
from services.canonical_character_manager import (  # noqa: E402
    CanonicalCharacterManager,
    SELECTED_BASE_CANDIDATE_TYPE,
)
from services.concept_planner import ConceptPlanner  # noqa: E402
from services.pipeline_runner import PipelineOptions, PipelineRunner  # noqa: E402


_CUT_LOG_RE = re.compile(r"\[OpenAI 컷 (\d{2})\]|컷 id (\d{2})")
_DETECT_SPECIES_RE = re.compile(r"\[자동감지\] species_hint 자동 설정: (\w+)")
_VALID_SPECIES = frozenset({"human", "cat", "dog", "rabbit", "hamster", "bird"})


def _parse_detected_species(logs: str) -> str:
    """파이프라인 로그에서 자동감지된 species를 추출."""
    m = _DETECT_SPECIES_RE.search(logs)
    if m:
        s = m.group(1).strip().lower()
        if s in _VALID_SPECIES:
            return s
    return ""


def _format_pipeline_error(code: int, logs: list[str]) -> str:
    tail = "".join(logs)[-2000:]
    if code == 7 or "OpenAIMissingKeyError" in tail or "OPENAI_API_KEY" in tail:
        return (
            "OpenAI API 키가 없습니다. 프로젝트 루트 .env 에 OPENAI_API_KEY 를 넣거나 "
            "UI에서 생성 엔진을 mock 으로 선택하세요. (app.py exit 7)"
        )
    return f"파이프라인 실패 (exit {code}). 로그: web/jobs/.../job.json 의 log_tail 참고"


def _package_dir(job: dict[str, Any], store: JobStore) -> Path:
    from services.pipeline_runner import _safe_folder_name

    folder = _safe_folder_name(str(job["series_name"]))
    return store.output_root(str(job["job_id"])) / folder


def build_custom_templates(job_dir: Path, emotions: list[str]) -> Path:
    base = FACTORY_ROOT / "data" / "big_emoticon_templates.json"
    rows = json.loads(base.read_text(encoding="utf-8"))
    for i, row in enumerate(rows):
        if i < len(emotions) and str(emotions[i]).strip():
            row["text"] = str(emotions[i]).strip()
    out = job_dir / "custom_templates.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def _sync_cuts_from_disk(job: dict[str, Any], pkg: Path) -> None:
    sticker = pkg / "png"
    if not sticker.is_dir():
        sticker = pkg / "png_no_text"
    cuts = job.get("cuts") or []
    for c in cuts:
        cid = str(c.get("id", "")).zfill(2)
        p = sticker / f"{cid}.png"
        if p.is_file() and c.get("status") != "done":
            c["status"] = "done"
    job["cuts"] = cuts


def _parse_log_progress(job: dict[str, Any], line: str) -> None:
    m = _CUT_LOG_RE.search(line)
    if m:
        cid = (m.group(1) or m.group(2) or "01").zfill(2)
        job["current_cut"] = cid
        for c in job.get("cuts") or []:
            if str(c.get("id")) == cid:
                c["status"] = "running"
        done = sum(1 for c in job.get("cuts") or [] if c.get("status") == "done")
        job["progress"] = min(95, int(10 + done * 5))


class PipelineService:
    def __init__(self, store: JobStore | None = None) -> None:
        self.store = store or JobStore()
        self.runner = PipelineRunner(project_root=FACTORY_ROOT)
        self._lock = threading.Lock()

    def _options(self, job: dict[str, Any], upload: Path) -> PipelineOptions:
        return PipelineOptions(
            character_path=str(upload.resolve()),
            series_name=str(job["series_name"]),
            theme=str(job.get("theme") or "사랑"),
            species_hint=str(job.get("species_hint") or ""),
            reference_type="photo",
            stylizer="none",
            generator=str(job.get("generator") or "mock"),
            overwrite=True,
            make_preview=True,
            no_ai_text=True,
            output_root=str(self.store.output_root(str(job["job_id"])).resolve()),
            candidate_count=3,
            candidate_openai_model=str(job.get("candidate_openai_model") or "gpt-image-1"),
            candidate_openai_mode=str(job.get("candidate_openai_mode") or "auto"),
            grid_mode=True,
            art_style=str(job.get("art_style") or "illustration").strip().lower(),
        )

    def _log_sink(self, job_id: str, buf: list[str]) -> Callable[[str], None]:
        def sink(line: str) -> None:
            buf.append(line + "\n")
            with self._lock:
                try:
                    job = self.store.load(job_id)
                    job["log_tail"] = "".join(buf)[-12000:]
                    _parse_log_progress(job, line)
                    self.store.save(job_id, job)
                except FileNotFoundError:
                    pass

        return sink

    def run_candidates_async(self, job_id: str, *, generator: str) -> None:
        def work() -> None:
            try:
                job = self.store.load(job_id)
                job["generator"] = generator
                self.store.update(
                    job_id,
                    phase="candidates_running",
                    progress=5,
                    message="귀여운 캐릭터 만드는 중...",
                    error=None,
                )
                upload = self._resolve_upload(job_id)
                opts = self._options(job, upload)
                opts = PipelineOptions(**{**opts.__dict__, "make_candidates": True})
                logs: list[str] = []
                res = self.runner.generate_candidates(
                    opts, log=self._log_sink(job_id, logs)
                )
                pkg = res.package_dir
                # 자동감지 결과를 로그에서 파싱해서 job에 저장
                detected_species = _parse_detected_species("".join(logs))
                update_kwargs: dict = dict(
                    phase="candidates_ready" if res.returncode == 0 else "failed",
                    progress=100 if res.returncode == 0 else 0,
                    message="후보가 준비되었습니다." if res.returncode == 0 else "후보 생성 실패",
                    package_dir=str(pkg.resolve()) if pkg else None,
                    error=None
                    if res.returncode == 0
                    else _format_pipeline_error(res.returncode, logs),
                    log_tail="".join(logs)[-12000:],
                )
                if detected_species:
                    update_kwargs["species_hint"] = detected_species
                self.store.update(job_id, **update_kwargs)
            except Exception as exc:
                self.store.update(
                    job_id,
                    phase="failed",
                    progress=0,
                    message="후보 생성 중 오류",
                    error=str(exc),
                )

        threading.Thread(target=work, daemon=True).start()

    def select_candidate(self, job_id: str, index: int) -> Path:
        job = self.store.load(job_id)
        pkg = _package_dir(job, self.store)
        cand = pkg / "character_candidates" / f"candidate_{index:02d}.png"
        if not cand.is_file():
            raise FileNotFoundError(f"candidate not found: {cand}")
        mgr = CanonicalCharacterManager()
        mgr.set_from_existing_image(
            cand,
            pkg,
            SELECTED_BASE_CANDIDATE_TYPE,
            {
                "original_reference": str(cand.resolve()),
                "candidate_index": index,
                "policy": CANONICAL_BASE_POLICY_KO,
            },
        )
        self.store.update(
            job_id,
            phase="canonical_selected",
            progress=100,
            message="캐논 캐릭터가 고정되었습니다.",
            selected_candidate=index,
            package_dir=str(pkg.resolve()),
        )
        return pkg

    def run_emoticons_async(self, job_id: str, emotions: list[str]) -> None:
        def work() -> None:
            try:
                job = self.store.load(job_id)
                if not job.get("selected_candidate"):
                    raise RuntimeError("먼저 후보를 선택하세요.")
                upload = self._resolve_upload(job_id)
                job_dir = self.store.job_dir(job_id)
                tpl = build_custom_templates(job_dir, emotions)
                job["emotions"] = list(emotions)
                cuts = [
                    {
                        "id": f"{i:02d}",
                        "text": emotions[i - 1] if i - 1 < len(emotions) else "",
                        "status": "pending",
                    }
                    for i in range(1, 17)
                ]
                self.store.update(
                    job_id,
                    phase="emoticons_running",
                    progress=8,
                    message="이모티콘 생성 중...",
                    cuts=cuts,
                    error=None,
                )
                opts = self._options(job, upload)
                opts = PipelineOptions(
                    **{
                        **opts.__dict__,
                        "select_candidate": None,
                        "cut_templates": str(tpl.resolve()),
                        "make_candidates": False,
                    }
                )
                logs: list[str] = []
                res = self.runner.run_emoticon_pipeline(
                    opts, log=self._log_sink(job_id, logs)
                )
                pkg = res.package_dir or _package_dir(job, self.store)
                job = self.store.load(job_id)
                _sync_cuts_from_disk(job, Path(pkg))
                for c in job.get("cuts") or []:
                    if c.get("status") != "done":
                        cid = str(c.get("id", "")).zfill(2)
                        if (Path(pkg) / "png" / f"{cid}.png").is_file():
                            c["status"] = "done"
                self.store.update(
                    job_id,
                    phase="completed" if res.returncode == 0 else "failed",
                    progress=100 if res.returncode == 0 else 0,
                    message="이모티콘 생성이 완료되었습니다." if res.returncode == 0 else "생성 실패",
                    package_dir=str(Path(pkg).resolve()),
                    cuts=job.get("cuts"),
                    error=None
                    if res.returncode == 0
                    else _format_pipeline_error(res.returncode, logs),
                    log_tail="".join(logs)[-12000:],
                )
            except Exception as exc:
                self.store.update(
                    job_id,
                    phase="failed",
                    progress=0,
                    message="이모티콘 생성 중 오류",
                    error=str(exc),
                )

        threading.Thread(target=work, daemon=True).start()

    def _resolve_upload(self, job_id: str) -> Path:
        job = self.store.load(job_id)
        up_dir = self.store.job_dir(job_id) / "uploads"
        # ._* 파일은 exFAT macOS AppleDouble 메타파일 — 실제 이미지 아님
        files = sorted(f for f in up_dir.glob("*.*") if not f.name.startswith("._"))
        if not files:
            raise FileNotFoundError("uploaded image missing")
        return files[0]

    def build_preview_payload(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.load(job_id)
        pkg_s = job.get("package_dir")
        if not pkg_s:
            return None
        pkg = Path(pkg_s)
        meta: dict[str, Any] = {}
        for name in (
            "package_info.json",
            "generation_log.json",
            "consistency_report.json",
            "cut_plan.json",
        ):
            p = pkg / "meta" / name
            if p.is_file():
                try:
                    meta[name.replace(".json", "")] = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
        meta["preview_html_exists"] = (pkg / "preview.html").is_file()
        return meta

    def list_cut_urls(self, job_id: str) -> list[dict[str, Any]]:
        job = self.store.load(job_id)
        pkg_s = job.get("package_dir")
        if not pkg_s:
            return job.get("cuts") or []
        pkg = Path(pkg_s)
        sticker = pkg / "png" if (pkg / "png").is_dir() else pkg / "png_no_text"
        out: list[dict[str, Any]] = []
        for i in range(1, 17):
            cid = f"{i:02d}"
            text = ""
            for c in job.get("cuts") or []:
                if str(c.get("id")) == cid:
                    text = str(c.get("text", ""))
                    break
            p = sticker / f"{cid}.png"
            out.append(
                {
                    "id": cid,
                    "text": text or (job.get("emotions") or [""] * 16)[i - 1],
                    "status": "done" if p.is_file() else "pending",
                    "path": str(p) if p.is_file() else None,
                }
            )
        return out
