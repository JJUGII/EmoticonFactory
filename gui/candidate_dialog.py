"""Large dialog for picking one of three base character candidates."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def _style_caption(entry: dict | None, index_1based: int) -> str:
    if not entry:
        return f"후보 {index_1based}"
    hint = str(entry.get("style_hint") or "").strip()
    seed = entry.get("variation_seed")
    if hint and seed is not None:
        return f"후보 {index_1based} · {hint} (seed={seed})"
    if hint:
        return f"후보 {index_1based} · {hint}"
    return f"후보 {index_1based}"


def _load_manifest_entries(candidates_dir: Path | None) -> list[dict]:
    if candidates_dir is None:
        return []
    manifest = candidates_dir / "candidates.json"
    if not manifest.is_file():
        return []
    try:
        doc = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = doc.get("candidates")
    return list(rows) if isinstance(rows, list) else []


class CandidateDialog(QDialog):
    """Pick the canonical base character for the 16-cut pack."""

    REGENERATE_CODE = 2

    def __init__(
        self,
        paths: list[Path],
        parent: QWidget | None = None,
        *,
        candidates_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("16컷의 기준이 될 캐릭터를 선택하세요")
        self._paths = [p for p in paths if p.is_file()]
        self._selected_1based: int | None = None
        self._cards: list[QPushButton] = []
        manifest_entries = _load_manifest_entries(candidates_dir)

        lay = QVBoxLayout(self)
        hint = QLabel(
            "입력 이미지와 같은 정체성으로 만든 베이스 캐릭터 3장입니다. "
            "16컷 이모티콘의 기준이 될 1장을 고르세요."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555; margin-bottom: 8px;")
        lay.addWidget(hint)
        row = QHBoxLayout()
        for i, p in enumerate(self._paths):
            btn = QPushButton()
            btn.setFlat(True)
            pm = QPixmap(str(p))
            if not pm.isNull():
                scaled = pm.scaled(
                    280,
                    280,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                btn.setIcon(QIcon(scaled))
                btn.setIconSize(QSize(scaled.width(), scaled.height()))
            btn.setMinimumSize(300, 300)
            idx = i + 1
            btn.clicked.connect(lambda _=False, j=idx: self._pick(j))
            self._cards.append(btn)
            entry = manifest_entries[i] if i < len(manifest_entries) else None
            if not isinstance(entry, dict):
                entry = None
            col = QVBoxLayout()
            cap = QLabel(_style_caption(entry, idx))
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(cap)
            col.addWidget(btn)
            row.addLayout(col)
        lay.addLayout(row)

        btn_row = QHBoxLayout()
        regen = QPushButton("다시 생성")
        cancel = QPushButton("취소")
        ok = QPushButton("선택 확정")
        regen.clicked.connect(lambda: self.done(self.REGENERATE_CODE))
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._on_accept)
        btn_row.addWidget(regen)
        btn_row.addStretch(1)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        lay.addLayout(btn_row)

    def _pick(self, one_based: int) -> None:
        self._selected_1based = one_based
        for i, b in enumerate(self._cards):
            b.setStyleSheet("border: 3px solid #6ab0ff;" if i + 1 == one_based else "")

    def _on_accept(self) -> None:
        if self._selected_1based is None:
            QMessageBox.warning(self, "선택", "후보 카드를 먼저 클릭하세요.")
            return
        self.accept()

    def selected_index_1based(self) -> int | None:
        return self._selected_1based
