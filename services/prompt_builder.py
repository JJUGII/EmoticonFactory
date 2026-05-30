"""Build image-generation prompts from cut plan, theme, and character profile."""

from __future__ import annotations

from typing import Any, Sequence

from services.character_profile import CharacterProfile
from services.base_character_prompt import CANONICAL_BASE_POSE_LOCK_EN
from services.identity_lock import (
    critical_identity_lock_fragment,
    handcrafted_style_fragment,
    identity_profile_fragment,
    living_being_philosophy_fragment,
    pose_expression_strength_fragment,
    trait_locks_fragment,
)
from services.identity_profile_analyzer import IdentityProfile
from services.illustration_style import (
    character_art_texture_lock_fragment,
    clamp_style_intensity,
    illustration_texture_fragment,
)
from services.realistic_style import (
    realistic_character_lock_fragment,
    realistic_style_base_fragment,
    realistic_texture_fragment,
)

_KAKAO_EMOTION_BASE_KO = (
    "귀여운 한국 메신저 스티커 스타일, "
    "따뜻한 파스텔 팔레트, "
    "깔끔한 스티커 일러스트, "
    "부드럽고 표현력 있는 감정, "
    "작은 크기에서도 잘 보이게, "
    "카카오톡 이모티콘 상용 품질, "
    "동일한 캐릭터 정체성 유지, "
    "얼굴형·눈·털 무늬·실루엣 보존, "
    "단순한 배경, "
    "중앙 한 캐릭터, "
    "감정이 잘 드러나는 포즈, "
    "상업용 스티커 퀄리티"
)

# 하위 호환
_KAKAO_EMOTION_BASE_EN = _KAKAO_EMOTION_BASE_KO

_CHARACTER_ART_LOCK_KO = (
    "제공된 캐논 캐릭터 이미지를 그대로 사용해줘. "
    "캐릭터를 재디자인하지 마. "
    "일반 마스코트로 단순화하지 마. "
    "수채화 질감과 선 느낌을 유지해. "
    "바꿀 수 있는 것: 포즈, 표정, 소품, 제스처만."
)

_CHARACTER_ART_LOCK_EN = _CHARACTER_ART_LOCK_KO

_CRITICAL_POSE_VARIATION_KO = (
    "중요: 새 캐릭터 디자인이 아니라 포즈·표정 변형 작업이다. "
    "팩 전체에서 캐릭터 정체성은 절대 바꾸지 마."
)

_CRITICAL_POSE_VARIATION_EN = _CRITICAL_POSE_VARIATION_KO


