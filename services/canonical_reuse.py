"""Reuse existing canonical character — skip GPT candidate generation (Comfy tuning)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.canonical_character_manager import (
    SOURCE_JSON,
    CanonicalCharacterManager,
    CANONICAL_FILENAME,
)

_JOB_CACHE_SUBDIR = Path("package") / "character_candidates"
_CACHE_CANONICAL = "canonical_character.png"
_CACHE_SELECTED = "selected_candidate.png"


@dataclass(frozen=True)
class CanonicalFingerprint:
    canonical_hash: str
    canonical_source: str
    path: str


def paths_are_same_file(src: Path, dst: Path) -> bool:
    """True when resolved src and dst refer to the same filesystem object."""
    try:
        return Path(src).resolve() == Path(dst).resolve()
    except OSError:
        return False


def log_reuse_canonical_copy_skipped(path: Path | None = None) -> None:
    note = f" path={Path(path).resolve()}" if path is not None else ""
    print(
        f"[REUSE_CHARACTER] canonical copy skipped same_file=true{note}",
        file=sys.stderr,
    )


def safe_copy_file(
    src: Path,
    dst: Path,
    *,
    log_same_file: bool = True,
) -> bool:
    """
    Copy ``src`` → ``dst``. If both resolve to the same file, skip (no error).

    Returns True when a copy was performed, False when skipped as same file.
    """
    s, d = Path(src), Path(dst)
    if paths_are_same_file(s, d):
        if log_same_file:
            log_reuse_canonical_copy_skipped(s)
        d.parent.mkdir(parents=True, exist_ok=True)
        return False
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(s, d)
    return True


def _env_bool(name: str) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def is_comfyui_test_mode() -> bool:
    return _env_bool("COMFYUI_TEST_MODE")


def is_emoticon_reuse_character_env() -> bool:
    return _env_bool("EMOTICON_REUSE_CHARACTER")


def is_reuse_character_enabled(*, cli_reuse: bool = False) -> bool:
    return cli_reuse or is_emoticon_reuse_character_env() or is_comfyui_test_mode()


def job_dir_from_package(package_dir: Path) -> Path | None:
    """``.../jobs/<job_id>/outputs/<series>/`` → ``.../jobs/<job_id>/``."""
    p = Path(package_dir).resolve()
    if p.parent.name == "outputs":
        return p.parent.parent
    return None


def job_cache_dir(job_dir: Path) -> Path:
    return Path(job_dir) / _JOB_CACHE_SUBDIR


def resolve_canonical_path(
    package_dir: Path,
    *,
    job_dir: Path | None = None,
) -> Path | None:
    """Find canonical image: job cache → package character/ → candidates."""
    pkg = Path(package_dir)
    jd = job_dir or job_dir_from_package(pkg)
    if jd is not None:
        cache = job_cache_dir(jd)
        for name in (_CACHE_CANONICAL, _CACHE_SELECTED):
            p = cache / name
            if p.is_file():
                return p
    canon = CanonicalCharacterManager.get_canonical_path(pkg)
    if canon is not None:
        return canon
    cand_dir = pkg / "character_candidates"
    if cand_dir.is_dir():
        for name in ("selected_candidate.png", _CACHE_CANONICAL):
            p = cand_dir / name
            if p.is_file():
                return p
        hits = sorted(cand_dir.glob("candidate_*.png"))
        if len(hits) == 1:
            return hits[0]
    return None


def canonical_fingerprint(canonical_path: Path) -> CanonicalFingerprint:
    p = Path(canonical_path)
    digest = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    short = digest.hexdigest()[:16]
    rel = p.name
    try:
        parts = p.parts
        if "character" in parts:
            idx = parts.index("character")
            rel = "/".join(parts[idx:])
    except ValueError:
        pass
    return CanonicalFingerprint(
        canonical_hash=short,
        canonical_source=rel,
        path=str(p.resolve()),
    )


def read_canonical_source_meta(package_dir: Path) -> dict[str, Any]:
    meta_path = Path(package_dir) / "character" / SOURCE_JSON
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def persist_job_canonical_cache(
    package_dir: Path,
    *,
    job_dir: Path | None = None,
) -> CanonicalFingerprint | None:
    """Mirror canonical into ``web/jobs/<id>/package/character_candidates/``."""
    pkg = Path(package_dir)
    jd = job_dir or job_dir_from_package(pkg)
    canon = CanonicalCharacterManager.get_canonical_path(pkg) or resolve_canonical_path(
        pkg, job_dir=jd
    )
    if canon is None or not canon.is_file():
        return None
    fp = canonical_fingerprint(canon)
    if jd is None:
        return fp
    cache = job_cache_dir(jd)
    cache.mkdir(parents=True, exist_ok=True)
    for name in (_CACHE_CANONICAL, _CACHE_SELECTED):
        safe_copy_file(canon, cache / name, log_same_file=True)
    meta = read_canonical_source_meta(pkg)
    idx = meta.get("candidate_index")
    if idx is not None:
        src_cand = pkg / "character_candidates" / f"candidate_{int(idx):02d}.png"
        dst_cand = cache / f"candidate_{int(idx):02d}.png"
        if src_cand.is_file():
            safe_copy_file(src_cand, dst_cand, log_same_file=True)
    manifest = {
        "canonical_hash": fp.canonical_hash,
        "canonical_source": fp.canonical_source,
        "canonical_path": fp.path,
        "cached_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }
    (cache / "cache_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return fp


def log_reuse_character(canonical_path: Path, *, enabled: bool = True) -> None:
    src = canonical_path.name
    if "character" in canonical_path.parts:
        src = f"character/{CANONICAL_FILENAME}"
    print(
        f"[REUSE_CHARACTER] enabled={str(enabled).lower()} source={src}",
        file=sys.stderr,
    )
    print(
        f"[REUSE_CHARACTER] path={canonical_path.resolve()}",
        file=sys.stderr,
    )


def log_gpt_candidate_skipped(*, reason: str = "reuse_character") -> None:
    print(
        f"[GPT_CANDIDATE] skipped=true reason={reason}",
        file=sys.stderr,
    )


def prompt_meta_canonical_fields(package_dir: Path) -> dict[str, str]:
    canon = resolve_canonical_path(package_dir)
    if canon is None:
        return {}
    fp = canonical_fingerprint(canon)
    meta = read_canonical_source_meta(package_dir)
    source = str(meta.get("source_type") or meta.get("original_reference") or fp.canonical_source)
    return {
        "canonical_hash": fp.canonical_hash,
        "canonical_source": source[:200],
    }
