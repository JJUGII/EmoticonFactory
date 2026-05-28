"""Reusable image widgets for the GUI."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _load_pixmap(path: Path, max_side: int = 512) -> QPixmap:
    img = QImage(str(path))
    if img.isNull():
        return QPixmap()
    return QPixmap.fromImage(img).scaled(
        max_side,
        max_side,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class ImageCard(QWidget):
    """Clickable thumbnail with optional selection border."""

    clicked = Signal()

    def __init__(self, title: str, path: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("imageCard")
        self._path = path
        self._selected = False
        lay = QVBoxLayout(self)
        self._title = QLabel(title)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img = QLabel()
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setMinimumSize(120, 120)
        self._img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if path and path.is_file():
            self._img.setPixmap(_load_pixmap(path, 200))
        else:
            self._img.setText("(없음)")
        lay.addWidget(self._title)
        lay.addWidget(self._img)
        self.set_selected(False)

    def set_image_path(self, path: Path | None) -> None:
        """Update thumbnail from ``path`` (or clear)."""
        self._path = path
        if path and path.is_file():
            self._img.setPixmap(_load_pixmap(path, 200))
        else:
            self._img.setText("(없음)")
        self.set_selected(False)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit()
        super().mousePressEvent(event)

    def path(self) -> Path | None:
        return self._path

    def set_selected(self, on: bool) -> None:
        self._selected = on
        border = "2px solid #6ab0ff" if on else "1px solid #444"
        self.setStyleSheet(f"#imageCard {{ border: {border}; border-radius: 6px; padding: 4px; }}")

    def is_selected(self) -> bool:
        return self._selected


class CutResultCell(QWidget):
    """Single cut thumbnail with drift/fail styling and optional regen button."""

    regenerate_requested = Signal(str)

    def __init__(self, cut_id: str, path: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cut_id = cut_id
        lay = QVBoxLayout(self)
        self._title = QLabel(cut_id)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img = QLabel()
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setMinimumSize(100, 100)
        if path and path.is_file():
            self._img.setPixmap(_load_pixmap(path, 140))
        else:
            self._img.setText("(없음)")
        self._score = QLabel("")
        self._score.setWordWrap(True)
        self._score.setStyleSheet("font-size: 10px; color: #666;")
        self._btn = QPushButton("재생성")
        self._btn.setMaximumHeight(26)
        self._btn.clicked.connect(lambda: self.regenerate_requested.emit(self._cut_id))
        lay.addWidget(self._title)
        lay.addWidget(self._img)
        lay.addWidget(self._score)
        lay.addWidget(self._btn)
        self.set_fail_style(False)

    def set_fail_style(self, on: bool) -> None:
        border = "3px solid #e53935" if on else "1px solid #444"
        self.setStyleSheet(f"border: {border}; border-radius: 6px; padding: 4px;")

    def set_score_text(self, text: str) -> None:
        self._score.setText(text)


class ResultGridWidget(QWidget):
    """4×4-style grid of final sticker PNGs with consistency drift highlighting."""

    regenerate_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._root: Path | None = None
        outer = QVBoxLayout(self)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._inner = QWidget()
        self._grid = QGridLayout(self._inner)
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)

    def _consistency_map(self, package_dir: Path) -> dict[str, dict]:
        rep = package_dir / "meta" / "consistency_report.json"
        if not rep.is_file():
            return {}
        try:
            doc = json.loads(rep.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        m: dict[str, dict] = {}
        for row in doc.get("items") or []:
            if isinstance(row, dict) and row.get("id"):
                m[str(row["id"])] = row
        return m

    def load_from_package_dir(self, package_dir: Path) -> None:
        self._root = package_dir
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        info_path = package_dir / "meta" / "package_info.json"
        if not info_path.is_file():
            lbl = QLabel("package_info.json 없음")
            self._grid.addWidget(lbl, 0, 0)
            return
        try:
            data = json.loads(info_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            lbl = QLabel("package_info.json 읽기 실패")
            self._grid.addWidget(lbl, 0, 0)
            return
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return
        cons_map = self._consistency_map(package_dir)
        failed_ids: set[str] = set()
        rep_path = package_dir / "meta" / "consistency_report.json"
        if rep_path.is_file():
            try:
                rep = json.loads(rep_path.read_text(encoding="utf-8"))
                failed_ids = {str(r.get("id")) for r in rep.get("failed") or [] if r.get("id")}
            except (OSError, json.JSONDecodeError):
                pass

        row = col = 0
        max_cols = 4
        for it in items:
            if not isinstance(it, dict):
                continue
            cid = str(it.get("id", "")).zfill(2)
            rel = str(it.get("png", "") or "").replace("\\", "/")
            if not rel:
                continue
            fp = (package_dir / rel).resolve()
            cell = CutResultCell(cid, fp if fp.is_file() else None)
            crow = cons_map.get(cid, {})
            id_s = crow.get("identity_similarity", "")
            cid_s = crow.get("canonical_identity_score", "")
            drift_st = crow.get("drift_status", "")
            is_fail = cid in failed_ids or str(crow.get("status")) == "fail" or drift_st == "fail"
            cell.set_fail_style(is_fail)
            cell.set_score_text(
                f"id={id_s} canon={cid_s} drift={crow.get('drift_similarity', '')} ({drift_st})"
            )
            cell.regenerate_requested.connect(self.regenerate_requested.emit)
            self._grid.addWidget(cell, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def _open_view(self, fp: Path) -> None:
        if not fp.is_file():
            QMessageBox.warning(self, "이미지", "파일이 없습니다.")
            return
        dlg = QMessageBox(self)
        dlg.setWindowTitle(str(fp.name))
        pix = _load_pixmap(fp, 480)
        if not pix.isNull():
            dlg.setIconPixmap(pix)
        dlg.setText(str(fp))
        dlg.exec()
