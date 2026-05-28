"""FastAPI routes."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from factory_web.config import ALLOWED_UPLOAD_EXT, DEFAULT_EMOTIONS, MAX_UPLOAD_BYTES
from factory_web.models import (
    CandidatesResponse,
    CandidateItem,
    CutProgressItem,
    EmotionsDefaultsResponse,
    GenerateCandidatesRequest,
    GenerateEmoticonsRequest,
    JobStatusResponse,
    ResultResponse,
    SelectCandidateRequest,
    UploadResponse,
)
from factory_web.services.job_store import JobStore
from factory_web.services.pipeline_service import PipelineService

router = APIRouter(prefix="/api")
store = JobStore()
pipeline = PipelineService(store)


def _job_status(doc: dict) -> JobStatusResponse:
    cuts = [
        CutProgressItem(
            id=str(c.get("id", "")).zfill(2),
            text=str(c.get("text", "")),
            status=c.get("status", "pending"),
        )
        for c in doc.get("cuts") or []
    ]
    return JobStatusResponse(
        job_id=str(doc["job_id"]),
        phase=doc.get("phase", "created"),
        progress=int(doc.get("progress") or 0),
        message=str(doc.get("message") or ""),
        current_cut=doc.get("current_cut"),
        cuts=cuts,
        error=doc.get("error"),
        log_tail=doc.get("log_tail"),
    )


@router.get("/emotions/defaults", response_model=EmotionsDefaultsResponse)
def emotions_defaults() -> EmotionsDefaultsResponse:
    return EmotionsDefaultsResponse(emotions=list(DEFAULT_EMOTIONS))


@router.post("/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile = File(...),
    series_name: str = Form(""),
    theme: str = Form("사랑"),
    generator: str = Form("mock"),
) -> UploadResponse:
    ext = Path(file.filename or "").suffix.lower()
    if not ext:
        ct = (file.content_type or "").lower()
        if "heic" in ct or "heif" in ct:
            ext = ".heic"
        elif "png" in ct:
            ext = ".png"
        elif "webp" in ct:
            ext = ".webp"
        elif "jpeg" in ct or "jpg" in ct:
            ext = ".jpg"
    if ext not in ALLOWED_UPLOAD_EXT:
        raise HTTPException(400, detail="jpg, png, webp, heic 만 지원합니다.")
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, detail="파일이 너무 큽니다 (최대 20MB).")

    doc = store.create(series_name=series_name or "MySticker", theme=theme)
    job_id = str(doc["job_id"])
    safe_name = f"photo{ext if ext else '.png'}"
    dest = store.upload_path(job_id, safe_name)
    dest.write_bytes(raw)
    store.update(
        job_id,
        phase="uploaded",
        progress=10,
        message="사진이 업로드되었습니다.",
        generator=generator.strip() or "mock",
        theme=theme,
    )
    return UploadResponse(
        job_id=job_id,
        preview_url=f"/api/files/{job_id}/uploads/{safe_name}",
        filename=safe_name,
    )


@router.post("/generate-candidates", response_model=JobStatusResponse)
def generate_candidates(body: GenerateCandidatesRequest) -> JobStatusResponse:
    try:
        store.load(body.job_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    art_style = str(body.art_style or "illustration").strip().lower()
    if art_style not in ("illustration", "realistic"):
        art_style = "illustration"
    store.update(
        body.job_id,
        generator=body.generator,
        theme=body.theme,
        species_hint=body.species_hint,
        art_style=art_style,
    )
    pipeline.run_candidates_async(body.job_id, generator=body.generator)
    return _job_status(store.load(body.job_id))


@router.post("/select-candidate")
def select_candidate(body: SelectCandidateRequest) -> dict:
    try:
        pipeline.select_candidate(body.job_id, int(body.candidate_index))
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return {"ok": True, "job": _job_status(store.load(body.job_id))}


@router.post("/generate-emoticons", response_model=JobStatusResponse)
def generate_emoticons(body: GenerateEmoticonsRequest) -> JobStatusResponse:
    if len(body.emotions) != 16:
        raise HTTPException(400, detail="감정 문구는 16개여야 합니다.")
    try:
        job = store.load(body.job_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    if not job.get("selected_candidate"):
        raise HTTPException(400, detail="먼저 후보 캐릭터를 선택하세요.")
    art_style_e = str(body.art_style or "illustration").strip().lower()
    if art_style_e not in ("illustration", "realistic"):
        art_style_e = "illustration"
    store.update(
        body.job_id,
        generator=body.generator,
        theme=body.theme,
        species_hint=body.species_hint,
        emotions=list(body.emotions),
        grid_mode=bool(body.grid_mode),
        art_style=art_style_e,
    )
    pipeline.run_emoticons_async(body.job_id, list(body.emotions))
    return _job_status(store.load(body.job_id))


@router.get("/job/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    try:
        doc = store.load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    pkg_s = doc.get("package_dir")
    if pkg_s and doc.get("phase") == "emoticons_running":
        from pathlib import Path as P

        pipeline_sync = PipelineService(store)
        _sync = pipeline_sync.list_cut_urls(job_id)
        for row in _sync:
            if row.get("status") == "done":
                for c in doc.get("cuts") or []:
                    if str(c.get("id")) == row["id"]:
                        c["status"] = "done"
        store.save(job_id, doc)
    return _job_status(store.load(job_id))


@router.get("/result/{job_id}", response_model=ResultResponse)
def get_result(job_id: str) -> ResultResponse:
    try:
        doc = store.load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    rows = pipeline.list_cut_urls(job_id)
    cuts = []
    for r in rows:
        url = None
        if r.get("path"):
            rel = Path(str(r["path"]))
            pkg = Path(str(doc.get("package_dir") or ""))
            try:
                rel_path = rel.relative_to(pkg)
                url = f"/api/files/{job_id}/package/{rel_path.as_posix()}"
            except ValueError:
                url = None
        cuts.append(
            CutProgressItem(
                id=r["id"],
                text=r.get("text", ""),
                status=r.get("status", "pending"),
                url=url,
            )
        )
    canon_url = None
    pkg_s = doc.get("package_dir")
    if pkg_s:
        canon = Path(pkg_s) / "character" / "canonical_character.png"
        if canon.is_file():
            canon_url = f"/api/files/{job_id}/package/character/canonical_character.png"
    return ResultResponse(
        job_id=job_id,
        package_dir=str(pkg_s or ""),
        preview=pipeline.build_preview_payload(job_id),
        cuts=cuts,
        canonical_url=canon_url,
    )


@router.get("/candidates/{job_id}", response_model=CandidatesResponse)
def list_candidates(job_id: str) -> CandidatesResponse:
    try:
        doc = store.load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    pkg_s = doc.get("package_dir")
    if not pkg_s:
        raise HTTPException(400, detail="후보가 아직 없습니다.")
    pkg = Path(pkg_s)
    cand_dir = pkg / "character_candidates"
    items: list[CandidateItem] = []
    for p in sorted(cand_dir.glob("candidate_*.png")):
        idx = int(p.stem.split("_")[-1])
        items.append(
            CandidateItem(
                index=idx,
                url=f"/api/files/{job_id}/package/character_candidates/{p.name}",
            )
        )
    return CandidatesResponse(job_id=job_id, candidates=items)


@router.get("/download/{job_id}")
def download_zip(job_id: str) -> StreamingResponse:
    try:
        doc = store.load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    pkg_s = doc.get("package_dir")
    if not pkg_s:
        raise HTTPException(400, detail="패키지가 없습니다.")
    pkg = Path(pkg_s)
    sticker = pkg / "png" if (pkg / "png").is_dir() else pkg / "png_no_text"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if sticker.is_dir():
            for png in sorted(sticker.glob("*.png")):
                zf.write(png, arcname=f"emoticons/{png.name}")
        canon = pkg / "character" / "canonical_character.png"
        if canon.is_file():
            zf.write(canon, arcname="canonical_character.png")
        prev = pkg / "preview.html"
        if prev.is_file():
            zf.write(prev, arcname="preview.html")
    buf.seek(0)
    name = f"emoticons_{job_id[:8]}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/files/{job_id}/{file_path:path}")
def serve_file(job_id: str, file_path: str) -> FileResponse:
    job_base = store.job_dir(job_id).resolve()
    if file_path.startswith("uploads/"):
        target = (job_base / file_path).resolve()
        target.relative_to(job_base)
    elif file_path.startswith("package/"):
        doc = store.load(job_id)
        pkg = Path(str(doc.get("package_dir") or "")).resolve()
        if not pkg.is_dir():
            raise HTTPException(404, detail="package missing")
        target = (pkg / file_path.removeprefix("package/")).resolve()
        target.relative_to(pkg)
    else:
        raise HTTPException(400, detail="invalid path")
    if not target.is_file():
        raise HTTPException(404, detail="not found")
    return FileResponse(target)
