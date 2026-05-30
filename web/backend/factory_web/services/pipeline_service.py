"""Wrap KakaoEmoticonFactory ``PipelineRunner`` + canonical manager."""

from __future__ import annotations

import json
import re
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from factory_web.config import FACTORY_ROOT
from factory_web.services.job_store import JobStore

if str(FACTORY_ROOT) not in sys.path:
    sys.path.insert(0, str(FACTORY_ROOT))

from services.base_character_prompt import CANONICAL_BASE_POLICY_KO  # noqa: E402
from services.canonical_character_manager import (  # noqa: E402
    CanonicalCharacterManager,
    SELECTED_BASE_CANDIDATE_TYPE,
)
from services.concept_planner import ConceptPlanner  # noqa: E402
from services.pipeline_runner import PipelineOptions, PipelineRunner  # noqa: E402


_CUT_LOG_RE = re.compile(r"\[OpenAI 컷 (\d{2})\]|컷 id (\d{2})")
_DETECT_SPECIES_RE = re.compile(r"\[자동감지\] species_hint 자동 설정: (\w+)")
_VALID_SPECIES = frozenset({"human", "cat", "dog", "rabbit", "hamster", "bird"})


def _parse_detected_species(logs: str) -> str:
    """파이프라인 로그에서 자동감지된 species를 추출."""
    m = _DETECT_SPECIES_RE.search(logs)
    if m:
        s = m.group(1).strip().lower()
        if s in _VALID_SPECIES:
            return s
    return ""


def _format_pipeline_error(code: int, logs: list[str]) -> str:
    tail = "".join(logs)[-2000:]
    if code == 7 or "OpenAIMissingKeyError" in tail or "OPENAI_API_KEY" in tail:
        return (
            "OpenAI API 키가 없습니다. 프로젝트 루트 .env 에 OPENAI_API_KEY 를 넣거나 "
            "UI에서 생성 엔진을 mock 으로 선택하세요. (app.py exit 7)"
        )
    return f"파이프라인 실패 (exit {code}). 로그: web/jobs/.../job.json 의 log_tail 참고"


def _package_dir(job: dict[str, Any], store: JobStore) -> Path:
    from services.pipeline_runner import _safe_folder_name

    folder = _safe_folder_name(str(job["series_name"]))
    return store.output_root(str(job["job_id"])) / folder


