"""Assemble UPLOAD_IT/ for GitHub + cloud deploy (web-only bundle)."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # KakaoEmoticonFactory
DEST = ROOT.parent / "UPLOAD_IT"  # emiticon/UPLOAD_IT

SKIP_DIR_NAMES = {
    "__pycache__",
    "node_modules",
    ".next",
    ".git",
    "jobs",
    "outputs",
    "gui",
    "AI_CONTEXT",
    "agent-transcripts",
    "terminals",
    "mcps",
    "UPLOAD_IT",
}

SKIP_FILE_NAMES = {".env", ".DS_Store", "Thumbs.db"}

FACTORY_FILES = ["app.py", "config.py", "requirements.txt"]

FACTORY_DIRS = ["services", "data"]

WEB_DIRS = ["frontend", "backend"]

WEB_FILES = ["README.md"]


def should_skip(path: Path) -> bool:
    if path.name in SKIP_FILE_NAMES:
        return True
    if path.suffix in {".pyc", ".pyo"}:
        return True
    parts = path.parts
    if "backend" in parts and "app" in parts:
        bi = parts.index("backend")
        if bi + 1 < len(parts) and parts[bi + 1] == "app":
            return True
    for part in parts:
        if part in SKIP_DIR_NAMES:
            return True
    return False


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        if should_skip(item):
            continue
        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    if DEST.exists():
        shutil.rmtree(DEST, ignore_errors=True)
    DEST.mkdir(parents=True)

    for name in FACTORY_FILES:
        shutil.copy2(ROOT / name, DEST / name)

    for name in FACTORY_DIRS:
        copy_tree(ROOT / name, DEST / name)

    web_dst = DEST / "web"
    web_dst.mkdir()
    for name in WEB_FILES:
        src = ROOT / "web" / name
        if src.is_file():
            shutil.copy2(src, web_dst / name)

    for name in WEB_DIRS:
        copy_tree(ROOT / "web" / name, web_dst / name)

    (web_dst / "jobs").mkdir(exist_ok=True)
    write_text(web_dst / "jobs" / ".gitkeep", "")

    for name in (
        "README_LOCAL_SERVER.md",
        "start_local_server.bat",
        "setup_cloudflare_tunnel.bat",
    ):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, DEST / name)

    copy_tree(ROOT / "cloudflare", DEST / "cloudflare")
    copy_tree(ROOT / "scripts", DEST / "scripts")

    extras = ROOT / "deploy" / "upload_it_extras"
    if extras.is_dir():
        for item in extras.rglob("*"):
            if item.is_dir():
                continue
            rel = item.relative_to(extras)
            target = DEST / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    print(f"UPLOAD_IT ready: {DEST}")
    print("  GitHub: cd UPLOAD_IT && git init && git add . && git commit")


if __name__ == "__main__":
    main()
