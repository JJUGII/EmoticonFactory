"""Web Push 알림 발송 (pywebpush + VAPID)."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

try:
    from pywebpush import webpush, WebPushException
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def _get_vapid_claims() -> dict[str, str]:
    subject = os.environ.get("VAPID_SUBJECT", "mailto:admin@emoticonfactory.app")
    return {"sub": subject}


def send(
    *,
    subscription: dict[str, Any],
    title: str,
    body: str,
    url: str = "/",
) -> bool:
    """Push 알림 발송. 성공 True, 실패 False 반환."""
    if not _AVAILABLE:
        print("[push] pywebpush 미설치 — 알림 건너뜀")
        return False

    private_key = os.environ.get("VAPID_PRIVATE_KEY", "")
    if not private_key:
        print("[push] VAPID_PRIVATE_KEY 없음 — 알림 건너뜀")
        return False

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
    })

    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=private_key,
            vapid_claims=_get_vapid_claims(),
        )
        print(f"[push] 알림 발송 완료: {title}")
        return True
    except WebPushException as e:
        print(f"[push] 발송 실패: {e}")
        return False
    except Exception as e:
        print(f"[push] 예외: {e}")
        return False