class PromptBuilder:
    """Creates prompts with a shared character consistency block + pose staging."""

    _LAYOUT_GUIDE: dict[str, str] = {
        "square_full_body": (
            "Full-body centered in frame, feet visible inside 540×540, "
            "head size ~38–45% of canvas height."
        ),
        "face_closeup": (
            "Face-dominant framing: head fills most of canvas, shoulders barely visible; "
            "eyes and mouth are focal."
        ),
        "half_body": (
            "Waist-up framing, hands/paws readable, slightly looser margins than closeup."
        ),
        "lying_pose": (
            "Horizontal resting pose near lower third of canvas, body axis ~10–20° tilt, "
            "ground line implied."
        ),
        "reaction_burst": (
            "Impact/reaction framing: subtle radial emphasis or forward energy; "
            "keep readable negative space for prop effects."
        ),
    }

    @staticmethod
    def _kakao_style_base_fragment(art_style: str = "illustration") -> str:
        if str(art_style).strip().lower() == "realistic":
            return realistic_style_base_fragment()
        return f"[카카오 이모티콘 톤] {_KAKAO_EMOTION_BASE_KO}"

    @staticmethod
    def _theme_enrichment_fragment(item: dict[str, Any]) -> str:
        parts: list[str] = []
        a = str(item.get("_kakao_theme_moment_en") or "").strip()
        b = str(item.get("_kakao_phrase_context_en") or "").strip()
        c = str(item.get("_kakao_readability_en") or "").strip()
        if a:
            parts.append(f"[Chat pack context] {a}")
        if b:
            parts.append(f"[Cut staging] {b}")
        if c:
            parts.append(f"[Sticker readability] {c}")
        return (" ".join(parts) + " ") if parts else ""

    @staticmethod
    def _staging_effects_fragment(item: dict[str, Any]) -> str:
        blob = " ".join(
            str(item.get(k, ""))
            for k in (
                "emotion",
                "facial_expression",
                "body_pose",
                "action",
                "motion_hint",
                "prop",
                "risk_notes",
            )
        ).lower()
        hints: list[str] = []
        if any(x in blob for x in ("하트", "heart", "love", "심쿵", "뽀뽀", "쪽")):
            hints.append("optional tiny floating pastel hearts near the character (flat, not 3D)")
        if any(x in blob for x in ("blush", "볼", "부끄", "shy", "심쿵")):
            hints.append("soft cheek blush gradients (sticker-flat)")
        if any(x in blob for x in ("sparkle", "반짝", "별", "twinkle", "shine")):
            hints.append("small sparkles or star glints for emotion emphasis")
        if any(x in blob for x in ("땀", "sweat", "panic", "당황")):
            hints.append("cute cartoon sweat drops if it matches the emotion")
        if any(x in blob for x in ("번개", "lightning", "impact", "십자")):
            hints.append("tiny motion lines or cute impact symbols (keep low clutter)")
        if any(x in blob for x in ("z ", "잘자", "sleep", "쿨쿨")):
            hints.append("sleepy Z or tiny moon/dream glyphs if it fits the pose")
        if not hints:
            hints.append(
                "subtle symbolic cute accents only if they stay simple and do not crowd the frame"
            )
        return (
            "[Scene accents — keep background simple or transparent] "
            + "; ".join(hints)
            + " "
        )

    @staticmethod
    def _critical_identity_fragment(
        *,
        canonical_identity_mode: bool,
        canonical_sheet_mode: bool,
        character_art_direct_canonical: bool,
    ) -> str:
        if canonical_sheet_mode or canonical_identity_mode or character_art_direct_canonical:
            return f"[Identity contract] {_CRITICAL_POSE_VARIATION_EN} "
        return ""

    @staticmethod
    def _character_art_lock_fragment(
        reference_type: str | None, *, character_art_direct_canonical: bool
    ) -> str:
        if character_art_direct_canonical:
            return ""
        if str(reference_type or "").strip().lower() == "character_art":
            return f"[Character-art lock] {_CHARACTER_ART_LOCK_EN} "
        return ""

    def build_prompt(
        self,
        item: dict[str, Any],
        theme: str,
        series_name: str,
        profile: CharacterProfile,
        reference_description: str = "",
        regeneration_suffixes: Sequence[str] | None = None,
        *,
        no_ai_text: bool = True,
        reference_type: str | None = None,
        canonical_identity_mode: bool = False,
        canonical_sheet_mode: bool = False,
        character_art_direct_canonical: bool = False,
        series_pack_coherence: bool = True,
        style_intensity: float = 0.5,
        identity_profile: IdentityProfile | None = None,
        pose_variation_strength: float = 1.0,
        expression_strength: float = 1.0,
        force_identity_lock: bool = False,
        art_style: str = "illustration",
    ) -> str:
        """Compose a single-image prompt for one cut."""
        si = clamp_style_intensity(style_intensity)
        identity_locked = (
            force_identity_lock
            or canonical_identity_mode
            or canonical_sheet_mode
            or character_art_direct_canonical
        )
        canonical_pose_lock = ""
        if canonical_identity_mode and not canonical_sheet_mode:
            canonical_pose_lock = f"[Canonical base lock] {CANONICAL_BASE_POSE_LOCK_EN} "
        block = self._build_character_block(
            profile,
            no_ai_text=no_ai_text,
            canonical_identity_mode=canonical_identity_mode,
            canonical_sheet_mode=canonical_sheet_mode,
            character_art_direct_canonical=character_art_direct_canonical,
            style_intensity=si,
        )

        cut_id = item.get("id", "")
        text = item.get("text", "")
        emotion = item.get("emotion", "")
        facial = item.get("facial_expression", "")
        body_pose = item.get("body_pose", "")
        prop = str(item.get("prop", "none")).strip()
        action = item.get("action", "")
        motion = item.get("motion_hint", "")
        importance = item.get("importance", "")
        layout = str(item.get("layout_type", "square_full_body"))
        text_pos = str(item.get("text_position", "bottom"))
        risk = str(item.get("risk_notes", ""))

        if character_art_direct_canonical:
            ref = reference_description.strip() or (
                "제공된 캐논 캐릭터 이미지를 그대로 사용. 재디자인·마스코트 단순화 금지. "
                "원본 일러스트 질감·수채감·선 개성 유지. 벡터 마스코트로 평탄화 금지. "
                "포즈·표정·소품·제스처만 변경."
            )
        elif canonical_sheet_mode:
            ref = reference_description.strip() or (
                "캐논 캐릭터 시트를 디자인 바이블로 사용. 모든 컷은 시트와 동일 캐릭터. "
                "포즈·동작·소품·감정만 변경. 재디자인·글자 금지."
            )
        elif canonical_identity_mode:
            ref = reference_description.strip() or (
                "제공된 캐논 캐릭터 이미지를 이번 실행의 정체성 기준으로 사용: "
                "얼굴·눈·귀·털 무늬·선 두께·팔레트·일러스트 스타일 동일, "
                "컷마다 포즈·동작·소품·감정만 변경."
            )
        else:
            ref = reference_description.strip() or (
                "이번 실행의 참조 이미지와 동일한 한 마리(종·색·무늬·귀·눈·실루엣 유지). "
                "포즈·소품·프레이밍만 컷마다 변경."
            )

        layout_line = self._LAYOUT_GUIDE.get(
            layout,
            "layout_type 구도에 맞게 프레이밍하되 캐릭터가 어색하게 잘리지 않게.",
        )

        prop_block = ""
        if prop.lower() != "none":
            prop_block = (
                f"소품 우선: '{prop}' 을 스티커에서 잘 보이게, 플랫 색, 캐릭터와 같은 선 두께로. "
            )

        if no_ai_text:
            typography = (
                "글자 정책: 한글·영문·캡션·워터마크·로고·글자 형태 기호를 그리지 마. "
                "나중에 소프트웨어로 문구를 올릴 캡션 여백을 비워 둬."
            )
        elif text_pos == "none":
            typography = "문구: 이 컷은 캔버스에 문구 없음(text_position=none)."
        else:
            typography = (
                f"문구: 한글 '{text}' 를 정확히, 크고 굵게, 고대비, 흰 외곽선 스티커 캡션으로. "
                f"{text_pos} 안전 영역에 배치, 소품에 가리지 말 것."
            )

        _is_realistic = str(art_style).strip().lower() == "realistic"
        _texture_frag = (
            realistic_texture_fragment()
            if _is_realistic
            else illustration_texture_fragment(si)
        )
        _char_lock_frag = (
            realistic_character_lock_fragment(direct_canonical=character_art_direct_canonical)
            if _is_realistic
            else character_art_texture_lock_fragment(si, direct_canonical=character_art_direct_canonical)
        )
        scene = (
            f"{canonical_pose_lock}"
            f"{living_being_philosophy_fragment()}"
            f"{critical_identity_lock_fragment(enabled=identity_locked)}"
            f"{identity_profile_fragment(identity_profile)}"
            f"{trait_locks_fragment(identity_profile)}"
            f"{pose_expression_strength_fragment(pose_variation_strength, expression_strength)}"
            f"{handcrafted_style_fragment()}"
            f"{block} "
            f"{_texture_frag}"
            f"{_char_lock_frag}"
            f"{self._kakao_style_base_fragment(art_style)} "
            f"{self._theme_enrichment_fragment(item)}"
            f"{self._staging_effects_fragment(item)}"
            f"{self._critical_identity_fragment(canonical_identity_mode=canonical_identity_mode, canonical_sheet_mode=canonical_sheet_mode, character_art_direct_canonical=character_art_direct_canonical)}"
            f"{self._character_art_lock_fragment(reference_type, character_art_direct_canonical=character_art_direct_canonical)}"
            f"참조: {ref} "
            f"{self._reference_type_extra(reference_type, canonical_identity_mode, canonical_sheet_mode, character_art_direct_canonical)}"
            f"시리즈: {series_name}. 테마: {theme}. 컷 id {cut_id}. "
            f"[포즈 계획] emotion: {emotion}. facial_expression: {facial}. "
            f"body_pose: {body_pose}. action: {action}. motion_hint: {motion}. "
            f"layout_type ({layout}): {layout_line} "
            "[구도 필수] 캐릭터 주체는 캔버스 수평 정중앙 배치. "
            "좌우 여백 균등. 한쪽으로 편향되거나 잘리는 구도 금지. "
            "팔을 한쪽만 크게 뻗어 무게중심이 치우치는 비대칭 포즈 금지. "
            "완전한 등(뒷모습) 구도 금지 — 감정 전달을 위해 최소 3/4 정면 이상 유지. "
            f"text_position(여백 힌트): {text_pos}. story_importance: {importance}. "
            f"{prop_block}"
            f"{typography} "
            f"제작 메모 / risk_notes: {risk} "
            "큰 이모티콘 540×540. 모든 컷에서 동일한 대상 정체성 유지 — 새 캐릭터 디자인 금지."
        )
        if series_pack_coherence:
            scene += (
                " [시리즈 일관성] 16컷 팩은 동일 캐릭터 — 캐논 참조와 정확히 일치, 다른 마스코트로 드리프트 금지."
            )

        if regeneration_suffixes:
            suf = "; ".join(s.strip() for s in regeneration_suffixes if str(s).strip())
            if suf:
                scene = f"{scene} [Prompt fix] {suf}"

        return scene

    @staticmethod
    def _reference_type_extra(
        reference_type: str | None,
        canonical_identity_mode: bool,
        canonical_sheet_mode: bool,
        character_art_direct_canonical: bool = False,
    ) -> str:
        if character_art_direct_canonical:
            return (
                "완성 캐릭터 아트 직접 캐논 모드: 캐논 이미지 그대로, 재디자인·마스코트화 금지, "
                "원본 질감·수채·선 개성 유지, 포즈·표정·소품·제스처만 변경. "
                "추가 동물·글자 금지. 문구 오버레이 여백 확보. "
            )
        if canonical_sheet_mode:
            return (
                "캐논 시트 모드: 시트를 바이블로, 동일 무늬·눈·귀·실루엣·팔레트·선 두께. "
                "포즈·동작·소품·감정만 변경. 재디자인·추가 동물·글자 금지. "
            )
        if canonical_identity_mode:
            return (
                "캐논 캐릭터 모드: 재디자인·새 반려동물 생성 금지. 캐논 이미지 정체성 고정. "
                "얼굴·눈·귀·무늬·선·팔레트·표정 기준선 유지. 포즈·동작·소품·감정만 변경. "
                "추가 동물·배경·글자 금지. 문구 여백 확보. "
            )
        if not reference_type or str(reference_type).strip().lower() != "character_art":
            return ""
        return (
            "입력 분류: 기존 캐릭터 아트 — 참조 스타일 그대로, 재디자인 금지, "
            "이 컷에 지정된 포즈·동작·소품만 변경. "
        )

    def _build_character_block(
        self,
        profile: CharacterProfile,
        *,
        no_ai_text: bool,
        canonical_identity_mode: bool,
        canonical_sheet_mode: bool = False,
        character_art_direct_canonical: bool = False,
        style_intensity: float = 0.5,
    ) -> str:
        """Shared prefix: profile fields plus mandatory stylistic constraints."""
        design = ", ".join(profile.design_keywords)
        negative = ", ".join(profile.negative_keywords)
        rules = "; ".join(profile.consistency_rules)
        si = clamp_style_intensity(style_intensity)
        tex_note = ""
        if si >= 0.35:
            tex_note = (
                " Prefer painterly watercolor/storybook rendering over flat corporate vector mascot; "
                "slight natural asymmetry is welcome. "
            )
        elif si <= 0.15:
            tex_note = " Prefer clean Kakao vector sticker readability. "

        if character_art_direct_canonical:
            required = (
                "Warm, slightly exaggerated emoticon acting (cute and safe, not uncanny); "
                "follow the canonical character image as the sole visual truth (not a new design); "
                "preserve original illustration texture (e.g. watercolor or hand-drawn) when present; "
                "same species as profile; same sticker proportions for KakaoTalk big emoticon cuts; "
                "transparent or plain white background; "
                "no photorealistic fur unless the canonical already uses it; "
                "no complex background; no extra animals; no human."
            )
        elif canonical_sheet_mode:
            required = (
                "Warm, slightly exaggerated emoticon acting (cute and safe, not uncanny); "
                "follow the canonical turnaround character sheet exactly (not a new design); "
                "same species as profile; same sticker proportions language; "
                "cute KakaoTalk big emoticon sticker style; "
                "clean hand-drawn vector-like illustration; thick soft outline; flat colors; "
                "transparent or plain white background; "
                "no photorealistic fur; no complex background; no extra animals; no human."
            )
        elif canonical_identity_mode:
            required = (
                "따뜻하고 과장된 이모티콘 연기(귀엽고 안전하게); "
                "캐논 스티커 캐릭터를 그대로(새 디자인 금지); "
                "종·비율·선·색감 동일; 카카오톡 큰 이모티콘 스타일; "
                "투명 또는 흰 배경; 비실사; 추가 동물·사람 금지."
            )
        else:
            if str(getattr(profile, "species", "unknown")).strip().lower() == "unknown":
                required = (
                    "따뜻하고 과장된 이모티콘 연기; "
                    "첨부 참조와 동일한 대상(사람이면 사람 캐릭터, 동물이면 그 동물 캐릭터); "
                    "절대 사람을 동물로, 동물을 사람으로 바꾸지 마; "
                    "색·얼굴·특징·실루엣 유지; "
                    "카카오톡 스티커 스타일; 손그림 느낌; 투명 또는 흰 배경; "
                    "비실사; 복잡한 배경·추가 대상 금지."
                )
            else:
                required = (
                    "따뜻하고 과장된 이모티콘 연기; "
                    "첨부 참조와 동일한 대상(종·색·얼굴 무늬·귀·눈·실루엣 유지, 다른 종으로 바꾸지 마); "
                    "카카오톡 스티커 스타일; 손그림 느낌; 투명 또는 흰 배경; "
                    "비실사; 복잡한 배경·추가 동물·사람 금지."
                )
        if no_ai_text:
            required += " 글자·캡션 금지, Pillow 문구용 여백 확보."
        required += tex_note

        return (
            f"[캐릭터 일관성] {profile.species} — {profile.breed_style}. "
            f"주요 색/무늬: {profile.main_colors}. "
            f"얼굴: {profile.face_mask_color}. 눈: {profile.eye_color}. "
            f"귀: {profile.ear_shape}. "
            f"표정 범위: {profile.expression}. 성격: {profile.personality}. "
            f"디자인 키워드: {design}. 피할 것: {negative}. "
            f"규칙: {rules}. "
            f"필수 스타일: {required}"
        )
