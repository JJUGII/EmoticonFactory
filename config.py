"""Kakao big emoticon size limits and output paths (constants)."""

from pathlib import Path

# Canvas / asset sizes (pixels)
EMOTICON_SIZE: tuple[int, int] = (540, 540)
ICON_SIZE: tuple[int, int] = (78, 78)
SHARE_SIZE: tuple[int, int] = (600, 166)

# Kakao-style byte budgets (prototype defaults; verify against latest official guide)
MAX_EMOTICON_BYTES: int = 1 * 1024 * 1024
# Animated sticker WebP (Kakao big emoticon guideline target for this prototype)
MAX_WEBP_ANIM_BYTES: int = 1 * 1024 * 1024
MAX_WEBP_ANIM_FRAMES: int = 24  # inclusive of final preview still appended as last frame
MAX_ICON_BYTES: int = 16 * 1024
MAX_SHARE_BYTES: int = 500 * 1024

# Default output root (relative to KakaoEmoticonFactory working directory)
OUTPUT_DIR: str = "outputs"

# Project root (directory that contains app.py)
PROJECT_ROOT: Path = Path(__file__).resolve().parent
