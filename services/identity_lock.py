"""Prompt fragments for v0.7 universal identity lock (pose-only variation)."""

from __future__ import annotations

from services.identity_profile_analyzer import IdentityProfile


CRITICAL_IDENTITY_LOCK_KO = (
    "동일한 캐릭터이다. 재디자인 금지. 종 특성·얼굴 구조·눈 모양·팔레트 변경 금지. "
    "바꿀 수 있는 것: 포즈, 감정, 손 제스처, 소품, 동작만. 정체성은 그대로 유지."
)

LIVING_BEING_PHILOSOPHY_KO = (
    "이 생명체를 정체성을 바꾸지 않고 귀여운 카카오 이모티콘 캐릭터로 변환해줘. "
    "유지: 실루엣, 얼굴, 눈, 털/머리 무늬, 분위기, 알아볼 수 있는 특징. "
    "피할 것: 일반 마스코트 재디자인, 임의 색 변경, 종 변형, 기업용 플랫 아이콘."
)

HANDCRAFTED_ANTI_FLAT_KO = (
    "손으로 그린 동화책 일러스트, 부드러운 수채 질감, 은은한 붓 터치, "
    "따뜻한 손맛, 기업 벡터 마스코트 아님, 플랫 로고 캐릭터 아님, 흔한 AI 스티커 아님"
)

# 하위 호환
CRITICAL_IDENTITY_LOCK_EN = CRITICAL_IDENTITY_LOCK_KO
LIVING_BEING_PHILOSOPHY_EN = LIVING_BEING_PHILOSOPHY_KO
HANDCRAFTED_ANTI_FLAT_EN = HANDCRAFTED_ANTI_FLAT_KO


def clamp_strength(value: float, *, default: float = 1.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = default
    return max(0.0, min(1.0, v))


def critical_identity_lock_fragment(*, enabled: bool = True) -> str:
    if not enabled:
        return ""
    return f"[정체성 고정] {CRITICAL_IDENTITY_LOCK_KO} "


def living_being_philosophy_fragment() -> str:
    return f"[생명체 정체성] {LIVING_BEING_PHILOSOPHY_KO} "


def handcrafted_style_fragment() -> str:
    return f"[손그림 일러스트] {HANDCRAFTED_ANTI_FLAT_KO}. "


def trait_locks_fragment(profile: IdentityProfile | None) -> str:
    if profile is None:
        return ""
    tl = profile.trait_locks
    parts: list[str] = []
    if tl.species_trait_lock:
        parts.append("[종 특성 고정] " + "; ".join(tl.species_trait_lock))
    if tl.facial_landmark_lock:
        parts.append("[얼굴 랜드마크 고정] " + "; ".join(tl.facial_landmark_lock))
    if tl.fur_pattern_lock:
        parts.append("[털/무늬 고정] " + "; ".join(tl.fur_pattern_lock))
    if tl.hairstyle_lock:
        parts.append("[헤어/털 스타일 고정] " + "; ".join(tl.hairstyle_lock))
    if tl.eye_geometry_lock:
        parts.append("[눈 형태 고정] " + "; ".join(tl.eye_geometry_lock))
    if not parts:
        return ""
    return " ".join(parts) + " "


def identity_profile_fragment(profile: IdentityProfile | None) -> str:
    if profile is None:
        return ""
    dist = ", ".join(profile.distinctive_features[:6])
    pal = ", ".join(profile.primary_palette[:5])
    return (
        f"[정체성 프로필] entity_type={profile.entity_type}; species={profile.species}; "
        f"face_shape={profile.face_shape}; eye_shape={profile.eye_shape}; "
        f"eye_color={profile.eye_color}; mood={profile.mood}; "
        f"silhouette={profile.silhouette}; hair_or_fur={profile.hair_or_fur_pattern}; "
        f"palette=[{pal}]; distinctive=[{dist}]. "
    )


def pose_expression_strength_fragment(
    pose_variation_strength: float,
    expression_strength: float,
) -> str:
    ps = clamp_strength(pose_variation_strength)
    es = clamp_strength(expression_strength)
    if ps <= 0.08 and es <= 0.08:
        return ""
    pose_note = (
        "포즈는 아주 미세하게, 캐논 구도에 가깝게"
        if ps < 0.35
        else (
            "정체성은 고정한 채 중간 정도 포즈 변화"
            if ps < 0.72
            else "동작은 더 크게 가능하나 얼굴·종 특성은 동일"
        )
    )
    expr_note = (
        "표정 변화 최소"
        if es < 0.35
        else (
            "눈 형태·얼굴 구조는 유지한 채 감정이 잘 읽히게"
            if es < 0.72
            else "표현력 있는 연기, 눈 형태·얼굴은 동일"
        )
    )
    return (
        f"[변화 강도] pose={ps:.2f} ({pose_note}); "
        f"expression={es:.2f} ({expr_note}). "
    )
