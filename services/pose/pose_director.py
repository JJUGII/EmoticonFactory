"""Plan pose/composition per cut from emotion → body language → prompt hints."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from services.directing.body_acting import resolve_body_acting
from services.directing.exaggerated_acting import concise_template_hint_for_cut
from services.directing.composition_director import (
    FRAMING_SCHEDULE,
    CompositionAssignment,
    CompositionDirector,
    log_composition_director,
)
from services.directing.directing_diversity import DirectingDiversityTracker
from services.directing.emotion_fx import log_emotion_fx, resolve_emotion_fx
from services.directing.framing_enforcer import FramingDiversityEnforcer, log_framing_reroll
from services.directing.adaptive_sampler import log_adaptive_denoise
from services.directing.identity_dynamic import log_identity_dynamic
from services.directing.sticker_execution import build_cut_execution_profile
from services.pose.expression_override import load_comfyui_expression_strength
from services.pose.composition_templates import (
    anti_frontal_negative,
    composition_style_for_framing,
    framing_prompt_hint,
)
from services.pose.hand_actions import (
    HandActionSpec,
    apply_framing_boost_for_hands,
    hand_negative_prompt,
    hand_positive_core,
    resolve_hand_action,
    select_hand_action,
)
from services.pose.pose_templates import (
    classify_emotion_category,
    get_pose_types_for_category,
    humanize_hand_action,
    pose_detail,
)
from services.prompts.common_cut_spec import CutSpec
from services.prompts.entity_profile import EntityProfile
from services.prompts.prompt_profiles import OutputMode, PromptPipelineSettings


@dataclass(frozen=True)
class CutPosePlan:
    cut_id: str
    emotion_category: str
    pose_type: str
    camera_framing: str
    body_direction: str
    hand_action: str
    hand_action_id: str
    accessory_action: str
    composition_style: str
    camera_angle: str
    body_language: str
    arm_pose: str
    pose_freedom: str  # low | medium | high
    template_pose_hint: str
    hand_spec: HandActionSpec | None = None
    directing_framing: str = ""
    directing_camera: str = ""
    directing_pose: str = ""
    emotion_fx: str = ""
    body_acting_block: str = ""
    staging_pattern_id: str = ""
    identity_weight: float = 0.65
    sampler_denoise: float = 0.32
    execution_hard_positive: str = ""
    execution_hard_negative: str = ""
    pose_strength_block: str = ""
    text_safe_positive: str = ""
    text_safe_negative: str = ""
    framing_rerolled: bool = False

    def openai_layout_block(self, *, output_mode: OutputMode) -> str:
        framing_hint = framing_prompt_hint(self.camera_framing, output_mode=output_mode)
        hand_block = ""
        if self.hand_spec:
            hand_block = (
                f"[Hand action — PRIMARY] {self.hand_spec.label}: {self.hand_spec.description}. "
                f"{self.hand_spec.openai_block} "
                f"Arm pose: {self.hand_spec.arm_pose}. "
                f"Hands must be fully visible; prefer {self.camera_framing} framing. "
            )
        exaggeration = (
            "Hands and arms carry the emotion as much as the face; exaggerate gesture for sticker readability. "
            if output_mode == "sticker"
            else "Clear hand staging with gentle scene atmosphere. "
        )
        directing = ""
        if self.directing_framing:
            directing = (
                f"[Directing] framing={self.directing_framing}; camera={self.directing_camera}; "
                f"pose={self.directing_pose}; pattern={self.staging_pattern_id}. "
                f"[FX] {self.emotion_fx}. "
            )
        return (
            f"[Pose] type={self.pose_type}; direction={self.body_direction}. "
            f"{hand_block}"
            f"{directing}"
            f"[Body language] {self.body_language}. "
            f"Accessory: {self.accessory_action}. "
            f"[Framing] {self.camera_framing}; angle={self.camera_angle}; "
            f"{framing_hint} "
            f"[Composition] {self.composition_style}. "
            f"{exaggeration}"
            f"Do not draw face-only mugshot; emotion must read from hands + pose + face. "
        )

    def comfyui_keywords(self, *, output_mode: OutputMode) -> str:
        framing_kw = self.camera_framing.replace("_", " ")
        pose_kw = self.pose_type.replace("_", " ")
        hand_kw = (
            self.hand_spec.comfyui_positive
            if self.hand_spec
            else self.hand_action
        )
        parts = [
            hand_positive_core(output_mode=output_mode, sticker_exaggerate=output_mode == "sticker"),
            hand_kw,
            pose_kw,
            framing_kw,
            self.body_direction.replace("_", " "),
            self.arm_pose,
            self.camera_angle.replace("_", " "),
            self.directing_framing.replace("_", " "),
            self.directing_pose.replace("_", " "),
            self.body_acting_block,
            self.emotion_fx,
            "dynamic composition",
            "not front passport portrait",
        ]
        if output_mode == "sticker":
            parts.extend(["kakao emoticon hand gesture", "emotion through body language"])
        else:
            parts.extend(["storybook staging", "soft background"])
        return ", ".join(p for p in parts if p)

    def negative_extras(self, *, output_mode: OutputMode = "sticker") -> str:
        return f"{anti_frontal_negative()}, {hand_negative_prompt(output_mode=output_mode)}"


class PoseDirector:
    """emotion → pose/composition planning."""

    def __init__(
        self,
        *,
        composition_director: CompositionDirector | None = None,
    ) -> None:
        self._composition = composition_director or CompositionDirector()

    def plan(
        self,
        cut: CutSpec,
        *,
        entity: EntityProfile,
        settings: PromptPipelineSettings,
        output_mode: OutputMode,
        engine: str,
        directing_tracker: DirectingDiversityTracker | None = None,
        framing_enforcer: FramingDiversityEnforcer | None = None,
        expression_intensity: str | None = None,
    ) -> CutPosePlan:
        tuning = settings.tuning_for(engine)
        category = classify_emotion_category(
            cut.emotion,
            cut.facial_expression,
            cut.text,
            cut.action,
        )
        poses = get_pose_types_for_category(category)
        cut_id_s = str(cut.id)
        cut_idx = max(0, int(cut_id_s) - 1) if cut_id_s.isdigit() else 0
        expr_intensity = expression_intensity or load_comfyui_expression_strength()

        comp: CompositionAssignment | None = None
        pose_type = poses[cut_idx % len(poses)]
        hand_id = select_hand_action(category, cut_idx, pose_type)
        detail = pose_detail(pose_type)
        framing_rerolled = False
        directing_rerolled = False

        framing_candidates = self._composition.iter_framing_candidates(
            cut_idx, layout_type=cut.layout_type
        )
        if output_mode == "sticker" and not framing_candidates:
            framing_candidates = list(FRAMING_SCHEDULE)

        accepted = False
        for fi, framing_key in enumerate(
            framing_candidates if output_mode == "sticker" else ["upper_body"]
        ):
            if output_mode == "sticker":
                comp = self._composition.preview_framing(framing_key)
            else:
                comp = self._composition.assign(
                    cut_id_s,
                    cut_idx,
                    layout_type=cut.layout_type,
                    emotion_category=category,
                )
            for offset in range(max(len(poses), 1)):
                pt = poses[(cut_idx + offset) % len(poses)]
                hid = select_hand_action(category, cut_idx + offset, pt)
                det = pose_detail(pt)
                body_dir = det["body_direction"]
                if framing_enforcer and framing_enforcer.would_duplicate(
                    comp.camera, comp.framing, body_dir
                ):
                    framing_rerolled = True
                    log_framing_reroll(
                        cut.id,
                        camera=comp.camera,
                        framing=comp.framing,
                        body_direction=body_dir,
                        attempt=fi * len(poses) + offset,
                    )
                    continue
                if directing_tracker and directing_tracker.would_duplicate(
                    comp.framing, pt, hid
                ):
                    directing_rerolled = True
                    continue
                pose_type = pt
                hand_id = hid
                detail = det
                if output_mode == "sticker":
                    comp = self._composition.commit_framing(comp.framing)
                if framing_enforcer:
                    framing_enforcer.register(comp.camera, comp.framing, body_dir)
                if directing_tracker:
                    directing_tracker.register(comp.framing, pose_type, hand_id)
                accepted = True
                break
            if accepted:
                break

        if not accepted and output_mode == "sticker":
            comp = self._composition.assign(
                cut_id_s,
                cut_idx,
                layout_type=cut.layout_type,
                emotion_category=category,
            )
            pose_type = poses[cut_idx % len(poses)]
            hand_id = select_hand_action(category, cut_idx, pose_type)
            detail = pose_detail(pose_type)

        assert comp is not None
        log_composition_director(cut.id, comp)
        framing = comp.camera_framing

        if output_mode == "sticker":
            template_hint = concise_template_hint_for_cut(
                category,
                cut_idx,
                cut.emotion,
                cut.text,
                cut.action,
            )
        else:
            template_hint = " ".join(
                x
                for x in (cut.body_pose, cut.action, cut.motion_hint)
                if str(x).strip()
            ).strip()

        freedom = self._pose_freedom(tuning.identity_lock, tuning.pose_variation, output_mode)

        body = resolve_body_acting(
            category,
            cut_idx,
            cut_text=cut.text,
            action=cut.action,
        )
        fx = resolve_emotion_fx(category, cut_idx)
        log_emotion_fx(cut.id, fx)

        hand_spec = resolve_hand_action(
            hand_id,
            is_human=entity.is_human,
            is_pet=entity.is_pet,
            output_mode=output_mode,
            sticker_exaggerate=output_mode == "sticker",
        )
        framing = apply_framing_boost_for_hands(framing, hand_spec)

        hand_desc = humanize_hand_action(
            hand_spec.description,
            is_human=entity.is_human,
            is_pet=entity.is_pet,
        )
        body_language = (
            f"{hand_spec.body_language}; pose={detail['body_language']}; "
            f"arm={hand_spec.arm_pose}"
        )

        if freedom == "low" and output_mode != "sticker":
            if pose_type in ("jumping_pose", "exaggerated_stomp", "jump_back"):
                pose_type = "leaning_pose" if category == "happy" else "crossed_arms"
                detail = pose_detail(pose_type)

        if freedom == "high" and output_mode == "sticker":
            if comp.framing in ("full_body", "action_pose", "sitting_pose"):
                pass
            elif comp.framing == "closeup" and hand_spec.framing_boost != "none":
                framing = apply_framing_boost_for_hands("upper_body", hand_spec)

        if output_mode == "sticker":
            comp_style = comp.composition_hint
        else:
            comp_style = composition_style_for_framing(framing)
            comp_style += f"; {comp.composition_hint}"
            comp_style += "; allow soft partial background and mood lighting"

        exec_prof = build_cut_execution_profile(
            framing=comp.framing,
            layout_type=cut.layout_type,
            expression_intensity=expr_intensity,
            text_position=cut.text_position,
            pose_token=f"{pose_type.replace('_', ' ')}, {comp.pose.replace('_', ' ')}",
        )
        log_identity_dynamic(cut.id, comp.framing, exec_prof.identity_weight)
        log_adaptive_denoise(cut.id, comp.framing, exec_prof.denoise)

        return CutPosePlan(
            cut_id=cut.id,
            emotion_category=category,
            pose_type=pose_type,
            camera_framing=framing,
            body_direction=detail["body_direction"],
            hand_action=hand_desc,
            hand_action_id=hand_id,
            accessory_action=detail["accessory_action"],
            composition_style=comp_style,
            camera_angle=detail["camera_angle"],
            body_language=body_language,
            arm_pose=hand_spec.arm_pose,
            pose_freedom=freedom,
            template_pose_hint=template_hint,
            hand_spec=hand_spec,
            directing_framing=comp.framing,
            directing_camera=comp.camera,
            directing_pose=comp.pose,
            emotion_fx=fx.positive_tags,
            body_acting_block=body.positive_block,
            staging_pattern_id=body.pattern_id,
            identity_weight=exec_prof.identity_weight,
            sampler_denoise=exec_prof.denoise,
            execution_hard_positive=exec_prof.hard_positive,
            execution_hard_negative=exec_prof.hard_negative,
            pose_strength_block=exec_prof.pose_strength_block,
            text_safe_positive=exec_prof.text_safe_positive,
            text_safe_negative=exec_prof.text_safe_negative,
            framing_rerolled=framing_rerolled,
        )

    @staticmethod
    def _pose_freedom(identity_lock: float, pose_variation: float, output_mode: OutputMode) -> str:
        # COMFYUI_IDENTITY_LOCK=medium (0.65) → high pose freedom when variation also high
        score = pose_variation * 0.55 + (1.0 - identity_lock) * 0.45
        if output_mode == "illustration":
            score += 0.05
        if identity_lock <= 0.65 and pose_variation >= 0.6:
            return "high"
        if score >= 0.55:
            return "medium"
        return "low"


def log_pose_planning(plan: CutPosePlan) -> None:
    print(
        f"[POSE] cut={plan.cut_id} category={plan.emotion_category} "
        f"pose_type={plan.pose_type} body_direction={plan.body_direction} "
        f"freedom={plan.pose_freedom}",
        file=sys.stderr,
    )
    hid = plan.hand_action_id
    vis = plan.hand_spec.hand_visibility if plan.hand_spec else "?"
    print(
        f"[HAND_ACTION] cut={plan.cut_id} action={hid} visibility={vis} "
        f"arm_pose={plan.arm_pose} description={plan.hand_action[:100]}",
        file=sys.stderr,
    )
    print(
        f"[BODY_LANGUAGE] cut={plan.cut_id} primary={plan.hand_spec.body_language if plan.hand_spec else plan.body_language} "
        f"combined={plan.body_language[:160]}",
        file=sys.stderr,
    )
    print(
        f"[COMPOSITION] cut={plan.cut_id} camera_framing={plan.camera_framing} "
        f"camera_angle={plan.camera_angle} composition_style={plan.composition_style} "
        f"accessory_action={plan.accessory_action}",
        file=sys.stderr,
    )
    layout_line = (
        f"[PROMPT_LAYOUT] cut={plan.cut_id} pose={plan.pose_type} hand={hid} "
        f"framing={plan.camera_framing} direction={plan.body_direction} "
        f"template_hint={plan.template_pose_hint[:100]}"
    )
    print(layout_line, file=sys.stderr)