# ── 감정 → 템플릿 매칭 테이블 ────────────────────────────────────────────
# 각 튜플: (감정 키워드들, 선호 템플릿 0-기반 인덱스들(우선순위 순))
# 템플릿 감정: 0=따뜻한애정, 1=애틋함, 2=애교, 3=기쁨, 4=서운함,
#              5=질투, 6=설렘, 7=달콤함, 8=호기심, 9=평온,
#              10=감사, 11=미안함, 12=무기력, 13=동의, 14=짜증, 15=과한애정
_EMOTION_TEMPLATE_PREFS: list[tuple[tuple[str, ...], tuple[int, ...]]] = [
    # ── 사랑/애정 계열 ──
    (("사랑해", "사랑", "love", "하트폭격", "사랑스"),     (0, 15)),
    (("보고싶", "그리워", "miss", "보고싶어"),             (1, 4)),
    (("안아줘", "안아", "hug", "안아달라", "안겨"),         (2, 0)),
    (("좋아", "좋아해", "like", "좋음"),                   (6, 3, 15)),
    (("뽀뽀", "키스", "kiss", "달콤", "입맞"),             (7,)),
    (("윙크", "wink", "눈짓", "시크"),                     (7, 5)),
    (("설레", "두근", "심쿵", "flutter", "두근두근"),       (6, 3)),

    # ── 감사/미안 계열 ──
    (("고마워", "감사", "thank", "고마", "고맙"),           (10, 2)),
    (("미안해", "미안", "sorry", "잘못", "사과"),           (11, 4)),

    # ── 긍정/기쁨 계열 ──
    (("행복해", "행복", "happy", "기뻐", "기쁘"),           (3, 6)),
    (("대박", "와우", "wow", "굿", "good", "짱"),           (6, 15, 3)),
    (("귀여워", "귀엽", "cute", "kawaii"),                  (2, 3)),
    (("뿌잉", "냥냥", "멍멍", "삐용"),                     (2, 6)),   # 애교/귀여운 소리
    (("화이팅", "파이팅", "응원해", "응원", "힘내"),        (15, 6)),

    # ── 부정/짜증/서운함 계열 ──
    (("화났어", "화나", "angry", "킹받", "짜증", "빡"),     (14, 5)),
    (("가지마", "가지말", "떠나지", "가면안"),              (4, 1)),
    (("눈물", "울어", "슬퍼", "울고싶", "cry", "슬픔"),     (4, 11)),
    (("힘들어", "힘들", "지쳐", "지친"),                    (12, 4)),
    (("질투", "부럽", "jealous"),                           (5,)),

    # ── 놀람/호기심 계열 ──
    (("놀랐어", "놀람", "surprised", "깜짝", "놀라", "헉"), (6, 5, 3)),
    (("뭐해", "궁금", "호기심", "어떻게", "왜"),            (8,)),

    # ── 수면/휴식 계열 ──
    (("졸려", "sleepy", "피곤", "졸리"),                    (9,)),
    (("잘자", "goodnight", "자요", "자자", "쿨쿨", "zzz"), (9, 7, 0)),
    (("배고파", "hungry", "먹고싶", "배고"),                (8, 4, 12)),
    (("심심해", "심심", "bored", "귀찮", "무기력"),         (12, 8)),
    (("축하해", "축하", "celebr", "만세"),                  (15, 6, 3)),

    # ── 기타 ──
    (("인정", "동의", "맞아", "okay", "ㅇㅇ"),              (13,)),
    (("부끄", "수줍", "쑥쓰", "shy"),                       (3, 7)),   # 눈 감고 볼 빨개짐
    (("으쓱", "뿌듯", "자랑"),                              (15, 6)),
]

