# KakaoEmoticonFactory (prototype)

Python CLI that turns **one real pet photo** into a Kakao-style **big emoticon** set: it analyzes a light-weight `PetProfile`, builds a generic `CharacterProfile`, plans 16 cuts, generates **text-free** sticker art (default), **normalizes** to 540×540, draws **Korean captions in Pillow** (not in the AI image by default), exports icons/share, writes `package_info.json` / `meta/prompts.json`, and runs static QA.

### 권장 기본 흐름 (v0.7)

**Input → Base candidates (3) → Select 1 → Canonical character → 16 emoticons**

1. 입력 이미지 1장을 `--character` 로 넣습니다.  
2. **`--make-candidates`** (또는 `--make-canonical-candidates`)로 **베이스 캐릭터 후보 3장**을 만듭니다 (입력 이미지 기준, 시트 없음).  
3. 마음에 드는 1장을 **`--select-candidate N`** 으로 `character/canonical_character.png` 에 고정합니다. (1회성 — 이후 `character_candidates/` 폴더가 없어도 3/16컷 생성 가능)  
4. **`--test-ids "01,02,03"`** 으로 3컷 테스트 후, 전체 16컷을 생성합니다.  
5. 이후 모든 컷은 **canonical_character.png** 만 보고 포즈·표정·소품만 바꿉니다.

`canonical_sheet` / `--make-character-sheet` / `--use-character-sheet` 는 **고급 옵션**이며 기본 UX에는 포함하지 않습니다.

### Reference 입력 타입 (`--reference-type`)

`services/reference_classifier.py` 가 기본 **`auto`** 일 때 `character/reference.png` 를 분석해 **`photo`**(실사) / **`character_art`**(이미 그려진 캐릭터 원본) / **`unknown`** 중 하나로 분류합니다. 결과는 `package_info.json`·`meta/generation_log.json`·`meta/style_log.json`(reference_classification)·`preview.html` 에 반영됩니다.

| 값 | 설명 |
|----|------|
| `auto` | 휴리스틱 자동 판별(알파·배경 단순도·색 수·에지·질감 등). |
| `photo` | 실사로 **강제** — `canonical_reference_policy`에 실사 안내 문구. |
| `character_art` | 캐릭터 아트로 **강제** — `stylizer none` 이고 원본 기준이면 정책 문구 **「이미 캐릭터화된 입력이므로 원본 캐릭터를 직접 기준으로 사용」**, 프롬프트에 스타일 보존·리디자인 금지 문구 추가. |
| `unknown` | 불확실로 **강제** — preview 에 수동 지정 권장. |

**실사 사진 입력 예시**(자동 판별 + mock 스모크):

```powershell
python app.py --character inputs/reference.png --series "우리집 귀찮냥" --theme "사랑" --species-hint cat --overwrite --reference-type auto --stylizer none --generator mock --test-one --make-preview
```

**이미 캐릭터화된 PNG를 넣는 경우**(자동이 오판하면 강제):

```powershell
python app.py --character inputs/my_sticker_character.png --series "내캐" --theme "일상" --overwrite --reference-type character_art --stylizer none --generator mock --test-one --make-preview
```

**Windows 한글 경로**: 출력 폴더·파일 이름에 한글이 포함되어도 동작하도록, OpenCV 디스크 I/O는 `services/image_io.py`의 `cv_imread` / `cv_imwrite`(내부적으로 `numpy.fromfile`·`cv2.imdecode`, `cv2.imencode`·`Path.write_bytes`), Pillow 저장/로드는 메모리 경유 래퍼를 사용합니다. 시리즈명이 한글인 경우에도 **`imread_/imwrite_ 경로 깨짐` 경고 없이** 일관성 검사·후처리·QC가 돌아가야 합니다.

## 설치

