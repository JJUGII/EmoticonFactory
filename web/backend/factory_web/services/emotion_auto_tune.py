"""
감정 단어 자동 튜닝 모듈 — 미등록 단어 자동 템플릿 매칭

  Method A: 서버 시작 시 GPT-4o-mini로 각 16개 템플릿 감정당
            한국어 유사어 30개 확장 → JSON 캐시 저장
  Method B: A로도 매칭 못한 단어 → OpenAI text-embedding-3-small
            cosine similarity로 가장 유사한 템플릿 선택

점수 체계:
  100-80  하드코딩 키워드 테이블 (_EMOTION_TEMPLATE_PREFS)
  60      GPT 확장 키워드 (Method A)
  40      임베딩 cosine similarity (Method B, 단어당 1회 API 호출)
  순서폴백 위 모두 실패 시 남은 템플릿 순서 배정
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── 16개 템플릿 감정 레이블 (0-based, big_emoticon_templates.json 순서) ──────
TEMPLATE_EMOTION_LABELS: list[str] = [
    "따뜻한 애정, 사랑, 하트",          # 0
    "애틋함, 보고싶음, 그리움",          # 1
    "애교, 안아줘, 귀여운 행동",         # 2
    "기쁨, 행복, 좋아",                  # 3
    "서운함, 삐짐, 섭섭함",              # 4
    "질투, 시기, 부러움",                # 5
    "설렘, 두근거림, 심쿵",             # 6
    "달콤함, 뽀뽀, 키스, 윙크",         # 7
    "호기심, 궁금함, 뭐해",             # 8
    "평온, 졸림, 잘자, 쿨쿨",           # 9
    "감사, 고마움, 감사해",              # 10
    "미안함, 사과, 죄송",               # 11
    "무기력, 귀찮음, 지침",             # 12
    "동의, 인정, 맞아",                 # 13
    "짜증, 화남, 분노",                 # 14
    "과한 애정, 하트 폭격, 넘치는 기쁨", # 15
]

_CACHE_DIR = Path(__file__).parent
_KEYWORD_CACHE_FILE = _CACHE_DIR / "emotion_keyword_cache.json"
_EMBED_CACHE_FILE = _CACHE_DIR / "emotion_embed_cache.json"
_CACHE_MAX_AGE_DAYS = 30  # 캐시 유효기간 (일)

# ── 런타임 상태 ──────────────────────────────────────────────────────────────
_expanded_keywords: dict[int, list[str]] = {}   # idx → [단어, ...]
_template_embeddings: dict[int, list[float]] = {}  # idx → vector
_init_lock = threading.Lock()
_initialized = False


# ── 내부 유틸 ────────────────────────────────────────────────────────────────

def _get_client():
    """OpenAI 클라이언트 lazy import. API 키 없으면 None."""
    try:
        from openai import OpenAI  # noqa: PLC0415
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return None
        return OpenAI(api_key=api_key)
    except ImportError:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if (na and nb) else 0.0


def _cache_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < _CACHE_MAX_AGE_DAYS * 86400


# ── Method A: GPT 키워드 확장 ─────────────────────────────────────────────

def _gpt_expand_keywords(client) -> dict[int, list[str]]:
    """GPT-4o-mini로 각 감정 카테고리당 한국어 유사 표현 생성 (2배치, 0-7 / 8-15)."""
    result: dict[int, list[str]] = {}
    system = (
        "You are a Korean internet-slang and emotion expert for KakaoTalk sticker design. "
        "Output ONLY valid JSON, no markdown fences."
    )

    for batch_start, batch_end in ((0, 8), (8, 16)):
        batch_labels = "\n".join(
            f"{i}: {TEMPLATE_EMOTION_LABELS[i]}" for i in range(batch_start, batch_end)
        )
        idx_range = f'"{batch_start}"~"{batch_end - 1}"'
        user = (
            f"아래 감정 카테고리 각각에 대해, 카카오톡 채팅에서 실제로 쓰는 "
            f"한국어 표현·단어·신조어·의성어·의태어를 20개씩 만들어줘. "
            f"구어체, 줄임말, Z세대 신조어 포함.\n\n"
            f"감정 카테고리:\n{batch_labels}\n\n"
            f"JSON 형식 (키는 {idx_range} 숫자 문자열): "
            f'{{{{"\\"{batch_start}\\"": ["단어1",...], ..., "\\"{batch_end-1}\\"": [...]}}}}'
        )
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.8,
                max_tokens=2500,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "{}"
            data: dict = json.loads(raw)
            for k, v in data.items():
                if str(k).isdigit():
                    result[int(k)] = [str(w) for w in v]
        except Exception as e:
            logger.warning(f"[auto_tune] GPT 배치 {batch_start}-{batch_end-1} 실패: {e}")

    return result


# ── Method B: 임베딩 캐시 구축 ───────────────────────────────────────────────

def _build_embeddings(client) -> dict[int, list[float]]:
    """16개 감정 레이블을 임베딩해 인덱스 → 벡터 반환."""
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=TEMPLATE_EMOTION_LABELS,
    )
    return {i: d.embedding for i, d in enumerate(resp.data)}


# ── 초기화 ──────────────────────────────────────────────────────────────────

def initialize(force: bool = False) -> bool:
    """
    서버 시작 시 한 번만 호출.
    캐시가 있으면 읽고, 없으면 GPT + 임베딩 API로 생성.
    백그라운드 스레드에서 호출해도 안전(lock 보호).

    Returns:
        True if at least one of (keywords, embeddings) is loaded.
    """
    global _expanded_keywords, _template_embeddings, _initialized

    with _init_lock:
        if _initialized and not force:
            return True

        client = _get_client()
        if client is None:
            logger.warning("[auto_tune] OPENAI_API_KEY 없음 → 자동 튜닝 비활성")
            _initialized = True
            return False

        # ── A: 키워드 확장 캐시 ─────────────────────────
        if _cache_fresh(_KEYWORD_CACHE_FILE) and not force:
            try:
                raw = json.loads(_KEYWORD_CACHE_FILE.read_text(encoding="utf-8"))
                _expanded_keywords = {int(k): v for k, v in raw.items()}
                total = sum(len(v) for v in _expanded_keywords.values())
                logger.info(f"[auto_tune] 키워드 캐시 로드: {total}개")
            except Exception as e:
                logger.warning(f"[auto_tune] 키워드 캐시 로드 실패: {e}")
                _expanded_keywords = {}

        if not _expanded_keywords:
            try:
                logger.info("[auto_tune] GPT 키워드 확장 생성 중...")
                _expanded_keywords = _gpt_expand_keywords(client)
                _KEYWORD_CACHE_FILE.write_text(
                    json.dumps(
                        {str(k): v for k, v in _expanded_keywords.items()},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                total = sum(len(v) for v in _expanded_keywords.values())
                logger.info(f"[auto_tune] 키워드 확장 완료 & 캐시 저장: {total}개")
            except Exception as e:
                logger.error(f"[auto_tune] GPT 키워드 확장 실패: {e}")

        # ── B: 임베딩 캐시 ──────────────────────────────
        if _cache_fresh(_EMBED_CACHE_FILE) and not force:
            try:
                raw = json.loads(_EMBED_CACHE_FILE.read_text(encoding="utf-8"))
                _template_embeddings = {int(k): v for k, v in raw.items()}
                logger.info(f"[auto_tune] 임베딩 캐시 로드: {len(_template_embeddings)}개")
            except Exception as e:
                logger.warning(f"[auto_tune] 임베딩 캐시 로드 실패: {e}")
                _template_embeddings = {}

        if not _template_embeddings:
            try:
                logger.info("[auto_tune] 템플릿 임베딩 생성 중...")
                _template_embeddings = _build_embeddings(client)
                _EMBED_CACHE_FILE.write_text(
                    json.dumps(
                        {str(k): v for k, v in _template_embeddings.items()},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                logger.info("[auto_tune] 임베딩 캐시 저장 완료")
            except Exception as e:
                logger.error(f"[auto_tune] 임베딩 생성 실패: {e}")

        _initialized = True
        return bool(_expanded_keywords or _template_embeddings)


def initialize_in_background() -> None:
    """서버 시작을 블록하지 않도록 백그라운드 스레드에서 초기화."""
    t = threading.Thread(target=initialize, daemon=True, name="emotion-auto-tune-init")
    t.start()


# ── 공개 API ─────────────────────────────────────────────────────────────────

def score_expanded(emotion: str, tmpl_idx: int) -> int:
    """
    GPT 확장 키워드 기반 점수(0 or 60).
    하드코딩 테이블(80-100)보다 낮은 점수를 부여.
    """
    if not _expanded_keywords:
        return 0
    emo = emotion.strip().lower()
    for kw in _expanded_keywords.get(tmpl_idx, []):
        kw_l = kw.strip().lower()
        if kw_l and (kw_l in emo or emo in kw_l):
            return 60
    return 0


def best_by_embedding(emotion: str, exclude_idxs: set[int] | None = None) -> int | None:
    """
    임베딩 cosine similarity로 가장 가까운 템플릿 인덱스 반환.
    유사도 임계값(0.25) 미만이면 None 반환.
    exclude_idxs: 이미 다른 감정에 배정된 인덱스는 제외.
    """
    if not _template_embeddings:
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=[emotion],
        )
        vec = resp.data[0].embedding
        best_idx, best_sim = -1, -1.0
        for i, tmpl_vec in _template_embeddings.items():
            if exclude_idxs and i in exclude_idxs:
                continue
            sim = _cosine(vec, tmpl_vec)
            if sim > best_sim:
                best_sim, best_idx = sim, i
        logger.debug(f"[auto_tune] embedding '{emotion}' → tmpl {best_idx} (sim={best_sim:.3f})")
        return best_idx if best_sim >= 0.25 else None
    except Exception as e:
        logger.warning(f"[auto_tune] 임베딩 API 실패 '{emotion}': {e}")
        return None


def is_ready() -> bool:
    return _initialized