# 특정 감정에 대한 emotion 레이블 + 포즈/표정 보정 오버라이드
_EMOTION_POSE_OVERRIDES: dict[str, dict[str, str]] = {
    "배고파": {
        "emotion": "배고픔",
        "facial_expression": "눈이 반쯤 풀리고 입꼬리 처짐, 배고픔에 맥 빠진 표정",
        "action": "배를 두 손으로 감싸며 고개를 살짝 숙임",
        "body_pose": "한쪽 손을 배에 얹고 정면을 바라보는 기운 없는 자세",
        "motion_hint": "배 부분 손이 배고픔에 살짝 떨림",
    },
    "놀랐어": {
        "emotion": "놀람",
        "facial_expression": "눈 크게 뜨고 입 살짝 벌린 놀란 표정, 동공 확장",
        "action": "두 손을 볼 옆에 들어올리며 뒤로 살짝 젖히는 놀람 반응",
        "body_pose": "상체를 살짝 뒤로 빼며 놀란 자세",
        "motion_hint": "놀라서 상체가 짧게 뒤로 한 번 젖혀짐",
        "prop": "none",
    },
    "응원해": {
        "emotion": "응원/열정",
        "facial_expression": "활짝 웃으며 힘차게 응원하는 밝은 표정",
        "action": "두 주먹을 좌우 완전 대칭으로 위로 힘차게 든 응원 동작",
        "body_pose": "캐릭터가 화면 정중앙에 위치, 좌우 대칭 포즈, 두 팔 동시에 위로 든 자세 — 한쪽으로 치우치지 않음",
        "motion_hint": "두 팔이 동시에 위로 한 번 올라갔다 내려옴",
        "prop": "none",
    },
    "축하해": {
        "emotion": "축하/기쁨",
        "facial_expression": "크게 활짝 웃으며 축하하는 환한 표정",
        "action": "양손을 위로 번쩍 들어올리며 만세 동작, 폭죽이나 하트 비산",
        "body_pose": "두 팔 위로 들어올린 만세 자세, 전신 들뜬 기운",
        "motion_hint": "배경에서 하트·폭죽·별 같은 반짝임이 터짐",
        "prop": "heart_shower",
    },
    "가지마": {
        "emotion": "서운함/가지마",
        "facial_expression": "입술을 살짝 내밀고 눈꼬리 처진 토라진 서운한 표정, 눈을 살짝 흘김",
        "action": "팔짱 끼고 고개만 살짝 옆으로 돌리는 토라진 동작",
        "body_pose": "캐릭터 정중앙 배치, 정면 또는 3/4 정면 방향 — 완전 뒷모습 절대 금지, 팔짱 낀 상반신 포즈",
        "motion_hint": "고개를 살짝 옆으로 돌리며 눈을 흘기는 동작",
        "prop": "none",
    },
    "눈물": {
        "emotion": "슬픔/눈물",
        "facial_expression": "눈에 눈물이 그렁그렁 맺히고 입꼬리가 처진 슬픈 표정",
        "action": "한 손 또는 두 손으로 눈물을 닦는 동작",
        "body_pose": "캐릭터 정중앙 배치, 정면 방향, 어깨가 살짝 처진 슬픈 자세 — 뒷모습 절대 금지",
        "motion_hint": "눈에서 눈물 한 방울이 흘러내림",
        "prop": "none",
    },
    "슬퍼": {
        "emotion": "슬픔",
        "facial_expression": "눈이 촉촉하고 입꼬리가 처진 슬픈 표정",
        "action": "두 손을 가슴에 모으고 고개를 살짝 숙임",
        "body_pose": "캐릭터 정중앙 배치, 정면 방향, 어깨가 처진 슬픈 자세 — 뒷모습 절대 금지",
        "motion_hint": "눈가에 눈물이 살짝 맺힘",
        "prop": "none",
    },
    "보고싶어": {
        "emotion": "그리움",
        "facial_expression": "눈을 살짝 촉촉하게 빛내며 먼 곳을 바라보는 그리운 표정, 입꼬리가 살짝 내려감",
        "action": "두 손을 가슴 앞에 모으고 먼 곳을 바라보는 그리움의 포즈",
        "body_pose": "캐릭터 상반신이 화면 정중앙에 위치, 박스·울타리·테이블 등 소품 일체 없음, 단순 배경",
        "motion_hint": "눈에 살짝 눈물이 맺히는 효과",
        "prop": "none",
    },
    "안아줘": {
        "emotion": "안아줘/애교",
        "facial_expression": "눈을 살짝 감고 입을 살짝 삐죽이는 애교 표정, 볼이 부풀어",
        "action": "두 팔을 가슴 높이에서 좌우 대칭으로 앞으로 살짝 뻗어 안아달라는 제스처",
        "body_pose": "캐릭터가 화면 정중앙에 위치, 두 팔이 좌우 완전 대칭으로 앞으로 뻗은 자세 — 한쪽으로 치우치지 않음",
        "motion_hint": "팔이 살짝 앞뒤로 흔들리는 동작",
        "prop": "none",
    },
    "잘자": {
        "emotion": "평온/수면",
        "facial_expression": "눈 감고 부드러운 미소, 편안한 수면 표정",
        "action": "두 손을 볼 옆에 모아 대고 고개 살짝 기울임",
        "body_pose": "눈 감고 양손을 볼에 모은 잘자 포즈",
        "motion_hint": "머리 위에서 Zzz 문양이 살짝 떠오름",
        "prop": "none",
    },
}


def _score_emotion_template(emotion: str, tmpl_idx: int) -> int:
    """감정 텍스트 ↔ 템플릿 인덱스 적합도.

    점수 체계:
      100-80  하드코딩 _EMOTION_TEMPLATE_PREFS (1순위·2순위)
      60      GPT 확장 키워드 (emotion_auto_tune.score_expanded)
      0       미매칭
    임베딩 폴백(40점)은 _match_emotions_to_templates() 에서 단어 단위로 처리.
    """
    emo = emotion.strip().lower()
    # ── 1: 하드코딩 키워드 테이블 ──
    for keywords, prefs in _EMOTION_TEMPLATE_PREFS:
        if any(kw in emo for kw in keywords):
            if tmpl_idx in prefs:
                return 100 - list(prefs).index(tmpl_idx) * 20
    # ── 2: GPT 확장 키워드 (초기화 완료 시에만) ──
    try:
        from factory_web.services import emotion_auto_tune  # noqa: PLC0415
        return emotion_auto_tune.score_expanded(emotion, tmpl_idx)
    except Exception:
        return 0


