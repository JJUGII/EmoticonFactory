"""Emotion → pose category catalog (engine-neutral planning data)."""

from __future__ import annotations

from typing import Any

# emotion category → pose_type ids (rotated per cut)
EMOTION_POSE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "happy": (
        "jumping_pose",
        "waving_pose",
        "leaning_pose",
        "sparkle_reaction",
        "arms_up_celebration",
        "bouncy_step",
    ),
    "sad": (
        "sitting_pose",
        "curled_pose",
        "side_glance",
        "slumped_shoulders",
        "hugging_knees",
        "rainy_mood",
    ),
    "angry": (
        "crossed_arms",
        "exaggerated_stomp",
        "tilted_forward",
        "puffed_cheeks_lean",
        "pointing_accuse",
        "steam_reaction",
    ),
    "love": (
        "hand_heart",
        "cheek_pose",
        "shy_pose",
        "hug_self",
        "blush_lean",
        "heart_gesture",
    ),
    "surprise": (
        "jump_back",
        "hands_on_cheeks",
        "wide_eyes_lean_back",
        "startled_pose",
        "question_tilt",
    ),
    "shy": (
        "shy_pose",
        "peek_pose",
        "finger_fidget",
        "cheek_cover",
    ),
    "tired": (
        "yawn_stretch",
        "droopy_slouch",
        "lying_half",
    ),
    "neutral": (
        "casual_wave",
        "thinking_tilt",
        "ok_sign",
        "shrug_pose",
        "listening_pose",
    ),
}

# Korean / English emotion hints → category
_EMOTION_HINTS: tuple[tuple[str, str], ...] = (
    ("happy", "기쁨"),
    ("happy", "좋아"),
    ("happy", "행복"),
    ("happy", "신남"),
    ("happy", "happy"),
    ("happy", "joy"),
    ("sad", "슬픔"),
    ("sad", "서운"),
    ("sad", "우울"),
    ("sad", "눈물"),
    ("sad", "sad"),
    ("sad", "애틋"),
    ("angry", "화"),
    ("angry", "삐"),
    ("angry", "질투"),
    ("angry", "분노"),
    ("angry", "angry"),
    ("love", "사랑"),
    ("love", "애정"),
    ("love", "심쿵"),
    ("love", "love"),
    ("love", "보고싶"),
    ("surprise", "놀람"),
    ("surprise", "당황"),
    ("surprise", "shock"),
    ("surprise", "surprise"),
    ("shy", "부끄"),
    ("shy", "shy"),
    ("tired", "피곤"),
    ("tired", "졸"),
    ("tired", "sleep"),
    ("tired", "잘자"),
)


def classify_emotion_category(*parts: str) -> str:
    blob = " ".join(p for p in parts if p).lower()
    for cat, hint in _EMOTION_HINTS:
        if hint in blob:
            return cat
    if any(x in blob for x in ("웃", "smile", "grin", "ㅋ")):
        return "happy"
    if any(x in blob for x in ("울", "cry", "tear")):
        return "sad"
    return "neutral"


