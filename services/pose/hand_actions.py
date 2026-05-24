"""Hand / arm action layer — primary emoticon body language (Kakao-style)."""

from __future__ import annotations

from dataclasses import dataclass

# emotion category → hand action ids (rotated per cut)
EMOTION_HAND_ACTIONS: dict[str, tuple[str, ...]] = {
    "happy": (
        "waving",
        "both_hands_up",
        "finger_heart",
        "clapping",
        "open_palms_cheer",
        "thumbs_up",
    ),
    "love": (
        "cheek_pose",
        "hand_heart",
        "shy_cover_mouth",
        "hug_gesture",
        "two_hand_cheek_squish",
        "offering_heart",
    ),
    "sad": (
        "sleeve_pull",
        "hugging_pillow",
        "face_cover",
        "wiping_tear",
        "droopy_arm_hang",
        "knees_hug",
    ),
    "angry": (
        "crossed_arms",
        "fist_pose",
        "pointing",
        "hands_on_hips",
        "trembling_fist",
        "arm_swing",
    ),
    "awkward": (
        "finger_touch",
        "scratching_head",
        "tiny_wave",
        "nervous_hand_clasp",
        "peek_hand_wave",
        "index_fingers_touch",
    ),
    "surprise": (
        "hands_on_cheeks",
        "hands_up_shock",
        "open_palms_out",
    ),
    "shy": (
        "finger_touch",
        "shy_cover_mouth",
        "cheek_pose",
        "nervous_hand_clasp",
    ),
    "tired": (
        "rubbing_eye",
        "yawn_hand_cover",
        "droopy_arm_hang",
    ),
    "neutral": (
        "tiny_wave",
        "ok_sign",
        "thinking_chin",
        "casual_hand_rest",
    ),
}

# pose_type → preferred hand action when aligned
_POSE_HAND_ALIGN: dict[str, str] = {
    "crossed_arms": "crossed_arms",
    "hand_heart": "hand_heart",
    "cheek_pose": "cheek_pose",
    "waving_pose": "waving",
    "shy_pose": "shy_cover_mouth",
    "pointing_accuse": "pointing",
    "finger_heart": "finger_heart",
    "hugging_knees": "knees_hug",
    "hug_self": "hug_gesture",
}


@dataclass
class HandActionSpec:
    action_id: str
    label: str
    description: str
    body_language: str
    arm_pose: str
    hand_visibility: str  # required | both | single
    openai_block: str
    comfyui_positive: str
    framing_boost: str  # upper_body | medium_shot | none