```powershell
cd KakaoEmoticonFactory
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Qt GUI (v0.1)

PySide6 기반 **반려동물 이모티콘 생성기** (`gui_app.py`). CLI와 동일하게 `app.py`를 subprocess로 호출합니다.

```powershell
cd KakaoEmoticonFactory
python gui_app.py
```

**CLI 예시 (권장)**

```powershell
# 1) 베이스 후보 3장 — 입력 이미지를 직접 참조해 단순 캐릭터화 (복잡한 정체성 프롬프트 아님)
python app.py --character inputs/reference.png --series "MySticker" --theme "사랑" --make-candidates --candidate-count 3 --generator mock --overwrite
python app.py --character inputs/1_1.png --series "PromptSimpleReal" --theme "사랑" --make-candidates --candidate-count 3 --generator openai --candidate-openai-model gpt-image-1 --candidate-openai-mode auto --overwrite
```

**후보 OpenAI 정책 (`--candidate-openai-mode`)**

| 모드 | 동작 |
|------|------|
| `auto`(기본) | 입력 PNG → `images.edit` 우선. 실패 시 `images.generate` 폴백 + 콘솔/`candidates.json` 경고 |
| `edit` | 이미지 참조만. 폴백 없음 |
| `generate` | 텍스트-only (명시 선택 시만). 드리프트 위험 큼 |

`candidates.json` 각 후보에 `prompt` 전문, `used_image_reference`, `text_only_fallback` 저장. **이미지 참조가 안 되면 품질이 크게 떨어질 수 있음** (고양이→강아지 drift 등).

```powershell

# 2) 후보 확인 후 선택 (예: 2번)
python app.py --character inputs/reference.png --series "MySticker" --theme "사랑" --select-candidate 2 --overwrite

# 3) 3컷 테스트
python app.py --character inputs/reference.png --series "MySticker" --theme "사랑" --select-candidate 2 --generator openai --test-ids "01,02,03" --make-preview --overwrite

