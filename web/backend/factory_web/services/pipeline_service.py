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
from services.generator_config import (  # noqa: E402
    load_generator_settings,
    resolve_candidate_generator,
    resolve_emoticon_generator,
)
from services.canonical_reuse import (  # noqa: E402
    is_reuse_character_enabled,
    log_gpt_candidate_skipped,
    log_reuse_character,
    persist_job_canonical_cache,
    resolve_canonical_path,
)
from services.pipeline_runner import PipelineOptions, PipelineRunner  # noqa: E402
from utils.files import (  # noqa: E402
    cleanup_appledouble_in_dir,
    is_junk_filename,
    is_valid_image_file,
    resolve_upload_character_path,
)


_CUT_LOG_RE = re.compile(
    r"\[OpenAI 컷 (\d{2})\]|\[COMFYUI\] completed cuts?=([\d,]+)|\[COMFYUI\] completed cut (\d{2})|"
    r"\[PIPELINE\] progress cuts=(\d+)/(\d+)|컷 id (\d{2})"
)


def _format_pipeline_error(code: int, logs: list[str]) -> str:
    tail = "".join(logs)[-2000:]
    if (
        code == 9
        or "ComfyUIError" in tail
        or "ComfyUICheckpointNotFoundError" in tail
        or "checkpoint not found" in tail
        or "invalid prompt (checkpoint)" in tail
        or "ComfyUI workflow" in tail
        or "ComfyUI 서버" in tail
    ):
        return (
            "ComfyUI 16컷 생성 실패. ComfyUI 큐·logs/comfyui.log·FastAPI [COMFYUI] 로그를 확인하세요. "
            "OPENAI_FALLBACK_FOR_EMOTICONS=false 이면 OpenAI로 전환하지 않습니다."
        )
    if code == 7 and ("OpenAIMissingKeyError" in tail or "OPENAI_API_KEY" in tail):
        return (
            "OpenAI API 키가 없습니다 (generator=openai). "
            "프로젝트 루트 .env 에 OPENAI_API_KEY 를 넣거나 GENERATOR_EMOTICON=comfyui 를 사용하세요."
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
    m = re.search(r"\[PIPELINE\] progress cuts=(\d+)/(\d+)", line)
    if m:
        done_n = int(m.group(1))
        total_n = max(1, int(m.group(2)))
        job["progress"] = min(95, int(10 + (done_n / total_n) * 85))
        job["message"] = f"이모티콘 생성 중... ({done_n}/{total_n})"
        cuts = job.get("cuts") or []
        for i, c in enumerate(cuts):
            if i < done_n:
                c["status"] = "done"
        return
    m = _CUT_LOG_RE.search(line)
    if m:
        batch_ids = m.group(2)
        if batch_ids and "[COMFYUI] completed cuts=" in line:
            for cid in batch_ids.split(","):
                cid = cid.strip().zfill(2)
                for c in job.get("cuts") or []:
                    if str(c.get("id")) == cid:
                        c["status"] = "done"
            job["current_cut"] = batch_ids.split(",")[-1].strip().zfill(2)
        else:
            cid = (m.group(1) or m.group(3) or m.group(6) or "01").zfill(2)
            job["current_cut"] = cid
            for c in job.get("cuts") or []:
                if str(c.get("id")) == cid:
                    if "completed cut" in line:
                        c["status"] = "done"
                    else:
                        c["status"] = "running"
        done = sum(1 for c in job.get("cuts") or [] if c.get("status") == "done")
        job["progress"] = min(95, int(10 + done * 5))


class PipelineService:
    def __init__(self, store: JobStore | None = None) -> None:
        self.store = store or JobStore()
        self.runner = PipelineRunner(project_root=FACTORY_ROOT)
        self._lock = threading.Lock()

    def has_canonical(self, job_id: str) -> bool:
        job = self.store.load(job_id)
        pkg_s = job.get("package_dir")
        if pkg_s:
            if resolve_canonical_path(Path(pkg_s), job_dir=self.store.job_dir(job_id)):
                return True
        # package may not be set yet; probe output folder
        try:
            pkg = _package_dir(job, self.store)
        except Exception:
            return False
        return resolve_canonical_path(pkg, job_dir=self.store.job_dir(job_id)) is not None

    def _resolve_canonical_for_job(self, job_id: str) -> Path:
        job = self.store.load(job_id)
        pkg = _package_dir(job, self.store) if job.get("package_dir") else None
        if pkg is None:
            pkg = self.store.output_root(job_id) / str(job["series_name"]).replace(" ", "_")
            if not (pkg).is_dir():
                from services.pipeline_runner import _safe_folder_name

                pkg = self.store.output_root(job_id) / _safe_folder_name(str(job["series_name"]))
        jd = self.store.job_dir(job_id)
        canon = resolve_canonical_path(pkg, job_dir=jd)
        if canon is None:
            raise FileNotFoundError("canonical_character.png not found for reuse")
        return canon

    @staticmethod
    def _pipeline_log(msg: str, sink: Callable[[str], None] | None = None) -> None:
        line = f"[PIPELINE] {msg}"
        if sink:
            sink(line)
        else:
            print(line, file=sys.stderr)

    @staticmethod
    def _generator_log(
        sink: Callable[[str], None] | None,
        *,
        candidate: str | None = None,
        emoticon: str | None = None,
    ) -> None:
        if candidate is not None:
            line = f"[GENERATOR] candidate={candidate}"
            print(line, file=sys.stderr)
            if sink:
                sink(line)
        if emoticon is not None:
            line = f"[GENERATOR] emoticon={emoticon}"
            print(line, file=sys.stderr)
            if sink:
                sink(line)

    def _resolve_upload(
        self,
        job_id: str,
        *,
        log: Callable[[str], None] | None = None,
    ) -> Path:
        up_dir = self.store.job_dir(job_id) / "uploads"
        cleanup_appledouble_in_dir(up_dir)
        picked = resolve_upload_character_path(up_dir, verify=True)
        if is_junk_filename(picked.name):
            cleanup_appledouble_in_dir(up_dir)
            picked = resolve_upload_character_path(up_dir, verify=True)
        self._pipeline_log(f"upload_dir={up_dir}", log)
        self._pipeline_log(f"character_path={picked}", log)
        self._pipeline_log(f"is_valid_image_file={is_valid_image_file(picked, verify=True)}", log)
        return picked

    def _options(
        self,
        job: dict[str, Any],
        upload: Path,
        *,
        generator: str,
        log: Callable[[str], None] | None = None,
    ) -> PipelineOptions:
        if is_junk_filename(upload.name) or not is_valid_image_file(upload, verify=False):
            raise FileNotFoundError(f"invalid character upload path: {upload}")
        return PipelineOptions(
            character_path=str(upload.resolve()),
            series_name=str(job["series_name"]),
            theme=str(job.get("theme") or "사랑"),
            species_hint=str(job.get("species_hint") or ""),
            reference_type="photo",
            stylizer="none",
            generator=str(generator),
            overwrite=True,
            make_preview=True,
            no_ai_text=True,
            output_root=str(self.store.output_root(str(job["job_id"])).resolve()),
            candidate_count=3,
            candidate_openai_model=str(job.get("candidate_openai_model") or "gpt-image-1"),
            candidate_openai_mode=str(job.get("candidate_openai_mode") or "auto"),
            source_mode=str(job.get("source_mode") or "auto"),
            output_mode=str(job.get("output_mode") or ""),
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
                if is_reuse_character_enabled():
                    jd = self.store.job_dir(job_id)
                    pkg_probe = None
                    if job.get("package_dir"):
                        pkg_probe = Path(str(job["package_dir"]))
                    elif job.get("series_name"):
                        from services.pipeline_runner import _safe_folder_name

                        pkg_probe = self.store.output_root(job_id) / _safe_folder_name(
                            str(job["series_name"])
                        )
                    canon = (
                        resolve_canonical_path(pkg_probe, job_dir=jd)
                        if pkg_probe and pkg_probe.is_dir()
                        else None
                    )
                    if canon is not None:
                        log_reuse_character(canon)
                        log_gpt_candidate_skipped(reason="reuse_character")
                        if pkg_probe:
                            persist_job_canonical_cache(pkg_probe, job_dir=jd)
                        self.store.update(
                            job_id,
                            phase="candidates_ready",
                            progress=100,
                            message="캐논 캐릭터 재사용 — GPT 후보 생성 생략",
                            reuse_character=True,
                        )
                        return
                settings = load_generator_settings()
                cand_gen = resolve_candidate_generator(generator)
                self.store.update(
                    job_id,
                    phase="candidates_running",
                    progress=5,
                    message="귀여운 캐릭터 만드는 중...",
                    error=None,
                    generator_candidate=cand_gen,
                    generator_emoticon=str(
                        job.get("generator_emoticon") or settings.emoticon
                    ),
                )
                logs: list[str] = []
                sink = self._log_sink(job_id, logs)
                self._generator_log(sink, candidate=cand_gen)
                upload = self._resolve_upload(job_id, log=sink)
                opts = self._options(job, upload, generator=cand_gen, log=sink)
                opts = PipelineOptions(**{**opts.__dict__, "make_candidates": True})
                argv = self.runner.build_argv(opts)
                self._pipeline_log(f"command={' '.join(argv)}", sink)
                res = self.runner.generate_candidates(opts, log=sink)
                pkg = res.package_dir
                self.store.update(
                    job_id,
                    phase="candidates_ready" if res.returncode == 0 else "failed",
                    progress=100 if res.returncode == 0 else 0,
                    message="후보가 준비되었습니다." if res.returncode == 0 else "후보 생성 실패",
                    package_dir=str(pkg.resolve()) if pkg else None,
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
        persist_job_canonical_cache(pkg, job_dir=self.store.job_dir(job_id))
        self.store.update(
            job_id,
            phase="canonical_selected",
            progress=100,
            message="캐논 캐릭터가 고정되었습니다.",
            selected_candidate=index,
            package_dir=str(pkg.resolve()),
        )
        return pkg

    def run_emoticons_async(
        self,
        job_id: str,
        emotions: list[str],
        *,
        reuse_character: bool = False,
    ) -> None:
        def work() -> None:
            try:
                job = self.store.load(job_id)
                reuse = reuse_character or is_reuse_character_enabled()
                if reuse:
                    canon = self._resolve_canonical_for_job(job_id)
                    log_reuse_character(canon)
                    log_gpt_candidate_skipped(reason="reuse_character")
                elif not job.get("selected_candidate"):
                    raise RuntimeError("먼저 후보를 선택하세요.")
                logs: list[str] = []
                sink = self._log_sink(job_id, logs)
                upload = self._resolve_upload(job_id, log=sink)
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
                emo_gen = resolve_emoticon_generator(
                    str(job.get("generator_emoticon") or "")
                )
                self._generator_log(sink, emoticon=emo_gen)
                self._pipeline_log(f"selected_generator={emo_gen}", sink)
                self.store.update(
                    job_id,
                    generator=emo_gen,
                    generator_emoticon=emo_gen,
                    generator_used=emo_gen,
                )
                opts = self._options(job, upload, generator=emo_gen, log=sink)
                canon_path: str | None = None
                if reuse:
                    canon_path = str(self._resolve_canonical_for_job(job_id).resolve())
                opts = PipelineOptions(
                    **{
                        **opts.__dict__,
                        "select_candidate": None,
                        "cut_templates": str(tpl.resolve()),
                        "make_candidates": False,
                        "reuse_character": reuse,
                        "canonical_character": canon_path or opts.canonical_character,
                    }
                )
                argv = self.runner.build_argv(opts)
                self._pipeline_log(f"command={' '.join(argv)}", sink)
                res = self.runner.run_emoticon_pipeline(
                    opts,
                    canonical_character_path=canon_path,
                    log=sink,
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
                    generator_used=emo_gen,
                    generator_emoticon=emo_gen,
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
