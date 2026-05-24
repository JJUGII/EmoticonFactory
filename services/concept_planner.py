"""Load 16-cut planning templates; validate with ``BigEmoticonPose``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from config import PROJECT_ROOT
from services.pose_schema import BigEmoticonPose
from services.theme_cut_enrichment import enrich_cut_plan_item


class ConceptPlanner:
    """Builds a 16-cut plan from JSON templates (theme/series reserved for future AI)."""

    def __init__(self, templates_path: Path | None = None) -> None:
        self._templates_path = templates_path or (
            PROJECT_ROOT / "data" / "big_emoticon_templates.json"
        )

    def plan(self, theme: str, series_name: str) -> list[dict[str, Any]]:
        """Return validated pose dicts enriched with ``_theme`` / ``_series_name``.

        Raises:
            FileNotFoundError: Template missing.
            ValueError: Not 16 cuts or validation failed.
        """
        path = self._templates_path
        if not path.is_file():
            raise FileNotFoundError(f"템플릿 파일을 찾을 수 없습니다: {path}")

        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("템플릿 JSON은 배열(list) 형식이어야 합니다.")

        out: list[dict[str, Any]] = []
        for i, row in enumerate(data):
            if not isinstance(row, dict):
                raise ValueError(f"템플릿 {i}번 항목이 객체(dict)가 아닙니다.")
            try:
                pose = BigEmoticonPose.model_validate(row)
            except ValidationError as exc:
                raise ValueError(f"컷 {row.get('id', i)} 검증 실패: {exc}") from exc

            item = pose.model_dump(mode="json")
            item["_theme"] = theme
            item["_series_name"] = series_name
            enrich_cut_plan_item(theme, item)
            out.append(item)

        if len(out) != 16:
            raise ValueError(f"템플릿은 16개여야 합니다. 현재: {len(out)}")

        return out

    @staticmethod
    def cut_plan_document(
        theme: str, series_name: str, items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """JSON-serializable document for ``meta/cut_plan.json``."""

        def _strip_meta(d: dict[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in d.items() if not str(k).startswith("_")}

        return {
            "series_name": series_name,
            "theme": theme,
            "cut_count": len(items),
            "cuts": [_strip_meta(item) for item in items],
        }