# 4) 16컷 전체
python app.py --character inputs/reference.png --series "MySticker" --theme "사랑" --select-candidate 2 --generator openai --make-preview --overwrite
```

**이미 완성된 캐릭터 원본** (`reference_type=character_art`): 후보 3장 대신 입력을 바로 canonical으로 고정하거나, 후보 중 가장 비슷한 1장을 선택하면 됩니다.

**고급 — character sheet** (선택): `--make-character-sheet` + `--use-character-sheet` 는 턴어라운드 시트가 필요할 때만 사용합니다.

### v0.7: Universal Living-Character Pipeline

모든 생물체·캐릭터 원본을 **동일 정체성(identity)** 으로 카카오 이모티콘화합니다. “새 마스코트 창조”가 아니라 **포즈·표정·제스처만 변경**합니다.

- **`services/identity_profile_analyzer.py`**: `entity_type`(human, baby, dog, cat, couple, family, character_art …), trait lock, `meta/identity_profile.json`
- **프롬프트**: `[CRITICAL IDENTITY LOCK]`, living-being 철학, universal trait lock, handcrafted anti-flat
- **일관성 v0.7**: `canonical_identity_score`, `identity_drift_heatmap`, `drift_reason`, `identity_drift_detected`
- **CLI**: `--pose-variation-strength`, `--expression-strength`, `--require-character-sheet`, `--make-canonical-candidates`(= 후보 3장)
- **GUI**: Step 라벨, 입력 타입 자동 분석, canonical 좌측 고정, drift 컷 빨간 테두리·컷별 재생성

```powershell
python app.py --character inputs/photo.png --series "MyDog" --theme "사랑" --make-candidates --select-candidate 2 --generator mock --test-ids "01,02,03" --make-preview --overwrite
```

### v0.6: 일러스트 질감 / anti-flat-AI (`--style-intensity`)

플랫한 generic AI 마스코트 느낌을 줄이기 위해 **수채화·동화책·손그림 질감** 프롬프트 블록과 휴리스틱 **texture drift** 검사를 추가했습니다. **canonical / consistency / regeneration 구조는 그대로**입니다.

| 옵션 | 설명 |
|------|------|
| `--style-intensity 0.0` | 카카오 벡터·플랫 스티커풍 |
| `0.5` (기본) | 기존 균형 |
| `1.0` | 수채화/동화책/프리미엄 반려동물 일러스트 감성 |

- **프롬프트**: `[Illustration texture style]`, `character_art` 직접 canonical 시 texture lock, 시트는 *illustration reference sheet* 문구.
- **일관성**: `identity_similarity` / `texture_similarity` / `style_similarity` + `texture_flattening_detected`.
- **재생성**: 평탄화 감지 시 watercolor/painterly 복원 suffix.
- **후보 3장** (`--make-candidates`): intensity **0.0 / 0.5 / 1.0** 고정 (A/B/C). `character_candidates/candidates.json`에 `style_label` 기록.
- **미리보기**: 컷별 identity · texture · style 유사도 표시.

```powershell
python app.py --character inputs/reference.png --series "TextureTest" --theme "사랑" --reference-type photo --stylizer none --generator mock --style-intensity 0.85 --test-ids "01,02,03" --make-preview --overwrite
```

### v0.5: canonical character sheet (실사 권장)

실사에서 바로 16컷을 만들기 전에 **`character/canonical_sheet.png`** 턴어라운드 시트를 만들고, **`--use-character-sheet`** 로 후보·생성·일관성 검사의 시각 기준을 시트에 맞출 수 있습니다.  
**`--make-character-sheet`** 는 **`--reference-type photo`**(또는 자동 분류가 실사인 경우)에서만 AI/목 시트를 생성합니다. **`character_art`** 이면 기본 동작은 **시트 생략 + `canonical_character.png` 만 고정**이며, 예외적으로 시트를 만들려면 **`--force-character-sheet`** 를 함께 쓰세요(드리프트 경고).

1. 시트 생성(실사 입력 예시):

```powershell
python app.py --character inputs/reference.png --series "SheetRealTest" --theme "사랑" --species-hint cat --reference-type photo --make-character-sheet --sheet-generator openai --sheet-openai-model gpt-image-1 --sheet-openai-mode auto --overwrite
```

2. 시트 기준 후보 3장:

```powershell
python app.py --character inputs/real_cat.png --series "우리집 귀찮냥" --theme "사랑" --species-hint cat --use-character-sheet --make-candidates --candidate-count 3 --generator openai --overwrite
```

3. 후보 선택 + 3컷:

```powershell
python app.py --character inputs/real_cat.png --series "우리집 귀찮냥" --theme "사랑" --species-hint cat --use-character-sheet --select-candidate 2 --generator openai --test-ids "01,02,03" --make-preview --overwrite
```

4. 전체 16컷:

```powershell
python app.py --character inputs/real_cat.png --series "우리집 귀찮냥" --theme "사랑" --species-hint cat --use-character-sheet --select-candidate 2 --generator openai --make-preview --overwrite
```

- **`--make-character-sheet`**: `character_art` 이면 기본적으로 **AI 시트 생략** 후 `canonical_character.png` 만 고정·메타 기록 후 종료. 실사(`photo`)만 시트 PNG+로그 생성.
- **`--force-character-sheet`**: `character_art` + `--make-character-sheet` 일 때만 **강제로** 시트 생성(프리뷰에 드리프트 경고).
- **`--sheet-openai-model`**: OpenAI 시트 전용 모델(기본 `gpt-image-1`). 컷 생성 `--openai-model` 과 별도입니다.
- **`--sheet-openai-mode`**: `auto` 또는 `generate` → `images.generate` 만 사용. `edit` 는 시트 경로에서 지원하지 않으며 명시적 오류로 안내됩니다.
- **`--character-sheet PATH`**: 외부 시트를 `character/canonical_sheet.png` 로 복사.
- **`--overwrite`**: **생성 결과만** 갱신합니다 (`png/`, `generated_raw/`, `preview.html`, `meta`의 generation 로그 등). 기본 보존: `character_candidates/`, `character/canonical_character.png`, `canonical_sheet.png`, `meta/identity_profile.json`.
- **`--reset-candidates`**: `--overwrite`와 함께 `character_candidates/` 삭제.
- **`--reset-canonical`**: `--overwrite`와 함께 `canonical_character.png`·`canonical_character_source.json` 삭제.
- **`--full-reset`**: `outputs/<series>` **폴더 전체 삭제** (이전 `--overwrite` 동작). GUI 「전체 초기화」와 동일.
- **`--drift-threshold`** / **`--strict-drift`**: 일관성 리포트의 휴리스틱 드리프트 판정(기본 0.68). `imagehash` 가 설치되어 있으면 pHash를 보조로 사용합니다.

### CLI: 캐릭터 후보·canonical

- **`--make-candidates`** / **`--candidate-count`** (`character_candidates/candidate_01.png` …, `candidates.json`) 후 종료.
- **`--select-candidate N`**: `candidate_NN.png` → `character/canonical_character.png` 로 고정 후 컷 생성 계속.
- **`--canonical-character PATH`**: 임의 PNG를 canonical 로 복사. **`--overwrite`** 는 후보·캐논을 기본 유지하므로 컷만 다시 돌릴 때 안전합니다.

예시:

```powershell
python app.py --character inputs/reference.png --series "GuiTest" --theme "사랑" --species-hint cat --make-candidates --candidate-count 3 --generator mock --overwrite
python app.py --character inputs/reference.png --canonical-character outputs/GuiTest/character_candidates/candidate_01.png --series "GuiTest" --theme "사랑" --species-hint cat --reference-type character_art --stylizer none --generator mock --test-ids "01,02,03" --make-preview --overwrite
```

### OpenAI 이미지 생성용 환경 변수

API 키는 코드에 넣지 않습니다. 프로젝트 루트(`KakaoEmoticonFactory/`)에 `.env`를 두거나 시스템 환경 변수로만 설정합니다.

1. 예시 파일을 복사합니다: `copy .env.example .env` (또는 수동 생성).
2. `.env`에 실제 키를 넣습니다:

```env
OPENAI_API_KEY=sk-...
```

`app.py`는 시작 시 `load_dotenv()`로 `.env`를 읽습니다. `--generator openai`인데 키가 비어 있으면 **키 설정 방법**과 **`--generator mock` / `--full-pipeline`** 안내가 포함된 메시지로 종료합니다.

`inputs/reference.png`에 캐릭터 참고 이미지를 두고 실행하세요(형식은 PNG 권장).

## 실행

```powershell
cd KakaoEmoticonFactory
python app.py --character inputs/reference.png --series "귀찮냥은 사랑중" --theme "사랑"
# 선택: 참조 이미지 설명(비전 캡션 등)
python app.py --character inputs/reference.png --series "귀찮냥은 사랑중" --theme "사랑" --reference-note "샴 고양이, 파스텔 톤 위주"
```

기존 출력 폴더를 덮어쓰려면:

```powershell
python app.py --character inputs/reference.png --series "귀찮냥은 사랑중" --theme "사랑" --overwrite
```

### 통합 모드(권장, mock 전체 파이프라인 한 번에)

아래는 **스타일 목업·생성 목업·후처리·일관성 검사·자동 재생성·WebP** 까지 순서대로 돌리는 것과 동등합니다. OpenAI 키가 없어도 동작합니다.

```powershell
python app.py --character inputs/reference.png --series "귀찮냥은 사랑중" --theme "사랑" --overwrite --full-pipeline
```

`--full-pipeline`은 내부적으로 다음과 같이 고정합니다: `--stylizer mock --generator mock --postprocess --check-consistency --auto-regenerate --make-webp --make-preview`. 실행이 끝나면 표준 출력에 **v0.7 실행 요약**이 출력됩니다.

### v0.7 실행 요약 (`_print_run_summary`)

종료 시 `========== 실행 요약 ==========` 블록이 stdout에 출력됩니다(GUI는 `PipelineRunner` 로그로 동일 내용 표시).

- **[입력/정체성]**: `reference_type`, `entity_type`, `identity_profile`, `canonical_identity_mode`
- **[기준 이미지]**: canonical / sheet / `generation_reference_*`
- **[AI/생성 백엔드]**: `generator`, `sheet_generator`, `stylizer`, OpenAI 모델, 텍스트 오버레이 방식
- **[스타일]**: `style_intensity`, pose/expression, anti-flat
- **[산출물]**: 패키지 경로, PNG/WebP, `preview.html`
- **[품질/드리프트]**: QC, consistency, `canonical_identity_score` 평균, heatmap, failed cuts

메타는 `meta/package_info.json`, `generation_log.json`, `identity_profile.json`, `consistency_report.json` 등에서 보강합니다.

**[다음 추천 작업]** 은 상황별 분기입니다. 예: `generator_backend==mock` 일 때만 OpenAI 품질 테스트를 권장하고, openai 부분 컷 테스트 후에는 16컷 확장을 안내합니다. **고정 문구 “필요 시 --generator openai”는 더 이상 항상 출력하지 않습니다.**

수동으로 동일 플래그를 모두 적는 예시:

```powershell
python app.py --character inputs/reference.png --series "귀찮냥은 사랑중" --theme "사랑" --overwrite --stylizer mock --generator mock --postprocess --check-consistency --auto-regenerate --make-webp --make-preview
```

브라우저에서 세트를 보려면 출력 폴더의 **`preview.html`** 을 여세요(`--make-preview` 또는 `--full-pipeline` 시 생성).

**실무 권장(OpenAI 생성, 스타일러는 실무 기본 `none`):**

```powershell
python app.py --character inputs/reference.png --series "우리집 귀찮냥" --theme "사랑" --species-hint cat --personality-hint "무심하고 시크하지만 귀여움" --overwrite --stylizer none --generator openai --test-one --make-preview
```

**스타일 통일 실험(`--stylizer openai` — 표준 캐릭터 기준, 드리프트 가능):**

```powershell
python app.py --character inputs/reference.png --series "우리집 귀찮냥" --theme "사랑" --species-hint cat --overwrite --stylizer openai --generator openai --test-one --make-preview
```

**OpenAI Images API로 실제 스티커 이미지를 생성**하려면(비용·시간 발생, `meta/generation_log.json`에 컷별 프롬프트·성공 여부·재시도 로그 기록):

```powershell
python app.py --character inputs/reference.png --series "귀찮냥은 사랑중" --theme "사랑" --overwrite --generator openai
```

- 모델 기본 **`gpt-image-1`**, 요청 크기 기본 **`1024x1024`**(`openai` Python 패키지 + 환경 변수 `OPENAI_API_KEY`).
- **`--openai-mode auto`(기본)**: `gpt-image-1` 은 **`images.generate` 우선**(레퍼런스 편집은 `dall-e-2` 등에서만 시도). `--openai-mode edit|generate` 로 고정 가능.
- 응답은 base64 또는 URL 바이너리를 받아 저장한 뒤 **`ImageProcessor`** 로 **540×540 RGBA** 정규화됩니다. 기본(비-AI 텍스트) 파이프라인에서는 `generated_raw/`·`png_no_text/`·`png/` 를 사용합니다.

**컷 01만 빠르게 검증**(`--test-one`: 일관성·재생성 생략, QC는 생성된 컷만):

```powershell
python app.py --character inputs/reference.png --series "우리집 귀찮냥" --theme "사랑" --species-hint cat --overwrite --stylizer none --generator mock --test-one --make-preview
```

**지정 컷만 생성**(`--test-ids`: `cut_plan`·`prompts`·`package_info`·미리보기 그리드가 선택 컷만 반영; WebP·일관성·자동 재생성은 생략):

```powershell
python app.py --character inputs/reference.png --series "우리집 귀찮냥" --theme "사랑" --species-hint cat --overwrite --stylizer none --generator mock --test-ids "01,02,03" --make-preview
```

OpenAI(키 필요)로 동일 스모크:

```powershell
python app.py --character inputs/reference.png --series "우리집 귀찮냥" --theme "사랑" --species-hint cat --personality-hint "무심하고 시크하지만 귀여움" --overwrite --stylizer openai --generator openai --test-one --make-preview
```

```powershell
python app.py --character inputs/reference.png --series "귀찮냥은 사랑중" --theme "사랑" --overwrite --generator openai --test-one
```

선택 CLI: `--openai-model`(기본 `gpt-image-1`), `--image-size`(기본 `1024x1024`), `--max-retries`(기본 `3`, 컷별 전체 사이클 재시도).  
한 컷이 API에서 실패하면 기본은 **즉시 중단**합니다. 나머지 컷을 계속 시도하려면 `--continue-on-error`를 쓰세요(16컷 미만이면 정적 QC는 실패할 수 있음).

출력 폴더 이름은 시리즈명에서 공백을 `_`로 바꾸고 Windows 금지 문자를 제거한 값입니다  
예: `귀찮냥은 사랑중` → `outputs/귀찮냥은_사랑중/`.

## 캐릭터 원본 표준화

`--character`로 넘긴 이미지는 먼저 `ReferenceProcessor`가 `outputs/<series>/character/` 아래에 정리합니다.

- `character_base.png` — 540×540, 투명 캔버스에 비율 유지·중앙 배치 (이모티콘 제작용 기준)
- `character_base_white.png` — 동일 구도, 흰 배경
- `character_base_transparent.png` — 참조에 **유의미한 알파**가 있을 때만 생성 (없으면 경고만 남김, 파이프라인은 계속)
- `character/reference.png` — 입력 실사의 **패키지 내 복사본**(생성·메타의 공통 원본 앵커)

`CharacterProfile` 은 `PetProfile` 에서 만들어지며 `package_info.json`의 `character_profile` / `pet_profile`에 기록되고, 모든 프롬프트 앞에 일관성 블록으로 붙습니다.

### 스타일 표준화 (`--stylizer`) 정책

| 값 | 용도 | 생성 API(`--generator openai`)가 쓰는 **이미지 기준** |
|----|------|--------------------------------------------------------|
| **`none`**(기본) | 실무 기본 | **`character/reference.png`** + PetProfile 텍스트. `standardized_character.png` 는 기준으로 사용하지 않음. |
| **`openai`** | 실험(스타일 통일 시도) | `OpenAIStyleStandardizer`가 만든 **`character/standardized_character.png`** (실패 시 원본으로 폴백). 원본 대비 캐릭터 드리프트 가능. |
| **`mock`** | 개발·CI용 | **`character/standardized_character_mock.png`** — 품질·정체성 판단 금지. |

- `meta/style_log.json` — 선택한 stylizer 백엔드 요약.
- `meta/style_prompt.txt` — 프로필·규칙·금지사항 등 사람이 읽기 좋은 텍스트.

`package_info.json` / `meta/generation_log.json`에는 `canonical_reference_used`, `canonical_reference_policy`, `stylizer_used_for_generation`, `reference_priority` 등으로 **실제 어떤 파일이 기준인지** 기록됩니다. `preview.html`에도 동일 정책이 요약됩니다.

```powershell
python app.py ... --stylizer none
python app.py ... --stylizer mock
python app.py ... --stylizer openai
```

`MockImageGenerator`·`OpenAIImageGenerator` 모두 **`reference_path`** 로 전달된 파일(위 정책에 따름)을 우선 시각 앵커로 사용합니다.

## 16컷 포즈 플랜 (`BigEmoticonPose`)

`data/big_emoticon_templates.json`은 각 컷마다 **`facial_expression` · `body_pose` · `prop`** 등을 포함합니다. 로드 시 `services/pose_schema.py`의 **`BigEmoticonPose`(Pydantic)** 로 검증됩니다.

- **`layout_type`**: `square_full_body`, `face_closeup`, `half_body`, `lying_pose`, `reaction_burst`
- **`text_position`**: `top`, `bottom`, `left`, `right`, `none`
- 결과는 **`meta/cut_plan.json`**(시리즈·테마·16컷 요약), **`meta/prompts.json`**(컷별 전 필드 + `prompt`)으로 저장됩니다.

`MockImageGenerator`는 **기준 이미지**(원본 복사 또는 mock/openai 표준 시트) 위에 레이아웃 스케일·미러·눕기 회전·소품(박스·테이블·쿠션·하트·번개 등)·표정 오버레이·(옵션) 텍스트 위치를 적용합니다.

## 출력 구조

```
outputs/<safe_series_name>/
  character/
    reference.png                # 입력 실사 복사본(생성·일관성 기준의 기본 앵커)
    character_base.png           # 540×540, 투명 배경 캔버스
    character_base_white.png      # 흰 배경
    character_base_transparent.png  # (조건부) 소스 알파가 있을 때
    standardized_character.png      # (--stylizer openai) API 표준 시트
    standardized_character_mock.png  # (--stylizer mock) 개발용 목업
  png/01.png ... 16.png      # (--postprocess 없음) 540×540 최종 스티커 RGBA
  png_raw/01.png ...         # (--postprocess 시) 정규화 원본(후처리 전)
  processed/01.png ...       # (--postprocess 시) 휴먼라이즈 후처리본 (기본 패키지 경로)
  webp/                     # (--make-webp) 움직이는 WebP(기본 3컷: 01·03·10)
  icon/01.png ... 16.png     # 78x78 RGBA
  share/share.png            # 600x166 RGBA
  meta/
    package_info.json        # 선택: animated_items(WebP 컷별 경로 메타)
    cut_plan.json            # 검증된 16컷 포즈 플랜(JSON)
    prompts.json             # 컷별 pose 필드 + 생성 프롬프트
    generation_log.json      # (--generator openai 시) 컷별 시도·소요 시간·usage 요약
    webp_report.json         # (--make-webp) WebP별 프레임·용량·애니메이션 종류 등
    consistency_report.json  # (--check-consistency 기본) 컷별 일관성 점수·이슈(JSON)
    regeneration_log.json    # (--auto-regenerate) 일관성·QC 기반 재생성 배치 요약
    regeneration_attempts/   # 컷별 재생성 전 백업 PNG + 프롬프트 보조 메타
    reference.png            # 입력 캐릭터 이미지 복사본
    style_prompt.txt         # 스타일 표준화용 텍스트(캐릭터 설명·규칙·금지 등)
  failed/                    # (--generator openai) 실패한 컷의 오류 메타(JSON)
    01_error.json ...
  failed_consistency/        # 일관성 임계값 미달 컷 PNG 복사본
    03.png ...
