"""Semi-realistic (Korean webtoon/manhwa) style prompts for emoticon generation.

'Realistic' in this context means Korean webtoon semi-realistic style:
natural skin/fur tones, soft shading, detailed eyes — NOT full photorealism.
Full photorealism is too detailed for small emoticon use and inconsistent across cuts.
"""

from __future__ import annotations

# ── 후보 생성용 핵심 프롬프트 ────────────────────────────────────────────

REALISTIC_CANDIDATE_CORE_KO = (
    "첨부된 이미지를 기반으로 한국 웹툰/manhwa 스타일의 세미-리얼리스틱 이모티콘 캐릭터로 변환해줘. "
    "자연스러운 피부톤 또는 털 색감, 부드러운 음영, 섬세한 눈 표현을 살리되 "
    "이모티콘 크기에서도 감정이 잘 전달되도록 가독성을 확보해줘. "
    "입력 이미지의 대상(사람이면 사람, 고양이면 고양이)을 그대로 유지해줘. "
    "얼굴 특징, 색감, 분위기는 바꾸지 말고 웹툰 세미-리얼 스타일로 변환만 해줘. "
    "배경은 흰색 또는 투명. 글자, 로고, 워터마크 없음. 중앙에 한 대상만. 1024×1024."
)

REALISTIC_CANDIDATE_CORE_EN = (
    "Convert the attached image into a semi-realistic Korean webtoon/manhwa style emoticon character. "
    "Preserve natural skin or fur tones, soft shading, and detailed eye expression while keeping "
    "emoticon readability at small sizes. "
    "Keep the same subject as the input (person stays person, cat stays cat). "
    "Stylize only — do not change species, face, colors, or mood. "
    "White or transparent background. No text, logos, or watermarks. One centered subject. 1024×1024."
)

REALISTIC_CANDIDATE_GUARD_KO = (
    "절대 다른 사람/동물로 바꾸지 마. "
    "완전한 사진 실사가 아닌 웹툰 세미-리얼 스타일이어야 해. "
    "이모티콘으로 사용 가능한 가독성 수준을 유지해."
)

# 후보별 스타일 힌트 (세미-리얼 계열 3종)
REALISTIC_CANDIDATE_STYLE_HINTS: dict[int, str] = {
    1: "깔끔한 한국 웹툰 펜선 + 플랫 셀 셰이딩, 선명한 윤곽",
    2: "부드러운 수채 느낌의 세미-리얼, 자연스러운 음영과 피부 질감",
    3: "현대 한국 만화풍 세미-리얼, 섬세한 눈빛과 표정 디테일 강조",
}

# ── 감정 컷 생성용 스타일 베이스 ─────────────────────────────────────────

REALISTIC_EMOTION_BASE_KO = (
    "한국 웹툰 세미-리얼리스틱 스타일, "
    "자연스러운 피부/털 톤과 부드러운 음영, "
    "섬세한 눈 표현과 하이라이트, "
    "이모티콘 가독성 확보(작은 크기에서도 감정 전달), "
    "카카오톡 큰 이모티콘 상용 품질, "
    "동일한 캐릭터 정체성 유지, "
    "얼굴형·눈·피부톤·특징 보존, "
    "단순한 배경, "
    "중앙 한 캐릭터, "
    "감정이 잘 드러나는 포즈"
)

# ── 일관성 잠금 — 리얼 스타일 전용 ──────────────────────────────────────

REALISTIC_CHARACTER_LOCK_KO = (
    "제공된 캐논 캐릭터 이미지를 그대로 사용해줘. "
    "캐릭터를 재디자인하지 마. 피부톤, 눈 색상, 얼굴 특징을 유지해. "
    "웹툰 세미-리얼 질감을 유지하고 만화 플랫 벡터로 단순화하지 마. "
    "바꿀 수 있는 것: 포즈, 표정, 소품, 제스처만."
)


def realistic_candidate_prompt_for_index(
    index_1based: int,
    *,
    species_hint: str = "",
    personality_hint: str = "",
) -> str:
    """Realistic-style candidate prompt (semi-realistic Korean webtoon)."""
    i = max(1, min(8, int(index_1based)))
    hint = REALISTIC_CANDIDATE_STYLE_HINTS.get(
        i, REALISTIC_CANDIDATE_STYLE_HINTS.get(3, "세미-리얼 웹툰 스타일")
    )
    parts = [
        REALISTIC_CANDIDATE_CORE_KO,
        f"스타일 힌트(이 후보): {hint}.",
        "대상 자체는 절대 바꾸지 말 것.",
    ]
    if species_hint.strip():
        sh = species_hint.strip().lower()
        if sh == "human":
            parts.append(
                "대상은 사람입니다. 반드시 사람 캐릭터(웹툰 세미-리얼 스타일)로 그려줘. "
                "고양이·강아지·동물로 절대 바꾸지 마. "
                "헤어 색상, 헤어스타일, 얼굴형을 최대한 유지해줘."
            )
        else:
            parts.append(f"추가 힌트(종/대상): {sh}.")
    if personality_hint.strip():
        parts.append(f"추가 힌트(분위기): {personality_hint.strip()}.")
    parts.append(REALISTIC_CANDIDATE_GUARD_KO)
    return " ".join(parts)


def realistic_texture_fragment() -> str:
    """[Realistic texture style] block for emoticon cut prompts."""
    return (
        "[Realistic texture style] "
        "Korean webtoon semi-realistic rendering: "
        "natural skin/fur tones, soft gradient shading, detailed eyes with highlights, "
        "clean crisp outlines, no flat vector fills, no cartoon cel simplification, "
        "emoticon-readable detail level. "
    )


def realistic_character_lock_fragment(*, direct_canonical: bool) -> str:
    """Realistic style character lock for canonical reference."""
    if not direct_canonical:
        return ""
    return f"[Realistic character lock] {REALISTIC_CHARACTER_LOCK_KO} "


def realistic_style_base_fragment() -> str:
    """Drop-in replacement for illustration _kakao_style_base_fragment() in realistic mode."""
    return f"[웹툰 세미-리얼 이모티콘 톤] {REALISTIC_EMOTION_BASE_KO}"