def _match_emotions_to_templates(emotions: list[str], n: int = 16) -> list[int]:
    """각 감정 → 최적 템플릿 인덱스(0-based) 그리디 최대 매칭.

    1) 하드코딩 + GPT 확장 키워드 점수로 그리디 배정
    2) 여전히 None인 감정 → 임베딩 cosine similarity (단어당 API 1회)
    3) 그래도 None → 남은 템플릿 순서 폴백
    """
    scores: list[tuple[int, int, int]] = []
    for ei, emo in enumerate(emotions[:n]):
        for ti in range(n):
            s = _score_emotion_template(emo, ti)
            if s > 0:
                scores.append((-s, ei, ti))
    scores.sort()

    result: list[int | None] = [None] * len(emotions)
    used_emos: set[int] = set()
    used_tmpl: set[int] = set()
    for _, ei, ti in scores:
        if ei in used_emos or ti in used_tmpl:
            continue
        result[ei] = ti
        used_emos.add(ei)
        used_tmpl.add(ti)

    # ── 임베딩 폴백: 키워드 미매칭 단어만 처리 ──
    unmatched = [ei for ei in range(len(emotions)) if result[ei] is None]
    if unmatched:
        try:
            from factory_web.services import emotion_auto_tune  # noqa: PLC0415
            for ei in unmatched:
                idx = emotion_auto_tune.best_by_embedding(
                    emotions[ei], exclude_idxs=set(used_tmpl)
                )
                if idx is not None:
                    result[ei] = idx
                    used_emos.add(ei)
                    used_tmpl.add(idx)
        except Exception:
            pass

    # ── 순서 폴백 ──
    remaining = [i for i in range(n) if i not in used_tmpl]
    for ei in range(len(emotions)):
        if result[ei] is None:
            result[ei] = remaining.pop(0) if remaining else ei % n
    return result  # type: ignore[return-value]


def _apply_emotion_pose_overrides(row: dict, emotion_text: str) -> None:
    """특정 감정 키워드에 맞게 facial_expression / action / body_pose 보정."""
    emo = emotion_text.strip().lower()
    for keyword, overrides in _EMOTION_POSE_OVERRIDES.items():
        if keyword in emo:
            row.update(overrides)
            break


def build_custom_templates(job_dir: Path, emotions: list[str]) -> Path:
    """감정 텍스트를 의미에 맞는 템플릿 포즈에 매칭해 custom_templates.json 생성."""
    base = FACTORY_ROOT / "data" / "big_emoticon_templates.json"
    templates = json.loads(base.read_text(encoding="utf-8"))

    n = min(len(emotions), 16)
    matching = _match_emotions_to_templates(emotions[:n])

    rows = []
    for pos_idx in range(n):
        tmpl = dict(templates[matching[pos_idx]])
        tmpl["id"] = str(pos_idx + 1).zfill(2)          # 순서 고정 ID
        tmpl["text"] = str(emotions[pos_idx]).strip()    # 사용자 감정 텍스트
        _apply_emotion_pose_overrides(tmpl, tmpl["text"])  # 필요 시 표정 보정
        rows.append(tmpl)

    out = job_dir / "custom_templates.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def _sync_cuts_from_disk(job: dict[str, Any], pkg: Path) -> None:
    sticker = pkg / "png"
    if not sticker.is_dir():
        sticker = pkg / "png_no_text"
    cuts = job.get("cuts") or []
    for c in cuts:
        cid = str(c.get("id", "")).zfill(2)
        p = sticker / f"{cid}.png"
        if p.is_file() and c.get("status") != "done":
            c["status"] = "done"
    job["cuts"] = cuts


