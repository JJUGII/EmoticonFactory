"""Qt GUI entry (PySide6). Run from ``KakaoEmoticonFactory/``: ``python gui_app.py``."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QMainWindow

from gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle("반려동물 이모티콘 생성기")
    inner = MainWindow()
    win.setCentralWidget(inner)
    win.resize(1120, 860)
    win.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
