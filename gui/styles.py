"""Minimal application styles (v0.1 — stability over polish)."""

APP_STYLESHEET = """
QMainWindow { background: #1e1e1e; color: #e0e0e0; }
QLabel { color: #e0e0e0; }
QLineEdit, QComboBox, QTextEdit {
  background: #2d2d2d;
  color: #e0e0e0;
  border: 1px solid #444;
  border-radius: 4px;
  padding: 4px;
}
QPushButton {
  background: #3a6ea5;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 8px 12px;
}
QPushButton:disabled { background: #555; color: #aaa; }
QPushButton#secondary { background: #444; }
QProgressBar {
  border: 1px solid #444;
  border-radius: 3px;
  text-align: center;
  height: 18px;
}
QProgressBar::chunk { background: #3a6ea5; }
"""