def _parse_log_progress(job: dict[str, Any], line: str) -> None:
    m = _CUT_LOG_RE.search(line)
    if m:
        cid = (m.group(1) or m.group(2) or "01").zfill(2)
        job["current_cut"] = cid
        for c in job.get("cuts") or []:
            if str(c.get("id")) == cid:
                c["status"] = "running"
        done = sum(1 for c in job.get("cuts") or [] if c.get("status") == "done")
        job["progress"] = min(95, int(10 + done * 5))


class PipelineService:
    def __init__(self, store: JobStore | None = None) -> None:
        self.store = store or JobStore()
        self.runner = PipelineRunner(project_root=FACTORY_ROOT)
        self._lock = threading.Lock()

    def _options(self, job: dict[str, Any], upload: Path) -> PipelineOptions:
        return PipelineOptions(
            character_path=str(upload.resolve()),
            series_name=str(job["series_name"]),
            theme=str(job.get("theme") or "사랑"),
            species_hint=str(job.get("species_hint") or ""),
            reference_type="photo",
            stylizer="none",
            generator=str(job.get("generator") or "mock"),
            overwrite=True,
            make_preview=True,
            no_ai_text=True,
            output_root=str(self.store.output_root(str(job["job_id"])).resolve()),
            candidate_count=1,
            candidate_openai_model=str(job.get("candidate_openai_model") or "gpt-image-1"),
            candidate_openai_mode=str(job.get("candidate_openai_mode") or "auto"),
            grid_mode=True,
            art_style=str(job.get("art_style") or "illustration").strip().lower(),
            no_text_overlay=True,
        )

    def _log_sink(self, job_id: str, buf: list[str]) -> Callable[[str], None]:
        def sink(line: str) -> None:
            buf.append(line + "\n")
            with self._lock:
                try:
                    job = self.store.load(job_id)
                    job["log_tail"] = "".join(buf)[-12000:]
                    _parse_log_progress(job, line)
                    self.store.save(job_id, job)
                except FileNotFoundError:
                    pass

        return sink

    def run_candidates_async(self, job_id: str, *, generator: str) -> None:
        def work() -> None:
            try:
                job = self.store.load(job_id)
                job["generator"] = generator
                self.store.update(
                    job_id,
                    phase="candidates_running",
                    progress=5,
                    message="귀여운 캐릭터 만드는 중...",
                    error=None,
                )
                upload = self._resolve_upload(job_id)
                logs: list[str] = []
                detected_species = ""

                # ── Step 1: 일러스트 후보 생성 (count=2) ─────────────────────
                opts_illus = self._options(job, upload)
                opts_illus = PipelineOptions(**{
                    **opts_illus.__dict__,
                    "make_candidates": True,
                    "candidate_count": 2,
                    "art_style": "illustration",
                })
                self.store.update(job_id, progress=10, message="일러스트 스타일 후보 생성 중...")
                res_illus = self.runner.generate_candidates(
                    opts_illus, log=self._log_sink(job_id, logs)
                )
                if res_illus.returncode != 0:
                    self.store.update(
                        job_id,
                        phase="failed",
                        progress=0,
                        message="후보 생성 실패",
                        error=_format_pipeline_error(res_illus.returncode, logs),
                        log_tail="".join(logs)[-12000:],
                    )
                    return

                pkg = res_illus.package_dir
                detected_species = _parse_detected_species("".join(logs))

                # 일러스트 후보 2장 메모리에 백업 (두 번째 run이 덮어쓸 수 있으므로)
                # 파이프라인은 1-based: candidate_01.png, candidate_02.png
                cand_dir = pkg / "character_candidates"
                illus_backup: dict[int, bytes] = {}
                for i in (1, 2):
                    p = cand_dir / f"candidate_{i:02d}.png"
                    if p.is_file():
                        illus_backup[i] = p.read_bytes()

                # ── Step 2: 실사 후보 생성 (count=2) ─────────────────────────
                opts_real = self._options(job, upload)
                opts_real = PipelineOptions(**{
                    **opts_real.__dict__,
                    "make_candidates": True,
                    "candidate_count": 2,
                    "art_style": "realistic",
                })
                self.store.update(job_id, progress=55, message="실사 스타일 후보 생성 중...")
                res_real = self.runner.generate_candidates(
                    opts_real, log=self._log_sink(job_id, logs)
                )

                # ── 파일 배치 (모두 1-based) ──────────────────────────────────
                # 최종: candidate_01,02 = 일러스트 A/B / candidate_03,04 = 실사 A/B
                cand_dir.mkdir(parents=True, exist_ok=True)
                if res_real.returncode == 0:
                    # 실사 후보: candidate_02→04, candidate_01→03 (역순으로 충돌 방지)
                    for src_i, dst_i in [(2, 4), (1, 3)]:
                        src = cand_dir / f"candidate_{src_i:02d}.png"
                        dst = cand_dir / f"candidate_{dst_i:02d}.png"
                        if src.is_file():
                            shutil.move(str(src), str(dst))
                # 일러스트 후보 복원: candidate_01, candidate_02
                for i, data in illus_backup.items():
                    (cand_dir / f"candidate_{i:02d}.png").write_bytes(data)

                # 자동감지 결과를 로그에서 파싱해서 job에 저장
                if not detected_species:
                    detected_species = _parse_detected_species("".join(logs))

                count_ready = sum(
                    1 for i in (1, 2, 3, 4)
                    if (cand_dir / f"candidate_{i:02d}.png").is_file()
                )
                msg = (
                    "후보가 준비되었습니다."
                    if count_ready >= 3
                    else f"후보 {count_ready}장이 준비되었습니다."
                )
                update_kwargs: dict = dict(
                    phase="candidates_ready",
                    progress=100,
                    message=msg,
                    package_dir=str(pkg.resolve()),
                    error=None,
                    log_tail="".join(logs)[-12000:],
                )
                if detected_species:
                    update_kwargs["species_hint"] = detected_species
                self.store.update(job_id, **update_kwargs)

            except Exception as exc:
                self.store.update(
                    job_id,
                    phase="failed",
                    progress=0,
                    message="후보 생성 중 오류",
                    error=str(exc),
                )

        threading.Thread(target=work, daemon=True).start()

    def select_candidate(self, job_id: str, index: int) -> Path:
        job = self.store.load(job_id)
        pkg = _package_dir(job, self.store)
        cand = pkg / "character_candidates" / f"candidate_{index:02d}.png"
        if not cand.is_file():
            raise FileNotFoundError(f"candidate not found: {cand}")
        mgr = CanonicalCharacterManager()
        mgr.set_from_existing_image(
            cand,
            pkg,
            SELECTED_BASE_CANDIDATE_TYPE,
            {
                "original_reference": str(cand.resolve()),
                "candidate_index": index,
                "policy": CANONICAL_BASE_POLICY_KO,
            },
        )
        self.store.update(
            job_id,
            phase="canonical_selected",
            progress=100,
            message="캐논 캐릭터가 고정되었습니다.",
            selected_candidate=index,
            package_dir=str(pkg.resolve()),
        )
        return pkg

    def run_emoticons_async(self, job_id: str, emotions: list[str]) -> None:
        def work() -> None:
            try:
                job = self.store.load(job_id)
                if not job.get("selected_candidate"):
                    raise RuntimeError("먼저 후보를 선택하세요.")
                upload = self._resolve_upload(job_id)
                job_dir = self.store.job_dir(job_id)
                tpl = build_custom_templates(job_dir, emotions)
                job["emotions"] = list(emotions)
                cuts = [
                    {
                        "id": f"{i:02d}",
                        "text": emotions[i - 1] if i - 1 < len(emotions) else "",
                        "status": "pending",
                    }
                    for i in range(1, 17)
                ]
                self.store.update(
                    job_id,
                    phase="emoticons_running",
                    progress=8,
                    message="이모티콘 생성 중...",
                    cuts=cuts,
                    error=None,
                )
                opts = self._options(job, upload)
                opts = PipelineOptions(
                    **{
                        **opts.__dict__,
                        "select_candidate": None,
                        "cut_templates": str(tpl.resolve()),
                        "make_candidates": False,
                    }
                )
                logs: list[str] = []
                res = self.runner.run_emoticon_pipeline(
                    opts, log=self._log_sink(job_id, logs)
                )
                pkg = res.package_dir or _package_dir(job, self.store)
                job = self.store.load(job_id)
                _sync_cuts_from_disk(job, Path(pkg))
                for c in job.get("cuts") or []:
                    if c.get("status") != "done":
                        cid = str(c.get("id", "")).zfill(2)
                        if (Path(pkg) / "png" / f"{cid}.png").is_file():
                            c["status"] = "done"
                self.store.update(
                    job_id,
                    phase="completed" if res.returncode == 0 else "failed",
                    progress=100 if res.returncode == 0 else 0,
                    message="이모티콘 생성이 완료되었습니다." if res.returncode == 0 else "생성 실패",
                    package_dir=str(Path(pkg).resolve()),
                    cuts=job.get("cuts"),
                    error=None
                    if res.returncode == 0
                    else _format_pipeline_error(res.returncode, logs),
                    log_tail="".join(logs)[-12000:],
                )
                # Web Push + SMS 알림 발송
                if res.returncode == 0:
                    job_after = self.store.load(job_id)

                    # Web Push
                    try:
                        push_sub = job_after.get("push_subscription")
                        if push_sub:
                            from factory_web.services.push_notifier import send as push_send
                            push_send(
                                subscription=push_sub,
                                title="🎉 이모티콘 완성!",
                                body="16장이 모두 준비됐어요. 지금 확인해보세요!",
                                url=f"/?job={job_id}",
                            )
                    except Exception as pe:
                        print(f"[push] 알림 발송 중 예외: {pe}")

                    # SMS
                    try:
                        phone = job_after.get("sms_phone")
                        if phone:
                            from factory_web.services.sms_notifier import send as sms_send
                            sms_send(
                                to=phone,
                                text=(
                                    "[이모티콘 스튜디오] 이모티콘 16장 생성 완료! "
                                    f"확인 → https://emoticonfactory.vercel.app/?job={job_id}"
                                ),
                            )
                    except Exception as se:
                        print(f"[sms] 알림 발송 중 예외: {se}")
            except Exception as exc:
                self.store.update(
                    job_id,
                    phase="failed",
                    progress=0,
                    message="이모티콘 생성 중 오류",
                    error=str(exc),
                )

        threading.Thread(target=work, daemon=True).start()

    def _resolve_upload(self, job_id: str) -> Path:
        job = self.store.load(job_id)
        up_dir = self.store.job_dir(job_id) / "uploads"
        # ._* 파일은 exFAT macOS AppleDouble 메타파일 — 실제 이미지 아님
        files = sorted(f for f in up_dir.glob("*.*") if not f.name.startswith("._"))
        if not files:
            raise FileNotFoundError("uploaded image missing")
        return files[0]

    def build_preview_payload(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.load(job_id)
        pkg_s = job.get("package_dir")
        if not pkg_s:
            return None
        pkg = Path(pkg_s)
        meta: dict[str, Any] = {}
        for name in (
            "package_info.json",
            "generation_log.json",
            "consistency_report.json",
            "cut_plan.json",
        ):
            p = pkg / "meta" / name
            if p.is_file():
                try:
                    meta[name.replace(".json", "")] = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
        meta["preview_html_exists"] = (pkg / "preview.html").is_file()
        return meta

    def list_cut_urls(self, job_id: str) -> list[dict[str, Any]]:
        job = self.store.load(job_id)
        pkg_s = job.get("package_dir")
        if not pkg_s:
            return job.get("cuts") or []
        pkg = Path(pkg_s)
        sticker = pkg / "png" if (pkg / "png").is_dir() else pkg / "png_no_text"
        out: list[dict[str, Any]] = []
        for i in range(1, 17):
            cid = f"{i:02d}"
            text = ""
            for c in job.get("cuts") or []:
                if str(c.get("id")) == cid:
                    text = str(c.get("text", ""))
                    break
            p = sticker / f"{cid}.png"
            out.append(
                {
                    "id": cid,
                    "text": text or (job.get("emotions") or [""] * 16)[i - 1],
                    "status": "done" if p.is_file() else "pending",
                    "path": str(p) if p.is_file() else None,
                }
            )
        return out
