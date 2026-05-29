"""Discord 서버 스티커 자동 업로드.

흐름:
  1. 유저가 웹에서 "Discord 서버에 추가" 클릭
  2. Discord OAuth2 봇 초대 URL로 리디렉션
     (bot + applications.commands 스코프, MANAGE_GUILD_EXPRESSIONS 권한)
  3. 유저가 서버 선택 후 "허가" → callback URL로 code + guild_id 전달
  4. 백엔드: code → access_token 교환 + guild_id 확인
  5. 봇 토큰으로 guild stickers 업로드 (최대 5~60개, Boost 레벨에 따라)
  6. 업로드 결과 반환

필요 환경변수:
  DISCORD_BOT_TOKEN      - 봇 토큰
  DISCORD_CLIENT_ID      - Application ID
  DISCORD_CLIENT_SECRET  - OAuth2 Client Secret
  DISCORD_REDIRECT_URI   - OAuth2 callback URL (예: http://localhost:8000/api/export/discord/callback)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from factory_web.services.exporters.image_converter import convert_all_pngs

DISCORD_API = "https://discord.com/api/v10"


# ── OAuth2 헬퍼 ──────────────────────────────────────────────────────────────

def get_oauth2_url(state: str) -> str:
    """봇 초대 + OAuth2 URL 생성.

    권한: MANAGE_GUILD_EXPRESSIONS (1 << 3 = 8 + 1 << 30 = 1073741824 → 1073741832)
    """
    client_id = os.environ.get("DISCORD_CLIENT_ID", "")
    redirect_uri = os.environ.get("DISCORD_REDIRECT_URI", "")

    if not client_id:
        raise RuntimeError("DISCORD_CLIENT_ID 환경변수가 없습니다.")

    import urllib.parse
    params = {
        "client_id":     client_id,
        "permissions":   "1073741832",          # MANAGE_GUILD_EXPRESSIONS + bot 기본
        "scope":         "bot applications.commands",
        "response_type": "code",
        "redirect_uri":  redirect_uri,
        "state":         state,
    }
    return f"https://discord.com/api/oauth2/authorize?{urllib.parse.urlencode(params)}"


def exchange_code(code: str) -> dict[str, Any]:
    """OAuth2 code → access_token + guild_id."""
    client_id     = os.environ.get("DISCORD_CLIENT_ID", "")
    client_secret = os.environ.get("DISCORD_CLIENT_SECRET", "")
    redirect_uri  = os.environ.get("DISCORD_REDIRECT_URI", "")

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id":     client_id,
                "client_secret": client_secret,
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Discord OAuth2 오류: {data}")
    return data  # contains guild.id


# ── 스티커 업로드 ────────────────────────────────────────────────────────────

def _bot_headers() -> dict[str, str]:
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN 환경변수가 없습니다.")
    return {"Authorization": f"Bot {token}"}


def get_guild_sticker_slots(guild_id: str) -> int:
    """서버 부스트 레벨에 따른 스티커 슬롯 수 반환."""
    boost_slots = {0: 5, 1: 15, 2: 30, 3: 60}
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{DISCORD_API}/guilds/{guild_id}", headers=_bot_headers())
    guild = resp.json()
    level = guild.get("premium_tier", 0)
    return boost_slots.get(level, 5)


def upload_stickers_to_guild(
    guild_id: str,
    png_dir: Path,
    emotions: list[str],
    series_name: str,
) -> list[dict[str, Any]]:
    """PNG → Discord 스티커 업로드. 슬롯 제한 내에서 최대한 업로드.

    Returns:
        업로드된 스티커 목록 [{"id": ..., "name": ..., "tags": ...}, ...]
    """
    max_slots = get_guild_sticker_slots(guild_id)

    # 현재 서버 스티커 수 확인
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(
            f"{DISCORD_API}/guilds/{guild_id}/stickers",
            headers=_bot_headers(),
        )
    existing = len(resp.json()) if isinstance(resp.json(), list) else 0
    available = max_slots - existing

    if available <= 0:
        raise RuntimeError(
            f"서버 스티커 슬롯이 꽉 찼습니다. (현재 {existing}/{max_slots}개)\n"
            "서버 부스트로 슬롯을 늘리거나 기존 스티커를 삭제하세요."
        )

    converted = convert_all_pngs(png_dir, "discord")
    to_upload = converted[:available]

    print(f"[discord] 서버 {guild_id}: 슬롯 {available}개 사용 가능, {len(to_upload)}개 업로드")

    uploaded = []
    with httpx.Client(timeout=30.0) as client:
        for i, (cut_id, png_bytes) in enumerate(to_upload):
            emotion_text = emotions[i] if i < len(emotions) else f"sticker{cut_id}"
            name = _safe_sticker_name(emotion_text, cut_id)
            tags = emotion_text[:200] if emotion_text else name

            resp = client.post(
                f"{DISCORD_API}/guilds/{guild_id}/stickers",
                headers=_bot_headers(),
                files={"file": (f"{cut_id}.png", png_bytes, "image/png")},
                data={"name": name, "tags": tags, "description": ""},
            )
            result = resp.json()
            if "id" in result:
                uploaded.append(result)
                print(f"[discord] 스티커 업로드 완료: {name} (id={result['id']})")
            else:
                print(f"[discord] 스티커 업로드 실패 {cut_id}: {result}")

    return uploaded


def _safe_sticker_name(text: str, fallback: str) -> str:
    """Discord 스티커 이름: 2~30자, 영숫자·밑줄·하이픈."""
    import re
    name = text.strip()
    # 한글은 영문 transliterate하거나 그대로 사용 (Discord는 유니코드 허용)
    name = re.sub(r"[^\w\s\-]", "", name, flags=re.UNICODE)
    name = re.sub(r"\s+", "_", name).strip("_")
    if len(name) < 2:
        name = f"sticker_{fallback}"
    return name[:30]


def export_for_job(
    job_id: str,
    guild_id: str,
    package_dir: str,
    emotions: list[str],
    series_name: str,
) -> dict[str, Any]:
    """Discord 서버에 스티커 업로드 후 결과 반환."""
    pkg = Path(package_dir)
    png_dir = pkg / "png"
    if not png_dir.is_dir():
        png_dir = pkg / "png_no_text"
    if not png_dir.is_dir():
        raise RuntimeError(f"PNG 폴더를 찾을 수 없습니다: {pkg}")

    uploaded = upload_stickers_to_guild(guild_id, png_dir, emotions, series_name)
    return {
        "guild_id":      guild_id,
        "uploaded_count": len(uploaded),
        "stickers":      [{"id": s["id"], "name": s["name"]} for s in uploaded],
    }
