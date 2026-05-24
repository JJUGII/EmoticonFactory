"""Copy and track ``character/canonical_character.png`` as fixed sticker identity."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANONICAL_FILENAME = "canonical_character.png"
SOURCE_JSON = "canonical_character_source.json"
SELECTED_BASE_CANDIDATE_TYPE = "selected_base_candidate"
SELECTED_BASE_CANDIDATE_POLICY = (
    "사용자가 선택한 베이스 캐릭터를 16컷 이모티콘의 절대 기준으로 고정"
)


class CanonicalCharacterManager:
    """Persist a user- or CLI-chosen character sheet as the canonical identity image."""

    @staticmethod
    def canonical_path(package_dir: Path) -> Path:
        return Path(package_dir) / "character" / CANONICAL_FILENAME

    @classmethod
    def get_canonical_path(cls, package_dir: Path) -> Path | None:
        p = cls.canonical_path(package_dir)
        return p if p.is_file() else None

    @classmethod
    def write_source_metadata(cls, package_dir: Path, metadata: dict[str, Any]) -> Path:
        char_dir = Path(package_dir) / "character"
        char_dir.mkdir(parents=True, exist_ok=True)
        path = char_dir / SOURCE_JSON
        path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def set_from_existing_image(
        cls,
        source_path: Path,
        package_dir: Path,
        source_type: str,
        metadata: dict[str, Any],
    ) -> Path:
        src = Path(source_path)
        if not src.is_file():
            raise FileNotFoundError(str(src))
        dest = cls.canonical_path(package_dir)
        from services.canonical_reuse import safe_copy_file

        safe_copy_file(src, dest, log_same_file=True)
        policy = str(metadata.get("policy") or "").strip()
        if not policy:
            policy = (
                SELECTED_BASE_CANDIDATE_POLICY
                if source_type == SELECTED_BASE_CANDIDATE_TYPE
                else "selected character art is fixed as canonical identity"
            )
        payload: dict[str, Any] = {
            "source_type": source_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "policy": policy,
            "canonical_relative": f"character/{CANONICAL_FILENAME}",
            **metadata,
        }
        cls.write_source_metadata(package_dir, payload)
        return dest
