"""Signal 스티커팩 업로드 및 signal.art 링크 발급.

흐름:
  1. PNG 16장 → WebP 512×512, 300KB 이하 변환
  2. signalstickers-client로 Signal CDN에 업로드
  3. signal.art/addstickers/#pack_id=...&pack_key=... 링크 반환

필요 환경변수:
  SIGNAL_USERNAME  - Signal 계정 전화번호 (+821012345678 형식)
  SIGNAL_PASSWORD  - Signal 등록 비밀번호 (계정 설정 > Linked Devices > 비밀번호)

참고:
  - Signal 측에서 팩이 계정에 연결되지 않는다고 명시 (프라이버시 설계)
  - 서버 Signal 계정 1개로 모든 유저 팩 업로드 가능
  - 비공식 API — Signal 정책 변경 시 중단될 수 있음
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from factory_web.services.exporters.image_converter import convert_all_pngs


def _run_async(coro):
    """동기 컨텍스트에서 async 함수 실행."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _upload_pack_async(
    username: str,
    password: str,
    pack_title: str,
    pack_author: str,
    sticker_items: list[tuple[str, bytes, str]],  # (cut_id, webp_bytes, emoji)
) -> tuple[str, str]:
    """Signal CDN에 팩 업로드 후 (pack_id, pack_key) 반환."""
    from signalstickers_client import StickersClient
    from signalstickers_client.models import LocalStickerPack, Sticker

    pack = LocalStickerPack()
    pack.title = pack_title
    pack.author = pack_author

    for i, (cut_id, webp_bytes, emoji) in enumerate(sticker_items):
        sticker = Sticker()
        sticker.id = i
        sticker.emoji = emoji
        sticker.image_data = webp_bytes
        pack.stickers[i] = sticker

    # 커버 이미지: 첫 번째 스티커 사용
    if sticker_items:
        cover = Sticker()
        cover.id = len(sticker_items)
        cover.emoji = sticker_items[0][2]
        cover.image_data = sticker_items[0][1]
        pack.cover = cover

    async with StickersClient(username, password) as client:
        pack_id, pack_key = await client.upload_pack(pack)

    return pack_id, pack_key


_EMOJI_MAP: list[tuple[tuple[str, ...], str]] = [
    (("사랑", "love", "하트"),             "❤️"),
    (("좋아", "like", "굿"),               "👍"),
    (("고마", "감사", "thank"),            "🙏"),
    (("미안", "sorry", "사과"),            "😢"),
    (("배고", "hungry", "먹"),             "🍽️"),
    (("졸려", "sleepy", "피곤", "잘자"),   "😴"),
    (("행복", "happy", "기뻐"),            "😊"),
    (("화나", "angry", "짜증", "킹받"),    "😤"),
    (("놀랐", "surprised", "헉"),          "😱"),
    (("응원", "화이팅", "파이팅"),         "💪"),
    (("가지마", "보고싶", "그리워"),       "🥺"),
    (("안아", "hug"),                      "🤗"),
    (("심심", "bored", "귀찮"),            "😑"),
    (("축하", "celebr", "만세"),           "🎉"),
    (("설레", "두근", "심쿵"),             "💓"),
    (("뽀뽀", "kiss", "키스"),             "😘"),
    (("귀여", "cute", "냥냥", "뿌잉"),     "🥰"),
    (("대박", "wow"),                      "🤩"),
]

_DEFAULT_EMOJI = "😄"


def _to_emoji(text: str) -> str:
    t = (text or "").strip().lower()
    for keywords, emoji in _EMOJI_MAP:
        if any(kw in t for kw in keywords):
            return emoji
    return _DEFAULT_EMOJI


def export_for_job(
    job_id: str,
    package_dir: str,
    emotions: list[str],
    series_name: str,
) -> str:
    """Signal 스티커팩 업로드 후 signal.art 링크 반환.

    Returns:
        "https://signal.art/addstickers/#pack_id=...&pack_key=..."
    """
    username = os.environ.get("SIGNAL_USERNAME", "").strip()
    password = os.environ.get("SIGNAL_PASSWORD", "").strip()

    if not username or not password:
        raise RuntimeError(
            "SIGNAL_USERNAME / SIGNAL_PASSWORD 환경변수가 없습니다.\n"
            "Signal 계정 전화번호와 비밀번호를 .env에 추가하세요."
        )

    pkg = Path(package_dir)
    png_dir = pkg / "png"
    if not png_dir.is_dir():
        png_dir = pkg / "png_no_text"
    if not png_dir.is_dir():
        raise RuntimeError(f"PNG 폴더를 찾을 수 없습니다: {pkg}")

    # WebP 변환
    converted = convert_all_pngs(png_dir, "signal")
    if not converted:
        raise RuntimeError("변환할 PNG가 없습니다.")

    sticker_items = [
        (cut_id, webp_bytes, _to_emoji(emotions[i] if i < len(emotions) else ""))
        for i, (cut_id, webp_bytes) in enumerate(converted)
    ]

    print(f"[signal] 팩 업로드 시작: {len(sticker_items)}컷")
    pack_id, pack_key = _run_async(
        _upload_pack_async(
            username=username,
            password=password,
            pack_title=f"{series_name} Stickers",
            pack_author="EmoticonFactory",
            sticker_items=sticker_items,
        )
    )

    link = f"https://signal.art/addstickers/#pack_id={pack_id}&pack_key={pack_key}"
    print(f"[signal] 업로드 완료: {link}")
    return link
