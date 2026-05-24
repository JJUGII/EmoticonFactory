"""Job state persisted as ``web/jobs/<job_id>/job.json``."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factory_web.config import FACTORY_ROOT, JOBS_ROOT, OUTPUTS_SUBDIR, UPLOADS_SUBDIR


def _generator_fields_from_settings() -> tuple[str, str, str]:
    """(generator_candidate, generator_emoticon, generator default for job)."""
    import sys

    root = FACTORY_ROOT.resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from services.generator_config import load_generator_settings  # noqa: WPS433

    s = load_generator_settings(root)
    return s.candidate, s.emoticon, s.emoticon


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else JOBS_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def job_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def create(self, *, series_name: str, theme: str) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        d = self.job_dir(job_id)
        (d / UPLOADS_SUBDIR).mkdir(parents=True, exist_ok=True)
        (d / OUTPUTS_SUBDIR).mkdir(parents=True, exist_ok=True)
        cand_gen, emo_gen, default_gen = _generator_fields_from_settings()
        doc: dict[str, Any] = {
            "job_id": job_id,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "phase": "created",
            "progress": 0,
            "message": "작업이 생성되었습니다.",
            "series_name": series_name.strip() or f"Web_{job_id[:8]}",
            "theme": theme.strip() or "사랑",
            "generator": default_gen,
            "generator_candidate": cand_gen,
            "generator_emoticon": emo_gen,
            "generator_used": None,
            "species_hint": "",
            "selected_candidate": None,
            "emotions": [],
            "cuts": [{"id": f"{i:02d}", "status": "pending", "text": ""} for i in range(1, 17)],
            "error": None,
            "log_tail": "",
            "package_dir": None,
        }
        self.save(job_id, doc)
        return doc

    def load(self, job_id: str) -> dict[str, Any]:
        p = self.job_path(job_id)
        if not p.is_file():
            raise FileNotFoundError(f"job not found: {job_id}")
        return json.loads(p.read_text(encoding="utf-8"))

    def save(self, job_id: str, doc: dict[str, Any]) -> None:
        doc["updated_at"] = _utc_now()
        p = self.job_path(job_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def update(self, job_id: str, **fields: Any) -> dict[str, Any]:
        doc = self.load(job_id)
        doc.update(fields)
        self.save(job_id, doc)
        return doc

    def upload_path(self, job_id: str, filename: str) -> Path:
        return self.job_dir(job_id) / UPLOADS_SUBDIR / filename

    def output_root(self, job_id: str) -> Path:
        return self.job_dir(job_id) / OUTPUTS_SUBDIR

    def delete_job(self, job_id: str) -> None:
        d = self.job_dir(job_id)
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
