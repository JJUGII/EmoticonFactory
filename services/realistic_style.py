"""Photo-realistic digital art style prompts for emoticon generation.

'Realistic' in this context means high-quality CG rendering / digital painting level realism:
real fur/skin texture, detailed lighting and shadows, iris detail in eyes.
NOT a cartoon, webtoon, or flat vector style.
"""

from __future__ import annotations

# ── 후보 생성용 핵심 프롬프트 ────────────────────────────────────────────

REALISTIC_CANDIDATE_CORE_KO = (
    "첨부된 사진 속 인물/동물을 실사에 최대한 가깝게 캐릭터화해줘. "
    "사진 속 얼굴 생김새(눈 모양, 눈썹, 코, 입술, 헤어스타일, 헤어 색상, 피부톤)를 그대로 유지하는 것이 최우선이야. "
    "예쁘게 미화하거나 이상화하지 말고, 실제 사진 속 인물과 닮아 보이는 것이 핵심이야. "
    "자연스러운 피부 질감, 머리카락 결, 눈의 홍채와 반사광을 살려줘. "
    "만화·플랫 벡터·과도한 미형화 금지. 실제 사진에서 보이는 특징을 그대로 캐릭터화해줘. "
    "배경은 흰색 또는 투명. 글자, 로고, 워터마크 없음. 중앙에 한 대상만. 1024×1024."
)

REALISTIC_CANDIDATE_CORE_EN = (
    "Convert the attached photo into a realistic-style character that closely resembles the actual person/animal in the photo. "
    "The top priority is preserving the actual face features: eye shape, nose, lips, hairstyle, hair color, and skin tone — exactly as they appear in the photo. "
    "Do NOT idealize or beautify beyond what is shown. It must look like the same person/animal. "
    "Apply natural skin texture, hair strand detail, iris and specular highlights in eyes. "
    "No cartoon, flat vector, or over-stylized look. Faithful photo-to-character conversion. "
    "White or transparent background. No text, logos, or watermarks. One centered subject. 1024×1024."
)

REALISTIC_CANDIDATE_GUARD_KO = (
    "절대 다른 사람/동물로 바꾸지 마. "
    "실제 사진 속 인물과 닮아 보여야 해 — 미화나 이상화 금지. "
    "만화·웹툰·플랫 스타일로 단순화하지 마. "
    "이모티콘으로 사용 가능한 가독성 수준을 유지해."
)

# 후보별 스타일 힌트 (실사풍 계열)
REALISTIC_CANDIDATE_STYLE_HINTS: dict[int, str] = {
    1: "실제 사진과 최대한 닮게, 자연광 조명, 자연스러운 피부·머리카락 질감",
    2: "사진 속 인물의 특징을 충실히 재현, 눈의 홍채·반사광 디테일 강조",
    3: "부드러운 자연광 조명의 실사풍, 피부 톤과 헤어 색상을 사진 그대로 유지",
}

# ── 감정 컷 생성용 스타일 베이스 ─────────────────────────────────────────

REALISTIC_EMOTION_BASE_KO = (
    "고품질 실사풍 디지털 아트 스타일, "
    "자연스러운 피부/털 질감과 섬세한 빛·그림자, "
    "눈의 반사광과 홍채 디테일, "
    "이모티콘 가독성 확보(작은 크기에서도 감정 전달), "
    "카카오톡 큰 이모티콘 상용 품질, "
    "동일한 캐릭터 정체성 유지, "
    "얼굴형·눈·피부톤·특징 보존, "
    "단순한 배경, "
    "중앙 한 캐릭터, "
    "감정이 잘 드러나는 포즈"
)

# ── 일관성 잠금 — 실사 스타일 전용 ──────────────────────────────────────

REALISTIC_CHARACTER_LOCK_KO = (
    "제공된 캐논 캐릭터 이미지를 그대로 사용해줘. "
    "캐릭터를 재디자인하지 마. 피부톤, 눈 색상, 얼굴 특징을 유지해. "
    "고품질 실사풍 CG 렌더링 질감을 유지하고 만화·플랫 벡터로 단순화하지 마. "
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
    if not species_hint.strip() or species_hint.strip().lower() == "unknown":
        parts.append(
            "이미지를 직접 보고 대상이 사람인지 동물인지 판단해줘. "
            "사람이면 반드시 사람 캐릭터(웹툰 세미-리얼 스타일)로, "
            "동물이면 해당 동물 캐릭터로 그려줘. "
            "절대 사람을 동물로, 동물을 사람으로 바꾸지 마."
        )
    if species_hint.strip() and species_hint.strip().lower() != "unknown":
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
        "High-quality photo-realistic digital art rendering: "
        "natural skin/fur texture, detailed lighting and shadows, iris detail and specular highlights in eyes, "
        "CG rendering or digital painting level realism, no flat vector fills, no cartoon simplification, "
        "emoticon-readable detail level. "
    )


def realistic_character_lock_fragment(*, direct_canonical: bool) -> str:
    """Realistic style character lock for canonical reference."""
    if not direct_canonical:
        return ""
    return f"[Realistic character lock] {REALISTIC_CHARACTER_LOCK_KO} "


def realistic_style_base_fragment() -> str:
    """Drop-in replacement for illustration _kakao_style_base_fragment() in realistic mode."""
    return f"[실사풍 디지털 아트 이모티콘 톤] {REALISTIC_EMOTION_BASE_KO}"