_HAND_CATALOG: dict[str, dict[str, str]] = {
    "waving": {
        "label": "waving",
        "description": "one hand waving clearly toward viewer",
        "body_language": "friendly active wave, arm lifted high",
        "arm_pose": "raised arm, open palm wave",
        "hand_visibility": "single",
        "openai_block": "Show a clear waving hand with open palm; arm fully visible.",
        "comfyui_positive": "waving hand, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "upper_body",
    },
    "both_hands_up": {
        "label": "both_hands_up",
        "description": "both hands raised in celebration",
        "body_language": "cheerful both arms up",
        "arm_pose": "both arms lifted above shoulders",
        "hand_visibility": "both",
        "openai_block": "Both hands raised high; full arms visible, celebratory gesture.",
        "comfyui_positive": "both hands up, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "upper_body",
    },
    "finger_heart": {
        "label": "finger_heart",
        "description": "finger heart gesture at chest or cheek height",
        "body_language": "cute finger heart, affectionate gesture",
        "arm_pose": "hands forming small heart near face",
        "hand_visibility": "both",
        "openai_block": "Clear finger-heart with both hands visible near face or chest.",
        "comfyui_positive": "finger heart gesture, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "clapping": {
        "label": "clapping",
        "description": "hands clapping in front of chest",
        "body_language": "joyful clapping motion",
        "arm_pose": "hands meeting mid-clap",
        "hand_visibility": "both",
        "openai_block": "Hands clapping in front of torso; both palms visible.",
        "comfyui_positive": "clapping hands, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "upper_body",
    },
    "open_palms_cheer": {
        "label": "open_palms_cheer",
        "description": "open palms forward cheer",
        "body_language": "open palms excitement",
        "arm_pose": "both hands forward open",
        "hand_visibility": "both",
        "openai_block": "Open palms facing viewer; arms bent at elbow, hands large in frame.",
        "comfyui_positive": "open palms, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "thumbs_up": {
        "label": "thumbs_up",
        "description": "thumb up gesture",
        "body_language": "confident thumbs up",
        "arm_pose": "one thumb up, other hand relaxed",
        "hand_visibility": "single",
        "openai_block": "Clear thumbs-up; hand and forearm visible.",
        "comfyui_positive": "thumbs up, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "cheek_pose": {
        "label": "cheek_pose",
        "description": "hands pressing or framing cheeks",
        "body_language": "sweet cheek squish with both hands",
        "arm_pose": "palms on cheeks",
        "hand_visibility": "both",
        "openai_block": "Both hands on cheeks; fingers and palms clearly drawn.",
        "comfyui_positive": "hands on cheeks, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "hand_heart": {
        "label": "hand_heart",
        "description": "hands forming heart shape",
        "body_language": "presenting hand heart",
        "arm_pose": "heart shape with both hands",
        "hand_visibility": "both",
        "openai_block": "Hands form a heart; both hands fully visible.",
        "comfyui_positive": "hand heart, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "shy_cover_mouth": {
        "label": "shy_cover_mouth",
        "description": "one or both hands shyly covering mouth",
        "body_language": "bashful hand over mouth",
        "arm_pose": "fingers over lips",
        "hand_visibility": "both",
        "openai_block": "Hand(s) covering mouth shyly; fingers visible, not hidden.",
        "comfyui_positive": "hand over mouth, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "hug_gesture": {
        "label": "hug_gesture",
        "description": "arms wrapped in self-hug or hugging air",
        "body_language": "warm hugging arms",
        "arm_pose": "arms crossed in hug",
        "hand_visibility": "both",
        "openai_block": "Arms in hug pose; hands and forearms visible on chest.",
        "comfyui_positive": "hugging arms, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "upper_body",
    },
    "two_hand_cheek_squish": {
        "label": "two_hand_cheek_squish",
        "description": "two hands squishing cheeks outward",
        "body_language": "playful cheek squish",
        "arm_pose": "both palms pushing cheeks",
        "hand_visibility": "both",
        "openai_block": "Two hands squishing cheeks; exaggerated cute hand pose.",
        "comfyui_positive": "hands on face, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "offering_heart": {
        "label": "offering_heart",
        "description": "hands offering small heart forward",
        "body_language": "giving affection gesture",
        "arm_pose": "cupped hands forward",
        "hand_visibility": "both",
        "openai_block": "Hands offering heart gesture toward viewer.",
        "comfyui_positive": "offering hands, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "sleeve_pull": {
        "label": "sleeve_pull",
        "description": "pulling sleeve or collar nervously",
        "body_language": "timid sleeve fidget",
        "arm_pose": "one hand pulling sleeve",
        "hand_visibility": "single",
        "openai_block": "Hand pulling sleeve; fingers gripping fabric, arm visible.",
        "comfyui_positive": "pulling sleeve, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "hugging_pillow": {
        "label": "hugging_pillow",
        "description": "hugging object or arms wrapped",
        "body_language": "comfort hug on pillow or arms",
        "arm_pose": "both arms wrapped around prop",
        "hand_visibility": "both",
        "openai_block": "Arms hugging pillow or chest; both hands visible gripping.",
        "comfyui_positive": "hugging pose, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "medium_shot",
    },
    "face_cover": {
        "label": "face_cover",
        "description": "hands partially covering face sadly",
        "body_language": "hide face behind hands",
        "arm_pose": "palms over eyes or cheeks",
        "hand_visibility": "both",
        "openai_block": "Hands covering part of face; fingers clearly visible, not cropped.",
        "comfyui_positive": "hands covering face, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "wiping_tear": {
        "label": "wiping_tear",
        "description": "hand wiping eye",
        "body_language": "wiping tear sadly",
        "arm_pose": "one hand at eye",
        "hand_visibility": "single",
        "openai_block": "Hand wiping eye; wrist and fingers visible.",
        "comfyui_positive": "hand near eye, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "droopy_arm_hang": {
        "label": "droopy_arm_hang",
        "description": "arms hanging low sadly",
        "body_language": "low energy dangling arms",
        "arm_pose": "arms at sides drooping",
        "hand_visibility": "both",
        "openai_block": "Both arms visible hanging low; hands drawn at sides.",
        "comfyui_positive": "droopy arms, expressive hands, visible hands at sides",
        "framing_boost": "medium_shot",
    },
    "knees_hug": {
        "label": "knees_hug",
        "description": "hugging knees, hands clasped",
        "body_language": "curled hug on knees",
        "arm_pose": "arms around knees, hands clasped",
        "hand_visibility": "both",
        "openai_block": "Hands clasped around knees; arms and hands visible.",
        "comfyui_positive": "hugging knees, expressive hands, visible hand gesture",
        "framing_boost": "medium_shot",
    },
    "crossed_arms": {
        "label": "crossed_arms",
        "description": "arms crossed firmly",
        "body_language": "defensive crossed arms",
        "arm_pose": "forearms crossed on chest",
        "hand_visibility": "both",
        "openai_block": "Arms crossed on chest; both forearms and hands visible.",
        "comfyui_positive": "crossed arms, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "upper_body",
    },
    "fist_pose": {
        "label": "fist_pose",
        "description": "clenched fists angry or determined",
        "body_language": "tight angry fists",
        "arm_pose": "fists at sides or raised",
        "hand_visibility": "both",
        "openai_block": "Clenched fists visible; knuckles and fingers readable.",
        "comfyui_positive": "clenched fists, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "upper_body",
    },
    "pointing": {
        "label": "pointing",
        "description": "pointing finger forward",
        "body_language": "accusatory or emphatic point",
        "arm_pose": "extended index finger",
        "hand_visibility": "single",
        "openai_block": "Clear pointing finger; full hand and arm visible.",
        "comfyui_positive": "pointing finger, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "upper_body",
    },
    "hands_on_hips": {
        "label": "hands_on_hips",
        "description": "hands on hips assertive",
        "body_language": "confident hands on hips",
        "arm_pose": "both hands on hips",
        "hand_visibility": "both",
        "openai_block": "Both hands on hips; elbows out, hands fully visible.",
        "comfyui_positive": "hands on hips, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "upper_body",
    },
    "trembling_fist": {
        "label": "trembling_fist",
        "description": "small trembling fists",
        "body_language": "angry trembling hands",
        "arm_pose": "fists shaking near chest",
        "hand_visibility": "both",
        "openai_block": "Trembling fists at chest height; both hands visible.",
        "comfyui_positive": "trembling fists, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "arm_swing": {
        "label": "arm_swing",
        "description": "arm swing motion annoyed",
        "body_language": "exaggerated arm swing",
        "arm_pose": "one arm swinging",
        "hand_visibility": "single",
        "openai_block": "Arm mid-swing; hand and motion readable.",
        "comfyui_positive": "swinging arm, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "upper_body",
    },
    "finger_touch": {
        "label": "finger_touch",
        "description": "index fingers touching nervously",
        "body_language": "awkward finger fidget",
        "arm_pose": "index fingers touching in front",
        "hand_visibility": "both",
        "openai_block": "Index fingers touching; both hands visible in front of chest.",
        "comfyui_positive": "fingers touching, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "scratching_head": {
        "label": "scratching_head",
        "description": "hand scratching back of head",
        "body_language": "awkward scratch",
        "arm_pose": "arm raised to head",
        "hand_visibility": "single",
        "openai_block": "Hand scratching head; elbow bent, hand visible.",
        "comfyui_positive": "hand on head, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "upper_body",
    },
    "tiny_wave": {
        "label": "tiny_wave",
        "description": "small shy wave",
        "body_language": "timid small wave",
        "arm_pose": "small hand wave at side",
        "hand_visibility": "single",
        "openai_block": "Small wave with one hand; fingers and palm visible.",
        "comfyui_positive": "small wave, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "nervous_hand_clasp": {
        "label": "nervous_hand_clasp",
        "description": "hands clasped nervously",
        "body_language": "fidgeting clasped hands",
        "arm_pose": "fingers interlocked in front",
        "hand_visibility": "both",
        "openai_block": "Clasped hands in front; all fingers visible.",
        "comfyui_positive": "clasped hands, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "peek_hand_wave": {
        "label": "peek_hand_wave",
        "description": "hand peeking and tiny wave",
        "body_language": "peek wave from side",
        "arm_pose": "hand entering frame waving",
        "hand_visibility": "single",
        "openai_block": "Hand peeking into frame with wave; full hand visible.",
        "comfyui_positive": "peeking hand wave, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "index_fingers_touch": {
        "label": "index_fingers_touch",
        "description": "two index fingers touching (shy)",
        "body_language": "classic shy finger touch",
        "arm_pose": "index fingertips together",
        "hand_visibility": "both",
        "openai_block": "Index fingertips touching; both hands in frame.",
        "comfyui_positive": "index fingers touching, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "hands_on_cheeks": {
        "label": "hands_on_cheeks",
        "description": "both hands on cheeks surprised",
        "body_language": "shocked hands on face",
        "arm_pose": "palms on cheeks",
        "hand_visibility": "both",
        "openai_block": "Both palms on cheeks; surprised hand pose.",
        "comfyui_positive": "hands on cheeks, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "hands_up_shock": {
        "label": "hands_up_shock",
        "description": "hands raised in shock",
        "body_language": "startled hands up",
        "arm_pose": "both hands up near head",
        "hand_visibility": "both",
        "openai_block": "Hands raised beside head; full arms visible.",
        "comfyui_positive": "hands up, expressive hands, visible hand gesture, dynamic arm pose",
        "framing_boost": "upper_body",
    },
    "open_palms_out": {
        "label": "open_palms_out",
        "description": "open palms outward surprise",
        "body_language": "what?! open palms",
        "arm_pose": "palms out forward",
        "hand_visibility": "both",
        "openai_block": "Open palms toward viewer; both hands large and clear.",
        "comfyui_positive": "open palms, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "rubbing_eye": {
        "label": "rubbing_eye",
        "description": "rubbing tired eye",
        "body_language": "sleepy eye rub",
        "arm_pose": "knuckle at eye",
        "hand_visibility": "single",
        "openai_block": "Hand rubbing eye; fingers visible.",
        "comfyui_positive": "hand at eye, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "yawn_hand_cover": {
        "label": "yawn_hand_cover",
        "description": "hand over yawning mouth",
        "body_language": "yawn cover mouth",
        "arm_pose": "palm over mouth",
        "hand_visibility": "single",
        "openai_block": "Hand covering yawn; hand fully drawn.",
        "comfyui_positive": "hand over mouth, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "ok_sign": {
        "label": "ok_sign",
        "description": "ok sign hand",
        "body_language": "ok gesture",
        "arm_pose": "ok finger circle",
        "hand_visibility": "single",
        "openai_block": "OK hand sign clearly visible.",
        "comfyui_positive": "ok sign hand, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "thinking_chin": {
        "label": "thinking_chin",
        "description": "hand on chin thinking",
        "body_language": "thinking pose",
        "arm_pose": "finger on chin",
        "hand_visibility": "single",
        "openai_block": "Hand on chin; fingers and wrist visible.",
        "comfyui_positive": "hand on chin, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
    "casual_hand_rest": {
        "label": "casual_hand_rest",
        "description": "one hand resting visible",
        "body_language": "relaxed hand on hip or cheek",
        "arm_pose": "hand on hip",
        "hand_visibility": "single",
        "openai_block": "One hand resting on hip or cheek; hand not hidden.",
        "comfyui_positive": "hand on hip, expressive hands, visible hand gesture",
        "framing_boost": "upper_body",
    },
}


def _awkward_category(category: str) -> str:
    if category in ("shy", "neutral"):
        return "awkward"
    return category


def get_hand_actions_for_emotion(category: str) -> tuple[str, ...]:
    cat = _awkward_category(category)
    return EMOTION_HAND_ACTIONS.get(cat, EMOTION_HAND_ACTIONS.get(category, EMOTION_HAND_ACTIONS["neutral"]))


def select_hand_action(
    emotion_category: str,
    cut_index: int,
    pose_type: str,
) -> str:
    actions = get_hand_actions_for_emotion(emotion_category)
    aligned = _POSE_HAND_ALIGN.get(pose_type)
    if aligned and aligned in actions:
        return aligned
    return actions[cut_index % len(actions)]


def resolve_hand_action(
    action_id: str,
    *,
    is_human: bool,
    is_pet: bool,
    output_mode: str,
    sticker_exaggerate: bool = True,
) -> HandActionSpec:
    raw = dict(_HAND_CATALOG.get(action_id, _HAND_CATALOG["tiny_wave"]))
    desc = raw["description"]
    body = raw["body_language"]
    arm = raw["arm_pose"]
    if is_human:
        arm = arm.replace("paw", "hand").replace("Paw", "hand")
    elif is_pet:
        desc = desc.replace("hand", "paw").replace("finger", "paw")
        arm = arm.replace("hand", "paw").replace("finger", "paw")
    openai = raw["openai_block"]
    comfy = raw["comfyui_positive"]
    if output_mode == "sticker" and sticker_exaggerate:
        openai += " Exaggerate hand size slightly for Kakao emoticon readability; hands are a primary emotion carrier."
        comfy += ", exaggerated hands, large readable hand gesture, chibi hand proportions"
    return HandActionSpec(
        action_id=action_id,
        label=raw["label"],
        description=desc,
        body_language=body,
        arm_pose=arm,
        hand_visibility=raw["hand_visibility"],
        openai_block=openai,
        comfyui_positive=comfy,
        framing_boost=raw.get("framing_boost", "upper_body"),
    )


def apply_framing_boost_for_hands(framing: str, hand: HandActionSpec) -> str:
    """Prefer upper_body / medium_shot so hands are not cropped."""
    boost = hand.framing_boost
    if framing == "closeup":
        return boost if boost in ("upper_body", "medium_shot") else "upper_body"
    if framing == "face_closeup":
        return "upper_body"
    return framing


def hand_negative_prompt(*, output_mode: str) -> str:
    base = "missing hands, cropped hands, hidden arms, hands behind back, hands out of frame, arm cut off"
    if output_mode == "sticker":
        base += ", tiny invisible hands, hands merged into body, no visible gesture"
    return base


def hand_positive_core(*, output_mode: str, sticker_exaggerate: bool = True) -> str:
    parts = [
        "expressive hands",
        "visible hand gesture",
        "dynamic arm pose",
        "clear forearms",
    ]
    if output_mode == "sticker" and sticker_exaggerate:
        parts.extend(["exaggerated hands", "large readable hands", "hand-focused gesture"])
    return ", ".join(parts)
