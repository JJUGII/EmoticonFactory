"""솔라피(Solapi) SMS 발송 서비스.

환경 변수:
    SOLAPI_API_KEY      솔라피 API 키
    SOLAPI_API_SECRET   솔라피 API 시크릿
    SOLAPI_SENDER       발신 번호 (010-XXXX-XXXX 또는 0XXXXXXXX)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from typing import Any

try:
    import requests as _requests
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def _auth_headers() -> dict[str, str]:
    """솔라피 HMAC-SHA256 인증 헤더 생성."""
    api_key = os.environ.get("SOLAPI_API_KEY", "")
    api_secret = os.environ.get("SOLAPI_API_SECRET", "")

    date = _iso_date()
    salt = uuid.uuid4().hex
    signature_raw = f"{date}{salt}"
    signature = hmac.new(
        api_secret.encode(), signature_raw.encode(), hashlib.sha256
    ).hexdigest()

    return {
        "Authorization": (
            f"HMAC-SHA256 apiKey={api_key}, "
            f"date={date}, salt={salt}, signature={signature}"
        ),
        "Content-Type": "application/json",
    }


def _iso_date() -> str:
    """RFC3339 형식 UTC 타임스탬프."""
    t = time.gmtime()
    return (
        f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
        f"T{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}Z"
    )


def _normalize_phone(phone: str) -> str:
    """전화번호 정규화: 하이픈·공백 제거, 국가코드(+82) 처리."""
    p = phone.strip().replace("-", "").replace(" ", "").replace("+82", "0")
    return p


def send(*, to: str, text: str) -> bool:
    """SMS 발송. 성공 True, 실패 False.

    Args:
        to:   수신 전화번호 (010-1234-5678 형태도 가능)
        text: 메시지 본문 (90바이트 이하 권장, 초과 시 LMS 자동 처리)
    """
    if not _AVAILABLE:
        print("[sms] requests 미설치 — SMS 건너뜀")
        return False

    api_key = os.environ.get("SOLAPI_API_KEY", "")
    api_secret = os.environ.get("SOLAPI_API_SECRET", "")
    sender = os.environ.get("SOLAPI_SENDER", "")

    if not api_key or not api_secret:
        print("[sms] SOLAPI_API_KEY / SOLAPI_API_SECRET 없음 — SMS 건너뜀")
        return False
    if not sender:
        print("[sms] SOLAPI_SENDER 없음 — SMS 건너뜀")
        return False

    to_norm = _normalize_phone(to)
    payload: dict[str, Any] = {
        "message": {
            "to": to_norm,
            "from": _normalize_phone(sender),
            "text": text,
        }
    }

    try:
        resp = _requests.post(
            "https://api.solapi.com/messages/v4/send",
            headers=_auth_headers(),
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            print(f"[sms] 발송 완료 → {to_norm}")
            return True
        print(f"[sms] 발송 실패 {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"[sms] 예외: {e}")
        return False
