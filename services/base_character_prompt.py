"""Base character candidate prompts — simple Korean, same subject, light style variation."""

from __future__ import annotations

# 후보 1차 생성 공통 본문 (한국어 우선)
BASE_CANDIDATE_CORE_KO = (
    "첨부된 이미지를 기반으로 카카오톡 이모티콘처럼 귀엽고 따뜻한 캐릭터 이미지로 변환해줘. "
    "입력 이미지의 대상이 고양이면 고양이로, 강아지면 강아지로, 사람이면 사람으로 유지해줘. "
    "종류와 얼굴 특징, 색감, 분위기는 바꾸지 말고 캐릭터화만 해줘. "
    "배경은 흰색 또는 투명 배경. "
    "글자, 로고, 워터마크는 넣지 마. "
    "중앙에 한 대상만 크게 배치해줘. "
    "사이즈는 1024x1024."
)

# 텍스트-only 폴백 시 보조 (영문)
BASE_CANDIDATE_CORE_EN = (
    "Turn the attached image into a cute warm Kakao-style emoticon character. "
    "Keep the same subject species and identity (cat stays cat, dog stays dog, person stays person). "
    "Stylize only — do not change species, face, colors, or mood. "
    "White or transparent background. No text, logos, or watermarks. "
    "One subject centered. 1024x1024."
)

BASE_CANDIDATE_GUARD_KO = (
    "절대 다른 동물이나 다른 사람으로 바꾸지 마. "
    "입력 이미지의 대상과 같은 존재로 보여야 해."
)

BASE_CANDIDATE_GUARD_EN = (
    "Never change to a different animal or person. "
    "The subject must remain the same entity as the input image."
)

BASE_CANDIDATE_STYLE_HINTS: dict[int, str] = {
    1: "부드러운 수채화 감성",
    2: "깔끔한 손그림 이모티콘 감성",
    3: "동화책 같은 따뜻한 일러스트 감성",
}

# mock 시각 차별용 (프롬프트에는 스타일 힌트만 사용)
BASE_CANDIDATE_VARIATION_SEEDS: dict[int, int] = {
    1: 101,
    2: 202,
    3: 303,
}

CANONICAL_BASE_POLICY_KO = (
    "사용자가 선택한 베이스 캐릭터를 16컷 이모티콘의 절대 기준으로 고정"
)

CANONICAL_BASE_POSE_LOCK_KO = (
    "중요: 새 캐릭터 디자인이 아니라 포즈·표정 변형 작업이다. "
    "선택된 베이스 캐릭터를 그대로 사용한다. "
    "종류, 색감, 얼굴형, 눈 모양, 털/무늬 패턴은 바꾸지 말고 "
    "포즈, 표정, 제스처, 소품만 바꿔라."
)

# 하위 호환
CANONICAL_BASE_POSE_LOCK_EN = CANONICAL_BASE_POSE_LOCK_KO
BASE_CHARACTER_CORE_PROMPT = BASE_CANDIDATE_CORE_KO


def base_candidate_prompt_for_index(
    index_1based: int,
    *,
    species_hint: str = "",
    personality_hint: str = "",
    include_english_fallback: bool = False,
    art_style: str = "illustration",
) -> str:
    """Same core prompt + small style hint + guard (후보별 차이는 스타일만).

    art_style: "illustration" (기본, 치비·수채화) | "realistic" (웹툰 세미-리얼)
    realistic 스타일은 realistic_style 모듈에서 빌드함.
    """
    # realistic 스타일은 전용 빌더로 위임
    if str(art_style).strip().lower() == "realistic":
        from services.realistic_style import realistic_candidate_prompt_for_index
        return realistic_candidate_prompt_for_index(
            index_1based,
            species_hint=species_hint,
            personality_hint=personality_hint,
        )

    i = max(1, min(8, int(index_1based)))
    hint = BASE_CANDIDATE_STYLE_HINTS.get(
        i, BASE_CANDIDATE_STYLE_HINTS.get(3, "귀여운 이모티콘 감성")
    )
    parts = [
        BASE_CANDIDATE_CORE_KO,
        f"스타일만 이 후보에 맞게 살짝 조정: {hint}.",
        "대상 자체는 절대 바꾸지 말 것.",
    ]
    if species_hint.strip():
        sh = species_hint.strip().lower()
        if sh == "human":
            parts.append(
                "대상은 사람입니다. 반드시 사람 캐릭터(치비·큐티 스타일)로 그려줘. "
                "고양이·강아지·동물로 절대 바꾸지 마. "
                "헤어 색상, 헤어스타일, 얼굴형을 최대한 유지해줘."
            )
        else:
            parts.append(f"추가 힌트(종/대상): {sh}.")
    if personality_hint.strip():
        parts.append(f"추가 힌트(분위기): {personality_hint.strip()}.")
    parts.append(BASE_CANDIDATE_GUARD_KO)
    if include_english_fallback:
        parts.extend([BASE_CANDIDATE_CORE_EN, BASE_CANDIDATE_GUARD_EN])
    return " ".join(parts)
