# Node Reference

이 문서는 `ComfyUI_AOG` 공개 노드를 기능 단위로 설명합니다.

## 1. 번들 / 로더 노드

### `AOG MMAudio Feature Bundle`

영상 특징 추출용 MMAudio 의존성을 한 번에 묶어 로드합니다.

주요 용도:

- `AOG Video Feature Extract`에 필요한 feature utils 공급
- authoring 보강용 MMAudio cue 준비

대표 출력:

- `mmaudio_featureutils`

### `AOG MMAudio SFX Bundle`

MMAudio SFX 생성에 필요한 모델과 feature utils를 묶어 로드합니다.

주요 용도:

- `AOG SFX Compose`에 필요한 `mmaudio_model`
- `AOG SFX Compose`에 필요한 `mmaudio_featureutils`

대표 출력:

- `mmaudio_featureutils`
- `mmaudio_model`

### `AOG QwenVL Bundle`

QwenVL 분석 노드와 authoring 노드가 공통으로 쓸 설정 번들입니다.

주요 용도:

- 영상 의미 분석
- prompt/lyrics/SFX prompt 작성
- music plan 작성

대표 출력:

- `qwenvl_bundle`

### `AOG Quality Preset`

빠른 테스트용 품질 프리셋입니다.

주의:

- shipped workflow에서는 사용하지 않거나 최소화하는 편이 좋습니다.
- 최종 품질 점검은 `Compose` 노드의 실제 위젯 값을 직접 조정하는 방식이 더 명확합니다.

## 2. 입력 적응 노드

### `AOG Load Video Frames`

파일 경로에서 직접 비디오를 읽어 `AOG_VIDEO_BATCH`를 만드는 보조 노드입니다.

권장 용도:

- CLI식 테스트
- 외부 경로 기반 자동화

### `AOG Workflow Video Batch Adapter`

워크플로우 내부 비디오/메타를 AOG 계약으로 변환합니다.

### `AOG VHS Video Batch Adapter`

`VHS_LoadVideo` 출력 계약을 `AOG_VIDEO_BATCH`로 바꿉니다.

가장 많이 쓰는 입력 경로:

1. `VHS_LoadVideo`
2. `AOG VHS Video Batch Adapter`

이 조합이 shipped workflow와 cookbook의 기본입니다.

## 3. 분석 / authoring 노드

### `AOG Video Feature Extract`

비디오 프레임에서 AOG용 구조화 특징을 만듭니다.

역할:

- summary 생성
- structured timeline 생성
- semantic cue 생성
- latent-derived structure cue 생성

대표 출력:

- `video_features`
- `summary_json`

### `AOG QwenVL Semantic Extract`

QwenVL을 사용해 영상 의미 분석 텍스트를 뽑습니다.

언제 쓰나:

- prompt/lyrics를 영상 의미와 더 강하게 맞추고 싶을 때
- 장면 설명을 summary JSON에 남기고 싶을 때

대표 출력:

- `scene_analysis`
- `summary_json`

### `AOG Prompt Draft`

ACE-Step용 프롬프트를 작성합니다.

지원 모드:

- `human`
- `llm`

주요 특징:

- `llm_provider = qwenvl | local_qwen`
- prompt 결과를 노드 UI에 표시
- summary JSON에 prompt 텍스트와 prompt 요약을 남김

대표 출력:

- `prompt_text`
- `summary_json`

### `AOG Lyrics Draft`

ACE-Step용 가사를 작성합니다.

지원 모드:

- `human`
- `llm`

주요 특징:

- `lyrics_language` 지원
- `authoring_language`와 분리 가능
- lyrics 결과를 노드 UI에 표시
- summary JSON에 lyrics 텍스트와 lyrics 요약을 남김

대표 출력:

- `lyrics_text`
- `summary_json`

### `AOG Music Plan`

영상 기반으로 음악 메타를 정합니다.

결정 항목:

- `bpm`
- `duration`
- `timesignature`
- `ace_language`
- `keyscale`

정책:

- `duration`은 입력 영상 길이 기준
- `plan_mode = llm`이면 나머지 항목은 LLM이 결정
- `plan_mode = human`이면 수동 값 사용

대표 출력:

- `bpm`
- `duration`
- `timesignature`
- `ace_language`
- `keyscale`
- `summary_json`

## 4. 생성 노드

### `AOG ACE-Step Compose`

ACE-Step으로 음악을 생성합니다.

핵심 입력:

- `model`
- `clip`
- `vae`
- `video_features`
- `prompt_text`
- `lyrics_text`
- `bpm`
- `duration`
- `timesignature`
- `ace_language`
- `keyscale`

직접 조절 가능한 주요 품질 파라미터:

- `generate_audio_codes`
- `text_cfg_scale`
- `temperature`
- `top_p`
- `top_k`
- `min_p`
- `steps`
- `cfg`
- `sampler_name`
- `scheduler`
- `denoise`

대표 출력:

- `audio`
- `summary_json`

### `AOG SFX Compose`

MMAudio 기반 SFX를 생성합니다.

지원 모드:

- `sfx_prompt_mode = human`
- `sfx_prompt_mode = llm`

LLM provider:

- `qwenvl`
- `local_qwen`

직접 조절 가능한 주요 품질 파라미터:

- `steps`
- `cfg`
- `seed`
- `gain`

대표 출력:

- `audio`
- `summary_json`

## 5. 후처리 / 출력 노드

### `AOG Final Audio Mix`

ACE-Step 오디오와 SFX 오디오를 최종 믹스합니다.

역할:

- music-only 믹스
- sfx-only 믹스
- full 믹스

대표 출력:

- `final_audio`
- `summary_json`

### `AOG Merge Summary JSON`

여러 단계 summary를 하나의 JSON 문자열로 병합합니다.

언제 쓰나:

- final summary JSON에
  - video 분석
  - prompt
  - lyrics
  - music plan
  - ACE
  - SFX
  - final mix
  - preview
  를 함께 남기고 싶을 때

대표 출력:

- `summary_json`

### `AOG Save Summary JSON`

summary JSON 문자열을 실제 파일로 저장합니다.

대표 출력:

- `summary_json`

### `AOG Mux Video Audio`

최종 오디오를 비디오에 mux합니다.

언제 쓰나:

- GUI preview와 별개로, 명시적 mux 파일을 만들고 싶을 때

### `AOG Preview Video Combine`

저장 + preview summary + 결과 파일명 반환을 담당합니다.

실무 팁:

- GUI에서 즉시 보이는 preview는 `VHS_VideoCombine`를 병렬로 함께 쓰는 편이 안정적입니다.
- `AOG Preview Video Combine`는 저장과 메타 정리에 계속 유용합니다.