POSE_CATALOG: dict[str, dict[str, str]] = {
    "jumping_pose": {
        "body_direction": "forward_dynamic",
        "hand_action": "arms raised mid-jump",
        "accessory_action": "optional motion lines at feet",
        "body_language": "energetic jump, both feet off ground feel",
        "camera_angle": "slight low angle",
    },
    "waving_pose": {
        "body_direction": "three_quarter_turn",
        "hand_action": "one hand waving high",
        "accessory_action": "none",
        "body_language": "friendly wave toward viewer",
        "camera_angle": "eye level",
    },
    "leaning_pose": {
        "body_direction": "leaning_into_frame",
        "hand_action": "hands on hips or one hand on cheek",
        "accessory_action": "none",
        "body_language": "playful lean, weight on one leg",
        "camera_angle": "dynamic diagonal",
    },
    "sparkle_reaction": {
        "body_direction": "forward",
        "hand_action": "clasped hands or sparkle gesture near face",
        "accessory_action": "small sparkles around head",
        "body_language": "delighted sparkle reaction",
        "camera_angle": "medium close",
    },
    "arms_up_celebration": {
        "body_direction": "forward",
        "hand_action": "both arms up victory pose",
        "accessory_action": "none",
        "body_language": "celebration cheer",
        "camera_angle": "medium shot",
    },
    "bouncy_step": {
        "body_direction": "side_three_quarter",
        "hand_action": "small bounce with bent knees",
        "accessory_action": "none",
        "body_language": "light bouncy step",
        "camera_angle": "medium shot",
    },
    "sitting_pose": {
        "body_direction": "side_seated",
        "hand_action": "hands on lap or hugging knees",
        "accessory_action": "none",
        "body_language": "quiet sitting, subdued posture",
        "camera_angle": "medium shot side",
    },
    "curled_pose": {
        "body_direction": "curled_inward",
        "hand_action": "arms wrapped around body",
        "accessory_action": "none",
        "body_language": "small curled defensive posture",
        "camera_angle": "medium close",
    },
    "side_glance": {
        "body_direction": "profile_three_quarter",
        "hand_action": "chin on hand, looking away",
        "accessory_action": "none",
        "body_language": "melancholic side glance",
        "camera_angle": "side view",
    },
    "slumped_shoulders": {
        "body_direction": "forward_slump",
        "hand_action": "arms hanging low",
        "accessory_action": "none",
        "body_language": "drooping shoulders, low energy",
        "camera_angle": "upper body",
    },
    "hugging_knees": {
        "body_direction": "seated_front",
        "hand_action": "hugging knees to chest",
        "accessory_action": "none",
        "body_language": "comfort-seeking hug pose",
        "camera_angle": "medium shot",
    },
    "rainy_mood": {
        "body_direction": "slight_tilt",
        "hand_action": "hand near face",
        "accessory_action": "tiny rain drop symbols",
        "body_language": "wistful rainy mood",
        "camera_angle": "medium close",
    },
    "crossed_arms": {
        "body_direction": "forward_assertive",
        "hand_action": "arms crossed firmly",
        "accessory_action": "none",
        "body_language": "annoyed crossed arms",
        "camera_angle": "upper body",
    },
    "exaggerated_stomp": {
        "body_direction": "forward",
        "hand_action": "fists on hips or stomping foot",
        "accessory_action": "impact puff at foot",
        "body_language": "exaggerated angry stomp",
        "camera_angle": "dynamic low angle",
    },
    "tilted_forward": {
        "body_direction": "leaning_forward_aggressive",
        "hand_action": "pointing or clenched fists",
        "accessory_action": "none",
        "body_language": "confrontational lean-in",
        "camera_angle": "dynamic angle",
    },
    "puffed_cheeks_lean": {
        "body_direction": "forward",
        "hand_action": "hands on puffed cheeks",
        "accessory_action": "none",
        "body_language": "pouty angry cheeks",
        "camera_angle": "closeup",
    },
    "pointing_accuse": {
        "body_direction": "three_quarter",
        "hand_action": "pointing finger forward",
        "accessory_action": "none",
        "body_language": "accusatory point",
        "camera_angle": "medium shot",
    },
    "steam_reaction": {
        "body_direction": "forward",
        "hand_action": "balled fists trembling",
        "accessory_action": "steam puff symbols",
        "body_language": "comic anger steam",
        "camera_angle": "upper body",
    },
    "hand_heart": {
        "body_direction": "forward",
        "hand_action": "finger heart gesture",
        "accessory_action": "tiny hearts",
        "body_language": "cute finger heart",
        "camera_angle": "upper body",
    },
    "cheek_pose": {
        "body_direction": "head_tilt",
        "hand_action": "hands on cheeks",
        "accessory_action": "blush marks",
        "body_language": "sweet cheek squish pose",
        "camera_angle": "closeup",
    },
    "shy_pose": {
        "body_direction": "slight_turn_away",
        "hand_action": "fingers touching, shoulders inward",
        "accessory_action": "none",
        "body_language": "shy inward shoulders",
        "camera_angle": "three_quarter",
    },
    "hug_self": {
        "body_direction": "forward",
        "hand_action": "arms hugging self",
        "accessory_action": "none",
        "body_language": "self-hug warmth",
        "camera_angle": "upper body",
    },
    "blush_lean": {
        "body_direction": "leaning_back_shy",
        "hand_action": "hands behind back or fidget",
        "accessory_action": "blush",
        "body_language": "bashful lean away",
        "camera_angle": "medium close",
    },
    "heart_gesture": {
        "body_direction": "forward",
        "hand_action": "hands forming heart shape",
        "accessory_action": "floating hearts",
        "body_language": "presenting heart gesture",
        "camera_angle": "medium shot",
    },
    "jump_back": {
        "body_direction": "recoiling_backward",
        "hand_action": "hands up defensively",
        "accessory_action": "shock lines",
        "body_language": "startled jump back",
        "camera_angle": "dynamic angle",
    },
    "hands_on_cheeks": {
        "body_direction": "forward",
        "hand_action": "both palms on cheeks",
        "accessory_action": "none",
        "body_language": "classic surprised hands-on-face",
        "camera_angle": "closeup",
    },
    "wide_eyes_lean_back": {
        "body_direction": "leaning_back",
        "hand_action": "hands raised near face",
        "accessory_action": "none",
        "body_language": "wide-eyed lean back shock",
        "camera_angle": "medium close",
    },
    "startled_pose": {
        "body_direction": "jolted",
        "hand_action": "flailing small motion",
        "accessory_action": "impact stars",
        "body_language": "startled jolt",
        "camera_angle": "dynamic_angle",
    },
    "question_tilt": {
        "body_direction": "head_tilt",
        "hand_action": "finger on chin",
        "accessory_action": "question mark glyph",
        "body_language": "curious head tilt",
        "camera_angle": "upper body",
    },
    "peek_pose": {
        "body_direction": "peeking_from_side",
        "hand_action": "hands on edge peeking",
        "accessory_action": "none",
        "body_language": "peek from behind frame edge",
        "camera_angle": "side_view",
    },
    "finger_fidget": {
        "body_direction": "inward",
        "hand_action": "fidgeting fingers together",
        "accessory_action": "none",
        "body_language": "nervous finger fidget",
        "camera_angle": "upper body",
    },
    "cheek_cover": {
        "body_direction": "partial_hide",
        "hand_action": "one hand covering cheek",
        "accessory_action": "none",
        "body_language": "hide shy face",
        "camera_angle": "closeup",
    },
    "yawn_stretch": {
        "body_direction": "stretching_up",
        "hand_action": "arms stretch yawn",
        "accessory_action": "zzz optional",
        "body_language": "sleepy yawn stretch",
        "camera_angle": "medium shot",
    },
    "droopy_slouch": {
        "body_direction": "slouch",
        "hand_action": "rubbing eye or droopy arms",
        "accessory_action": "none",
        "body_language": "exhausted slouch",
        "camera_angle": "upper body",
    },
    "lying_half": {
        "body_direction": "horizontal_rest",
        "hand_action": "pillow hug or arm under head",
        "accessory_action": "none",
        "body_language": "lying down tired",
        "camera_angle": "medium shot low",
    },
    "casual_wave": {
        "body_direction": "three_quarter",
        "hand_action": "casual small wave",
        "accessory_action": "none",
        "body_language": "relaxed greeting wave",
        "camera_angle": "upper body",
    },
    "thinking_tilt": {
        "body_direction": "tilted",
        "hand_action": "chin thinking pose",
        "accessory_action": "none",
        "body_language": "thinking head tilt",
        "camera_angle": "medium close",
    },
    "ok_sign": {
        "body_direction": "forward",
        "hand_action": "ok sign hand gesture",
        "accessory_action": "none",
        "body_language": "confident ok sign",
        "camera_angle": "upper body",
    },
    "shrug_pose": {
        "body_direction": "forward",
        "hand_action": "shoulders up shrug",
        "accessory_action": "none",
        "body_language": "playful shrug",
        "camera_angle": "upper body",
    },
    "listening_pose": {
        "body_direction": "slight_turn",
        "hand_action": "hand cupped near ear",
        "accessory_action": "none",
        "body_language": "listening attentively",
        "camera_angle": "three_quarter",
    },
}


def pose_detail(pose_type: str) -> dict[str, str]:
    return dict(POSE_CATALOG.get(pose_type, POSE_CATALOG["casual_wave"]))


def humanize_hand_action(action: str, *, is_human: bool, is_pet: bool) -> str:
    if is_human:
        return (
            action.replace("paw", "hand")
            .replace("Paw", "hand")
            .replace("front legs", "arms")
        )
    if is_pet:
        return action.replace("hand", "paw").replace("finger", "paw")
    return action


def get_pose_types_for_category(category: str) -> tuple[str, ...]:
    return EMOTION_POSE_CATEGORIES.get(category, EMOTION_POSE_CATEGORIES["neutral"])
