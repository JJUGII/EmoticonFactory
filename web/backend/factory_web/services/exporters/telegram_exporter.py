"""Telegram 스티커팩 자동 생성 및 배포 링크 발급.

흐름:
  1. PNG 16장 → WebP 512×512 변환
  2. Bot API createNewStickerSet 호출
  3. t.me/addstickers/<name> 링크 반환

필요 환경변수:
  TELEGRAM_BOT_TOKEN       - @BotFather에서 발급
  TELEGRAM_SERVICE_USER_ID - 봇에 /start 보낸 서비스 계정의 숫자 user_id
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

from factory_web.services.exporters.image_converter import convert_all_pngs

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# 감정 텍스트 → Telegram 이모지 매핑
_EMOTION_EMOJI_MAP: list[tuple[tuple[str, ...], str]] = [
    (("사랑", "love", "하트", "heart"),    "❤️"),
    (("좋아", "like", "굿", "좋음"),       "👍"),
    (("고마", "감사", "thank"),            "🙏"),
    (("미안", "sorry", "사과"),            "😢"),
    (("배고", "hungry", "먹"),             "🍽️"),
    (("졸려", "sleepy", "피곤", "잘자"),   "😴"),
    (("행복", "happy", "기뻐"),            "😊"),
    (("화나", "angry", "짜증", "킹받"),    "😤"),
    (("놀랐", "surprised", "헉", "깜짝"), "😱"),
    (("응원", "화이팅", "파이팅", "힘내"), "💪"),
    (("가지마", "보고싶", "그리워"),       "🥺"),
    (("안아", "hug"),                      "🤗"),
    (("심심", "bored", "귀찮"),            "😑"),
    (("축하", "celebr", "만세"),           "🎉"),
    (("설레", "두근", "심쿵"),             "💓"),
    (("뽀뽀", "kiss", "키스"),             "😘"),
    (("질투", "jealous", "부럽"),          "😒"),
    (("울어", "눈물", "슬퍼", "cry"),      "😭"),
    (("귀여", "cute", "냥냥", "뿌잉"),     "🥰"),
    (("대박", "wow", "오졌"),              "🤩"),
    (("으쓱", "뿌듯", "자랑"),             "😎"),
]

_DEFAULT_EMOJI = "😄"


def _emotion_to_emoji(text: str) -> str:
    t = (text or "").strip().lower()
    for keywords, emoji in _EMOTION_EMOJI_MAP:
        if any(kw in t for kw in keywords):
            return emoji
    return _DEFAULT_EMOJI


def _safe_pack_name(job_id: str, bot_username: str) -> str:
    """Telegram 팩 이름: ASCII 영숫자+밑줄, _by_<botname> 필수."""
    short = re.sub(r"[^a-z0-9]", "", job_id.lower())[:16]
    bot = re.sub(r"[^a-z0-9_]", "", bot_username.lower())
    return f"e{short}_by_{bot}"


def _bot_request(token: str, method: str, **kwargs: Any) -> dict:
    """Telegram Bot API 동기 요청 (httpx)."""
    url = TELEGRAM_API.format(token=token, method=method)
    with httpx.Client(timeout=60.0) as client:
        if "files" in kwargs:
            resp = client.post(url, data=kwargs.get("data", {}), files=kwargs["files"])
        else:
            resp = client.post(url, json=kwargs.get("json") or kwargs.get("data") or {})
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API 오류 [{method}]: {result.get('description')}")
    return result


def get_bot_info(token: str) -> dict:
    """봇 정보 조회 (username 확인용)."""
    return _bot_request(token, "getMe")["result"]


def create_sticker_pack(
    token: str,
    service_user_id: int,
    job_id: str,
    pack_title: str,
    png_dir: Path,
    emotions: list[str],
) -> str:
    """스티커팩 생성 후 t.me/addstickers 링크 반환.

    Args:
        token: TELEGRAM_BOT_TOKEN
        service_user_id: 봇에 /start 보낸 서비스 계정 user_id
        job_id: 팩 고유 식별자
        pack_title: 팩 표시 이름 (최대 64자)
        png_dir: Kakao PNG 폴더 (01.png~16.png)
        emotions: 컷 순서대로 감정 텍스트 리스트

    Returns:
        "https://t.me/addstickers/<pack_name>"
    """
    # 봇 username 조회
    bot_info = get_bot_info(token)
    bot_username = bot_info["username"]

    pack_name = _safe_pack_name(job_id, bot_username)

    # 기존 팩 확인 (이미 생성된 경우 링크만 반환)
    try:
        existing = _bot_request(token, "getStickerSet", json={"name": pack_name})
        print(f"[telegram] 기존 팩 재사용: {pack_name}")
        return f"https://t.me/addstickers/{pack_name}"
    except RuntimeError:
        pass  # 없으면 새로 생성

    # WebP 변환
    sticker_data = convert_all_pngs(png_dir, "telegram")
    if not sticker_data:
        raise RuntimeError("변환할 PNG가 없습니다.")

    print(f"[telegram] 팩 생성 시작: {pack_name} ({len(sticker_data)}컷)")

    # stickers JSON + multipart files 구성
    stickers_json = []
    files: dict[str, tuple] = {}

    for i, (cut_id, webp_bytes) in enumerate(sticker_data):
        emotion_text = emotions[i] if i < len(emotions) else ""
        emoji = _emotion_to_emoji(emotion_text)
        attach_name = f"sticker{i}"
        files[attach_name] = (f"{attach_name}.webp", webp_bytes, "image/webp")
        stickers_json.append({
            "sticker": f"attach://{attach_name}",
            "emoji_list": [emoji],
            "format": "static",
        })

    # createNewStickerSet
    data = {
        "user_id":      str(service_user_id),
        "name":         pack_name,
        "title":        pack_title[:64],
        "stickers":     json.dumps(stickers_json, ensure_ascii=False),
        "sticker_type": "regular",
    }

    url = TELEGRAM_API.format(token=token, method="createNewStickerSet")
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, data=data, files=files)

    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"createNewStickerSet 실패: {result.get('description')}")

    link = f"https://t.me/addstickers/{pack_name}"
    print(f"[telegram] 팩 생성 완료: {link}")
    return link


def export_for_job(job_id: str, package_dir: str, emotions: list[str], series_name: str) -> str:
    """파이프라인에서 호출하는 진입점.

    환경변수에서 토큰/user_id를 읽어 스티커팩 생성 후 링크 반환.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    user_id_str = os.environ.get("TELEGRAM_SERVICE_USER_ID", "").strip()

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 환경변수가 없습니다.")
    if not user_id_str:
        raise RuntimeError("TELEGRAM_SERVICE_USER_ID 환경변수가 없습니다.")

    service_user_id = int(user_id_str)
    pkg = Path(package_dir)

    # PNG 디렉토리 탐색
    png_dir = pkg / "png"
    if not png_dir.is_dir():
        png_dir = pkg / "png_no_text"
    if not png_dir.is_dir():
        raise RuntimeError(f"PNG 폴더를 찾을 수 없습니다: {pkg}")

    pack_title = f"{series_name} Stickers"
    return create_sticker_pack(token, service_user_id, job_id, pack_title, png_dir, emotions)