```

## 이미지 생성 백엔드 (`--generator`)

- **`mock`**(기본): `MockImageGenerator` — Pillow로 목업 스티커. API 없음.
- **`openai`**: `OpenAIImageGenerator` — `OPENAI_API_KEY` 필요. **`--stylizer none`**(기본)이면 **`character/reference.png`** + PetProfile을 우선 참조합니다. **`--stylizer openai`** 이면 **`standardized_character.png`** 를 시각적 기준으로 사용합니다. `gpt-image-1` 등 모델에 따라 **`images.generate` 우선**·`images.edit` 제한은 `meta/generation_log.json`에 기록됩니다.

스타일 표준화 전용 **`OpenAIStyleStandardizer`** 는 `--stylizer openai` 일 때만 호출됩니다(실험 옵션).

환경 변수는 `python-dotenv`로 `app.py`에서 `load_dotenv()` 합니다. 키는 코드에 넣지 마세요.

## 캐릭터 일관성 검사 (v0.3, `QualityChecker`와 별개)

생성된 16장의 `png/*.png`를 **이번 실행에서 선택된 기준 이미지**(대개 `character/reference.png`, 또는 `--stylizer openai|mock` 일 때 표준 시트)와 비교하는 **이미지·휴리스틱** 검사입니다. OpenCV로 전경 마스크(알파), 바운딩 박스, 평균 색상, 어두운 얼굴 마스크·파란 눈 후보 비율, 투명 배경 비율, 에지/라플라시안 기반 텍스처 복잡도를 계산합니다.

- 기본 **`--check-consistency`**: 검사 실행, `meta/consistency_report.json` 저장, 미통과 컷은 `failed_consistency/<id>.png`로 복사. **`QualityChecker`(해상도·파일 크기 등)** 과는 독립입니다.
- **`--no-check-consistency`**: 검사 생략.
- **`--consistency-threshold`**: 기본 `0.72` — 컷별 점수가 이 값 미만이면 `fail`로 분류.
- **`--strict-consistency`**: 한 컷이라도 미통과면 종료 코드 **9**(그래도 `share`/`package_info`/정적 QC는 먼저 수행되어 폴더를 열어볼 수 있음).

**한계:** 포즈·소품·한글 자막 위치에 따라 색/에지 분포가 달라 **오탐·미탐**이 날 수 있습니다. `CharacterConsistencyChecker`는 추후 **Vision API·CLIP 유사도** 등으로 교체하기 쉽게 모듈로 분리되어 있습니다.

### 실패 컷 자동 재생성 (`--auto-regenerate`)

- **`--auto-regenerate`**: (1) 일관성 검사 `--check-consistency`가 켜져 있으면, 실패 컷만 대상으로 `RegenerationManager`가 재생성(배치 루프, 기본 **`--max-regenerate-attempts 2`**) → 매 배치 후 전체 재검사 → `meta/consistency_report.json` 갱신 · `failed_consistency/` 반영. (2) 이후 정적 **`QualityChecker`**에서 **컷 단위**(대표 스티커/아이콘 규격·용량 등) 오류가 있으면, 남은 재생성 할당량으로 동일 파이프라인을 한 번 더 돌립니다(재생성 후 `share.png`·`package_info.json` 재작성 및 QC 재실행).
- **`--max-regenerate-attempts`**: 일관성 단계와 품질 단계가 **같은 상한을 공유**합니다(먼저 쓴 쪽에서 소진).
- 재생성 시 이슈 문자열을 코드로 매핑해 `PromptBuilder`에 **`[Prompt fix] ...`** 접미 문구를 붙이고, `meta/prompts.json` 및 `package_info` 항목의 `prompt`·`prompt_regeneration_history`를 갱신합니다. 이전 PNG는 `meta/regeneration_attempts/<id>/batchN_before.png` 등에 보관합니다.
- **`--generator mock`**: 재생성해도 합성 로직이 거의 동일해 **점수 개선이 제한적**일 수 있습니다. **OpenAI 이미지 생성**과 함께 쓸 때 의미가 큽니다.
- 무한 루프는 없으며, 배치 횟수는 `max_regenerate_attempts`로 상한 고정입니다.

### 사람이 손댄 듯한 후처리 (`--postprocess`)

AI 이미지의 잔노이즈·실사 느낌·알파 찌꺼기 등을 줄이기 위한 **보수적** 파이프라인입니다(Pillow + OpenCV). 전역 강블러는 피하고, 알파 모폴로지·이중선형 완화, 양방향 필터, 선택적 색 수 축소, 채도·대비 미세 조정, 약한 샤픈, 실루엣 기반 외곽 강조 후 **PNG optimize** 저장합니다.

- **`--postprocess`**: `png_raw/` 에 540×540 정규화 **원본**, `processed/` 에 후처리본을 둡니다(둘 다 16장 채워질 때 각각 존재).
- **`--postprocess-strength`**: 기본 `0.45` (0≈복사만, 1에 가까울수록 단순화·대비 영향 증가). **너무 크면** 디테일·합성 텍스트 획이 손상될 수 있습니다(자동 텍스트 검출 없음 → 과한 블러도 사용하지 않음).
- **`--use-processed-for-package`**(기본) / **`--no-use-processed-for-package`**: 패키지 `items[].png`, 아이콘 `create_icon` 입력, **`QualityChecker`의 스티커 검사 디렉터리**가 `processed/` 인지 `png_raw/` 인지 선택합니다.

```powershell
python app.py ... --overwrite --generator openai --postprocess --postprocess-strength 0.45
```

## 움직이는 WebP (v0.4, 카카오 제안용 사전 검토·프로토타입)

큰 이모티콘 제안 시 **움직이는 WebP 최소 3개**가 필요합니다. 본 레포의 `services/webp_animator.py`는 **Pillow만**으로 간단 프리셋(heart_pop · bounce · sleep 등)과 용량·프레임 상한 처리를 제공합니다.

- **카카오 제출 전에는** 카카오에서 권장하는 **전용 WebPAnimator**(또는 공식 검수 도구)로 최종 변환·검수하는 것을 권장합니다. 여기서 만든 WebP는 **사전 검토·프로토타입 용도**입니다.
- 기본 해상도 **540×540**, 루프 **4회**, 프레임 **24 이하**(내부에서 예산 초과 시 품질·프레임수로 자동 축소), 파일 **1MB 이하**를 목표로 `optimize_webp` 경로에서 맞춥니다.
- **마지막 프레임**은 카카오 썸네일 규격에 맞춰 **해당 컷의 정지 PNG(소스)와 동일**하게 둡니다(애니메이션 프레임 뒤에 소스를 append).

```powershell
python app.py --character inputs/reference.png --series "귀찮냥은 사랑중" --theme "사랑" --overwrite --make-webp
# 선택: animated 항목 개수 3(기본)~4 `--webp-count`, 품질 `--webp-quality`(기본 85)
```

- 기본 매핑: **01 사랑해** → heart_pop · **03 안아줘** → bounce · **10 잘자** → sleep. `--webp-count 4`이면 **04**에 blink 추가.
- 결과: `webp/*.webp`, `meta/webp_report.json`, `package_info.json`의 **`animated_items`**. 정적 **`QualityChecker`** 에서 선언된 WebP도 규격·용량 검사합니다.

## 카카오 “큰 이모티콘” 규격 요약(프로토타입 기준)

이 레포는 개발 편의를 위해 대표적인 정적 PNG 제약을 상수로 두고 검사합니다.

- 큰 이모티콘(스티커) PNG: **540×540**, **RGBA**, 용량 예산 **1MB 이하**(설정: `MAX_EMOTICON_BYTES`)
- 아이콘 PNG: **78×78**, **RGBA**, 용량 예산 **16KB 이하**(설정: `MAX_ICON_BYTES`)
- 공유 이미지 PNG: **600×166**, **RGBA**, 용량 예산 **500KB 이하**(설정: `MAX_SHARE_BYTES`)
- (선택) 움직이는 WebP: **`--make-webp`** 시 **540×540**, **≤24 프레임**, **≤1MB**(설정: `MAX_WEBP_ANIM_BYTES` 등), `package_info.animated_items`와 QC 연동

**주의:** 실제 심사/스토어 정책은 시점별로 변할 수 있으니 최신 공식 가이드를 반드시 확인하세요. 이 프로젝트의 `QualityChecker`는 완전한 제출 검수를 대체하지 않습니다.

## 주의사항

- **`--make-webp`** 로 생성하는 WebP는 **사전 검토·프로토타입** 용이며, 최종 제출물은 **카카오 권장 WebPAnimator·공식 가이드**로 다시 다듬는 것을 권장합니다.
- `MockImageGenerator`는 API 없이 Pillow로 임시 그림을 그립니다. `--generator openai`는 과금 API를 호출합니다.
- 한글 경로/파일명은 `pathlib.Path`와 UTF-8 입출력을 사용해 Windows에서도 동작하도록 작성했습니다.
