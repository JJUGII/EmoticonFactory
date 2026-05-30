"""Slack 워크스페이스 커스텀 이모지 업로드.

흐름:
  1. 유저가 Slack 앱 포털에서 워크스페이스에 설치 후 User OAuth Token(xoxp-...) 복사
  2. EmoticonFactory 웹에서 토큰 붙여넣기 + "업로드" 클릭
  3. 백엔드: 이모티콘 PNG → emoji.add API로 업로드

필요 OAuth Scope (User Token):
  emoji:write

이미지 규격:
  - PNG, 정사각형
  - 128KB 이하 (초과 시 자동 축소)
  - 이름: 영문 소문자·숫자·하이픈·밑줄 2~100자
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

from factory_web.services.exporters.image_converter import convert_all_pngs

SLACK_API = "https://slack.com/api"


# ── 이모지 업로드 ─────────────────────────────────────────────────────────────

def _safe_emoji_name(text: str, fallback: str) -> str:
    """Slack 이모지 이름: 2~100자, 영문 소문자·숫자·하이픈·밑줄."""
    name = text.lower().strip()
    name = re.sub(r"[^\w\s\-]", "", name, flags=re.UNICODE)
    name = re.sub(r"\s+", "_", name).strip("_")
    # 한글 등 비ASCII 제거 후 짧으면 fallback 사용
    ascii_only = re.sub(r"[^a-z0-9_\-]", "", name)
    if len(ascii_only) < 2:
        ascii_only = f"sticker_{fallback}"
    return ascii_only[:100]


def upload_emoji(token: str, name: str, image_bytes: bytes) -> dict[str, Any]:
    """단일 이모지 업로드. 성공 시 {"ok": True} 반환."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{SLACK_API}/emoji.add",
            headers={"Authorization": f"Bearer {token}"},
            data={"name": name, "mode": "data"},
            files={"image": (f"{name}.png", image_bytes, "image/png")},
        )
    result = resp.json()
    return result


def verify_token(token: str) -> dict[str, Any]:
    """토큰 유효성 확인 및 워크스페이스 정보 반환."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            f"{SLACK_API}/auth.test",
            headers={"Authorization": f"Bearer {token}"},
        )
    return resp.json()


# ── Job 전체 내보내기 ──────────────────────────────────────────────────────────

def export_for_job(
    job_id: str,
    token: str,
    package_dir: str,
    emotions: list[str],
    series_name: str,
) -> dict[str, Any]:
    """이모티콘 패키지의 PNG를 Slack 커스텀 이모지로 업로드.

    Returns:
        {"uploaded": [...], "failed": [...], "workspace": "team_name"}
    """
    # 토큰 확인
    auth = verify_token(token)
    if not auth.get("ok"):
        raise RuntimeError(f"Slack 토큰 오류: {auth.get('error', '알 수 없는 오류')}")

    workspace = auth.get("team", "unknown")
    print(f"[slack] 워크스페이스: {workspace} / 사용자: {auth.get('user')}")

    pkg = Path(package_dir)
    png_dir = pkg / "png"
    if not png_dir.is_dir():
        png_dir = pkg / "png_no_text"
    if not png_dir.is_dir():
        raise RuntimeError(f"PNG 폴더를 찾을 수 없습니다: {pkg}")

    # Slack 이모지 규격으로 변환 (PNG 128KB 이하)
    converted = convert_all_pngs(png_dir, "discord")  # discord 규격(PNG)과 동일

    uploaded = []
    failed = []

    for i, (cut_id, png_bytes) in enumerate(converted):
        emotion_text = emotions[i] if i < len(emotions) else f"sticker{i}"
        name = _safe_emoji_name(emotion_text, cut_id)

        # 이름 중복 방지: prefix로 시리즈명 축약 추가
        prefix = re.sub(r"[^a-z0-9]", "", series_name.lower())[:8] or "emo"
        full_name = f"{prefix}_{name}"[:100]

        result = upload_emoji(token, full_name, png_bytes)
        if result.get("ok"):
            uploaded.append({"name": full_name, "emotion": emotion_text})
            print(f"[slack] 이모지 업로드 완료: :{full_name}:")
        else:
            err = result.get("error", "unknown")
            # 이미 존재하는 이모지면 성공으로 처리
            if err == "error_name_taken":
                uploaded.append({"name": full_name, "emotion": emotion_text, "cached": True})
                print(f"[slack] 이미 존재: :{full_name}:")
            else:
                failed.append({"name": full_name, "error": err})
                print(f"[slack] 업로드 실패 {full_name}: {err}")

    return {
        "workspace": workspace,
        "uploaded_count": len(uploaded),
        "failed_count": len(failed),
        "uploaded": uploaded,
        "failed": failed,
    }
