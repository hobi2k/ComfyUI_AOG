# ComfyUI_AOG Project Plan

## 1. 프로젝트 개요

`ComfyUI_AOG`는 애니메이션 오프닝 전용 생성 파이프라인 프로젝트다.
프로젝트의 기본 전략은 아래와 같다.

1. 먼저 CLI 전용 파이프라인을 ComfyUI와 독립적으로 구현한다.
2. CLI에서 검증된 데이터 계약과 생성 단계를 ComfyUI workflow로 옮긴다.
3. 반복되거나 도메인 특화된 로직은 ComfyUI 커스텀 노드로 캡슐화한다.

이번 기획의 핵심 판단은 다음과 같다.

1. 기본 영상 생성 엔진은 `Wan 2.2 i2v`로 잡는다.
2. `Wan 2.2 s2v`는 메인 엔진이 아니라 영상 길이 확장 또는 특정 구간 보강용으로 사용한다.
3. 장면 연결은 마지막 프레임 기반 chaining을 기본 전략으로 한다.
4. 음악은 `Ace Step`으로 생성하고, 보컬이 필요한 경우 `Ace Step voice clone` 기반으로 음색을 지정한다.
5. 영상 먼저 생성 후 음악 생성, 또는 음악 먼저 생성 후 영상 생성 둘 다 가능한 구조로 만든다.
6. 화면비, 출력 포맷, 모델 경로는 모두 설정 파일에서 지정 가능하게 한다.
7. 장기적으로는 `SVI LoRA`를 사용해 1분 길이 오프닝까지 확장 가능하게 설계한다.
8. CLI는 외부 workflow 래퍼가 아니라 독립 실행 본체로 설계한다.
9. 비디오 런타임은 `sageattention` 사용 여부와 fallback attention 전략을 명시적으로 설정 가능해야 한다.
10. 1차 구현의 `run` 명령은 최종적으로 local python executor를 통해 실제 모델 추론과 export까지 수행해야 한다.

구현 방향의 상세 원칙은 [CLI-First Architecture](/home/hosung/pytorch-demo/ComfyUI_AOG/docs/CLI_FIRST_ARCHITECTURE.md) 문서를 따른다.

이 문서는 "무엇을 만들 것인가"보다 "어떻게 구현할 것인가"를 중심으로 정리한다.

---

## 2. 최종 목표

사용자가 아래 정보를 주면 애니메이션 오프닝 영상을 자동으로 제작하는 시스템을 만든다.

- 캐릭터가 포함된 이미지
- 텍스트 설명
- 길이
- 화면비
- 출력 포맷
- 영상/음악 생성 순서
- Wan 2.2 모델 경로
- Ace Step 모델 및 voice clone 경로

최종 시스템은 아래를 수행해야 한다.

- 샷 구조 계획
- Wan 2.2 i2v 기반 샷 생성
- 마지막 프레임 기반 연속성 유지
- 필요 시 s2v 기반 길이 확장
- Ace Step 기반 음악 생성
- 필요 시 voice clone 기반 보컬 생성
- 최종 영상/음악 sync 및 export

---

## 3. 핵심 요구사항

### 3.1 입력 요구사항

- 캐릭터 단독 이미지가 아니라 캐릭터가 담긴 일반 이미지를 입력으로 받을 수 있어야 한다.
- 이미지가 1장만 있어도 시작 가능해야 한다.
- 텍스트 설명을 같이 받아 conditioning에 사용할 수 있어야 한다.
- 화면비를 사용자가 지정할 수 있어야 한다.
- 출력 포맷을 사용자가 지정할 수 있어야 한다.
- 모델 경로를 사용자가 직접 지정할 수 있어야 한다.

### 3.2 영상 생성 요구사항

- 기본 생성은 `Wan 2.2 i2v`를 사용한다.
- 샷과 샷 사이는 last-frame chaining으로 연결한다.
- 긴 구간 또는 특정 구간 확장은 `Wan 2.2 s2v`를 사용 가능하게 한다.
- 1분 영상은 한 번에 만들지 않고 짧은 블록을 이어 붙이는 구조로 설계한다.

### 3.3 음악 생성 요구사항

- `Ace Step`으로 오프닝용 음악 생성이 가능해야 한다.
- instrumental만 생성하는 모드가 있어야 한다.
- `Ace Step voice clone`을 사용해 보컬 음색을 지정하는 모드가 있어야 한다.
- 영상 기준으로 음악을 생성하는 `video-first` 흐름이 가능해야 한다.
- 음악 기준으로 영상 구조를 짜는 `music-first` 흐름이 가능해야 한다.

### 3.4 시스템 요구사항

- CLI에서 전 과정을 headless로 실행할 수 있어야 한다.
- 같은 파이프라인을 ComfyUI workflow로 재현할 수 있어야 한다.
- 반복 로직은 커스텀 노드로 분리해 workflow 복잡도를 줄여야 한다.
- CLI는 node-by-node 실행 결과를 JSON manifest로 저장할 수 있어야 한다.
- CLI는 최소한 `validate -> plan -> run` 세 단계로 분리되어야 한다.
- `run`은 최종적으로 local python executor를 통해 실제 모델 추론과 export를 수행해야 한다.
- manifest와 job 파일은 workflow 이식과 디버깅을 위한 보조 산출물로 유지한다.

### 3.5 예제 설정과 placeholder 자산

- `examples/` 아래 YAML의 이미지, 가사, voice clone 경로는 샘플 placeholder를 포함할 수 있다.
- placeholder 경로는 문서와 스키마 예시용으로는 허용한다.
- 실제 렌더 실행 전에는 별도 validation 단계에서 존재 여부를 검사한다.
- 즉, `schema validation`과 `runtime asset validation`은 분리한다.

### 3.6 extension 이미지 입력 방식

- 영상 extension 시 다음 샷 입력은 `last_frame`을 사용할 수 있어야 한다.
- 또는 사용자가 지정한 `custom_image`를 다음 extension 입력으로 사용할 수 있어야 한다.
- 이 선택은 설정 파일에서 shot 전역 기본값으로 지정하고, 추후 shot 단위 override가 가능하게 설계한다.

---

## 4. 핵심 판단

### 4.1 왜 i2v를 메인으로 잡는가

이 프로젝트의 중심 문제는 "오디오를 따라 반응하는 한 장면 생성"이 아니라 "여러 샷을 설계하고 연결해 오프닝을 만드는 것"이다.
따라서 아래가 중요하다.

- 시작 이미지를 바로 샷으로 만들 수 있어야 한다.
- 샷 단위 제어가 쉬워야 한다.
- 마지막 프레임을 다음 샷의 입력으로 넘기기 쉬워야 한다.
- 짧은 샷을 여러 개 이어 붙이는 orchestration이 쉬워야 한다.

이 기준에서는 `Wan 2.2 i2v`가 가장 직접적이다.

### 4.2 s2v를 어떻게 쓰는가

`Wan 2.2 s2v`는 메인 샷 생성기가 아니라 보조 확장기로 본다.

적합한 사용 위치:

- 이미 만들어진 샷 뒤에 길이를 조금 더 붙이고 싶을 때
- 음악 구간에 맞춰 움직임을 더 길게 유지하고 싶을 때
- 특정 구간에서 오디오 구동형 움직임이 더 자연스러울 때

즉 구조는 `i2v main + s2v extension`이다.

### 4.3 음악 생성은 어떻게 접근하는가

1차 구현에서는 영상 분석용 LLM을 필수로 두지 않는다.
대신 샷 생성 시 이미 알고 있는 메타데이터를 음악 계획에 재사용한다.

예:

- 샷 길이
- 샷 타입
- 에너지 태그
- 전환 시점
- 장면 수
- climax 구간

이 정보를 바탕으로 Ace Step용 `music plan`을 만든다.

---

## 5. 지원 모드

### 5.1 Video-First Mode

흐름:

1. 입력 이미지와 텍스트로 샷 플랜을 만든다.
2. Wan 2.2 i2v로 샷을 생성한다.
3. 각 샷의 마지막 프레임을 다음 샷 입력으로 사용한다.
4. 필요 시 일부 샷은 s2v로 길이를 확장한다.
5. 샷 메타데이터를 기반으로 music plan을 만든다.
6. Ace Step으로 instrumental 또는 vocal 포함 트랙을 생성한다.
7. 최종 합성과 export를 수행한다.

장점:

- 오프닝 시각 구조를 먼저 고정할 수 있다.
- continuity 제어가 쉽다.
- 샷 단위 디버깅이 쉽다.

### 5.2 Music-First Mode

흐름:

1. Ace Step으로 음악을 먼저 생성한다.
2. BPM, 섹션, 에너지 포인트를 추출한다.
3. 이 정보를 기반으로 샷 플랜을 만든다.
4. Wan 2.2 i2v로 샷을 생성한다.
5. 필요 시 s2v로 일부 구간을 늘린다.
6. 최종 sync를 맞추고 export한다.

장점:

- 박자와 컷 포인트를 맞추기 쉽다.
- 음악 중심 오프닝 구조에 적합하다.

### 5.3 Vocal Mode

별도 독립 모드라기보다 음악 생성 시 붙는 옵션이다.

흐름:

1. instrumental 구조를 생성한다.
2. voice clone 설정을 로드한다.
3. 가사, 멜로디, 보컬 스타일 조건을 적용한다.
4. vocal stem과 instrumental stem을 별도로 생성 또는 출력한다.
5. 최종 mix에서 합친다.

---

## 6. 전체 파이프라인 흐름

```text
Input Assets
  -> Config Parse
  -> Mode Select
  -> Shot Planning
  -> I2V Shot Generation
  -> Last Frame Extract
  -> Next Shot Conditioning
  -> Optional S2V Extension
  -> Music Plan Build
  -> Ace Step Music Generate
  -> Optional Voice Clone Vocal Generate
  -> Final Sync
  -> Export
```

---

## 7. 단계별 설계

### 현재 구현 상태

현재 구현은 다음 단계까지 진행되어 있다.

- CLI config/schema/manifest 계층
- validate / plan / run 명령 분리
- shot / extension / music / execution plan 생성
- local runtime 부트스트랩 계층 추가
- Wan / Ace Step direct-call wrapper 초안 추가

아직 남은 핵심 구현은 다음과 같다.

- 실제 Wan 2.2 shot 생성 검증
- 실제 Ace Step 오디오 생성 검증
- chaining 및 최종 export 검증

즉 현재는 `local runtime이 연결된 CLI`를 실제 추론 안정화 단계로 다듬는 구간이다.

### Step 1. Input Assets

입력 예시:

- 캐릭터가 포함된 이미지
- 추가 레퍼런스 이미지
- 텍스트 설명
- 타이틀 텍스트
- 프로젝트 YAML
- voice clone용 참조 데이터

### Step 2. Config Parse

설정 파일에서 아래를 읽는다.

- 프로젝트 이름
- 길이
- 화면비
- 출력 포맷
- 실행 모드
- Wan 2.2 i2v 모델 경로
- Wan 2.2 s2v 모델 경로
- Ace Step 모델 경로
- voice clone 경로 또는 clone ID

모델은 단일 파일이 아니라 bundle 단위로 읽는다.

예:

- Wan: high/low UNet, VAE, text encoder, clip vision, optional LoRA
- Ace Step: diffusion model, dual text encoder, VAE, optional voice clone
- Postprocess: upscale model, frame interpolation model

### Step 3. Shot Planning

출력 예시:

- scene list
- shot duration
- transition point
- prompt fragments
- energy curve
- extension-needed flag

### Step 4. I2V Shot Generation

기본 전략:

- 첫 샷은 입력 이미지에서 시작
- 이후 샷은 이전 샷 마지막 프레임에서 시작
- 샷별 prompt는 공통 prompt와 샷별 prompt를 조합

### Step 5. Last Frame Chaining

각 샷 종료 후 마지막 프레임을 추출한다.
이 프레임은 다음 샷 입력 또는 continuity reference로 사용한다.

### Step 6. Optional S2V Extension

s2v는 아래 조건에서만 사용한다.

- 샷 길이를 음악 구간에 맞춰 더 늘려야 할 때
- 움직임이 더 길게 유지되어야 할 때
- 별도 오디오 구동형 확장이 유리한 구간일 때

즉, s2v는 모든 샷에 쓰지 않는다.
또한 extension 입력 이미지는 아래 중 하나를 사용한다.

- `last_frame`
- `custom_image`

### Step 7. Music Plan Build

영상 또는 오디오 메타데이터를 바탕으로 아래를 만든다.

- total duration
- section map
- tempo target
- hit points
- energy curve
- ending style

### Step 8. Ace Step Music Generate

출력 가능 타입:

- instrumental only
- vocal included
- separate stems

### Step 9. Optional Voice Clone Vocal Generate

voice clone 사용 시 아래를 처리한다.

- voice clone 설정 로드
- singer identity 지정
- lyric timing 정렬
- vocal style 조건 적용
- vocal stem 생성

### Step 10. Final Sync

최종 단계에서 아래를 수행한다.

- 영상 길이 미세 조정
- 음악 시작점 조정
- vocal/instrumental 정렬
- 자막/타이틀 오버레이
- format별 export 옵션 적용

---

## 8. 모델 전략

### 8.1 영상 모델

기본:

- `Wan 2.2 i2v`

보조:

- `Wan 2.2 s2v`

원칙:

- i2v는 샷 생성
- s2v는 길이 확장

### 8.2 음악 모델

기본:

- `Ace Step`

보컬 옵션:

- `Ace Step voice clone`

원칙:

- instrumental과 vocal을 논리적으로 분리
- vocal은 가능하면 stem 단위로 다루기

### 8.3 모델 경로 관리

모델 경로는 전부 설정 파일에서 받는다.

필수 관리 대상:

- video i2v model path
- video s2v model path
- video model format
- audio model path
- voice clone path or clone id
- runtime backend

---

## 9. 1차 MVP 범위

- 길이: 10초~20초
- 화면비: 설정 가능
- 출력 포맷: `mp4`, `webm`
- 입력 이미지: 1장 이상
- 영상 생성: `Wan 2.2 i2v`
- 길이 확장: 선택적 `Wan 2.2 s2v`
- 음악 생성: `Ace Step`
- 보컬: 선택적 `voice clone`
- 실행 모드:
  - `video-first`
  - `music-first`

MVP 완료 기준:

- 설정 파일 하나로 end-to-end 실행 가능
- 샷별 영상 저장 가능
- 마지막 프레임 chaining 동작
- 음악 생성 동작
- mp4/webm export 동작

---

## 10. 1분 영상 확장 전략

1분 영상은 아래 방식으로 접근한다.

1. 5초~10초 단위 블록으로 나눈다.
2. 각 블록은 i2v 중심으로 생성한다.
3. 필요한 블록만 s2v로 길이를 늘린다.
4. 블록 간 continuity는 last-frame chaining과 `SVI LoRA`로 보강한다.
5. 전체 블록을 음악 구조에 맞게 조합한다.

즉, 1분 영상은 "한 번에 1분 생성"이 아니라 "짧은 블록 생성 + 확장 + 연결"로 푼다.

---

## 11. 구현 우선순위

### Phase 1. CLI MVP

목표:

- 전체 orchestration과 입출력 계약을 먼저 고정한다.

구현 항목:

1. 프로젝트 YAML 스키마 정의
2. 모델 경로 해석기
3. 입력 이미지/텍스트 로더
4. shot planner
5. output/export 설정 처리

### Phase 2. I2V Runner

목표:

- Wan 2.2 i2v 기반 샷 생성 경로를 붙인다.

구현 항목:

1. 첫 샷 생성
2. 마지막 프레임 추출
3. 다음 샷 chaining
4. shot-level 결과 저장

### Phase 3. Music Runner

목표:

- Ace Step 생성 및 sync 경로를 붙인다.

구현 항목:

1. music plan builder
2. video-first 음악 생성
3. music-first planning
4. sync 조정

### Phase 4. Voice Clone Runner

목표:

- 보컬 음색 지정 경로를 추가한다.

구현 항목:

1. clone config loader
2. clone reference path 처리
3. vocal stem 생성
4. instrumental/vocal mix 정리

### Phase 5. S2V Extension

목표:

- 필요한 샷만 길이를 확장할 수 있게 한다.

구현 항목:

1. extension-needed 판정
2. s2v extension path 연결
3. extension 결과를 기존 shot chain에 병합

### Phase 6. ComfyUI Workflow

목표:

- CLI에서 검증한 흐름을 workflow로 옮긴다.

구현 항목:

1. i2v shot workflow
2. last-frame extractor
3. optional s2v extension workflow
4. manifest 기반 실행

### Phase 7. Custom Nodes

목표:

- 반복 로직을 커스텀 노드로 옮긴다.

우선 후보:

1. `AOGProjectConfigLoader`
2. `AOGWanModelConfig`
3. `AOGShotPlanBuilder`
4. `AOGLastFrameExtractor`
5. `AOGShotChainBuilder`
6. `AOGAceStepPromptBuilder`
7. `AOGAceVoiceCloneResolver`
8. `AOGExportConfig`

### Phase 8. Node-Based CLI Validation

목표:

- 각 처리 단계를 파이썬 노드 실행 파일로 쪼개고 CLI에서 순차 실행한다.

구현 항목:

1. YAML loader
2. asset validation node
3. model bundle resolution node
4. shot planning node
5. extension source resolution node
6. output manifest writer

완료 기준:

- 실제 생성 이전에도 파이프라인 구조 검증 가능
- 노드별 입력/출력 JSON을 남길 수 있음

---

## 12. 권장 디렉터리 구조

```text
ComfyUI_AOG/
  docs/
    PROJECT_PLAN.md
  aog/
    cli/
    config/
    planning/
    models/
    video/
    audio/
    voice/
    chaining/
    export/
  workflows/
    wan22_i2v_opening.json
    wan22_i2v_s2v_extend.json
  custom_nodes/
    comfyui_aog/
      __init__.py
      nodes/
      utils/
  presets/
    prompts/
    shot_templates/
  examples/
    project.video_first.yaml
    project.music_first.yaml
```

---

## 13. 데이터 계약

### 13.1 Project Config 예시

```yaml
project_name: "opening_demo"
mode: "video-first"
duration: 15
aspect_ratio: "21:9"
output_format: "webm"

video:
  i2v_model:
    family: "wan2.2"
    format: "safetensors"
    path: "./models/wan22_i2v.safetensors"
  s2v_model:
    family: "wan2.2"
    format: "gguf"
    path: "./models/wan22_s2v.gguf"
  chain_strategy: "last_frame"
  use_svi_lora: false

audio:
  engine: "ace-step"
  model_path: "./models/acestep"
  mode: "generate"
  prompt: "upbeat cinematic anime opening"
  voice_clone:
    enabled: true
    clone_id: "heroine_v1"
    reference_audio_dir: "./voices/heroine_v1"

inputs:
  source_images:
    - "./assets/scene01.png"
  text_prompt: "hero and rival standing in the rain, dramatic opening shot"

output:
  dir: "./outputs/opening_demo"
  fps: 24
```

실제 예제 YAML은 위 축약 예시보다 더 상세한 bundle 구조를 사용한다.
참고:

- [project.video_first.yaml](/home/hosung/pytorch-demo/ComfyUI_AOG/examples/project.video_first.yaml)
- [project.music_first.yaml](/home/hosung/pytorch-demo/ComfyUI_AOG/examples/project.music_first.yaml)

실사용 기본 출력 루트는 현재 아래 경로를 기준으로 잡는다.

- `/mnt/d/Stable Diffusion/aog`

### 13.2 Shot Plan 예시

```json
[
  {
    "index": 0,
    "duration": 4.0,
    "generator": "wan2.2-i2v",
    "input_image": "scene01.png",
    "prompt": "dramatic anime opening, hero introduction",
    "extension_needed": false,
    "chain_out": "shot_000_last.png"
  },
  {
    "index": 1,
    "duration": 6.0,
    "generator": "wan2.2-i2v",
    "input_image": "shot_000_last.png",
    "prompt": "camera rise, city lights, emotional tension",
    "extension_needed": true,
    "extension_generator": "wan2.2-s2v",
    "chain_out": "shot_001_last.png"
  }
]
```

### 13.3 Music Plan 예시

```json
{
  "duration": 15,
  "tempo_target": 138,
  "energy_curve": ["low", "mid", "high"],
  "hit_points": [2.0, 4.0, 8.5, 12.0, 14.5],
  "sections": [
    {"start": 0.0, "end": 4.0, "label": "intro_build"},
    {"start": 4.0, "end": 10.0, "label": "character_lift"},
    {"start": 10.0, "end": 15.0, "label": "climax"}
  ],
  "vocal": {
    "enabled": true,
    "clone_id": "heroine_v1",
    "style": "bright emotional anime vocal"
  }
}
```

---

## 14. ComfyUI workflow 설계안

### 14.1 i2v 메인 workflow

구성:

1. Config Loader
2. Wan Model Loader
3. Input Image Loader
4. Prompt Builder
5. Wan 2.2 i2v Generate
6. Last Frame Extract
7. Save Video
8. Save Last Frame

### 14.2 s2v 확장 workflow

구성:

1. Config Loader
2. Extension Segment Loader
3. S2V Model Loader
4. Wan 2.2 s2v Generate
5. Save Extended Video

### 14.3 운영 전략

초기에는 하나의 거대한 loop workflow보다 shot-by-shot 실행이 현실적이다.
CLI가 샷 목록을 돌며 workflow를 여러 번 호출하고, 각 호출 결과의 마지막 프레임을 다음 호출 입력으로 넘기는 구조를 기본으로 한다.
길이를 더 늘려야 하는 샷에서만 s2v extension workflow를 추가 호출한다.

---

## 15. 리스크와 대응

### 15.1 긴 시퀀스 continuity

문제:

- 샷 수가 늘수록 외형, 구도, 조명이 흔들릴 수 있다.

대응:

- shot 길이 제한
- last-frame chaining
- prompt inheritance
- `SVI LoRA` 보강

### 15.2 s2v 확장 품질

문제:

- 확장 구간이 기존 i2v 샷과 이질적으로 보일 수 있다.

대응:

- 모든 샷에 s2v를 쓰지 않기
- extension-needed 규칙을 명확히 두기
- 테스트 샷으로 extension 품질 검증

### 15.3 voice clone 품질

문제:

- 참조 데이터 품질이 낮으면 보컬 품질이 흔들릴 수 있다.

대응:

- clone reference 디렉터리 구조 관리
- clone metadata 저장
- instrumental-only fallback 유지

### 15.4 포맷 다양성

문제:

- `mp4`, `webm`마다 인코딩 옵션이 다르다.

대응:

- export 모듈 분리
- 포맷별 preset 인코딩 설정 제공

---

## 16. 결론

이 프로젝트의 가장 현실적인 구조는 아래와 같다.

1. `Wan 2.2 i2v`로 샷을 만든다.
2. 마지막 프레임으로 샷을 연결한다.
3. 필요할 때만 `Wan 2.2 s2v`로 길이를 확장한다.
4. `Ace Step`으로 음악을 만든다.
5. 보컬이 필요하면 `Ace Step voice clone`으로 음색을 지정한다.
6. 모든 모델 경로, 화면비, 출력 포맷은 설정 파일에서 지정한다.

즉, 이 프로젝트의 핵심은 "오프닝 생성기"라기보다 "Wan 2.2 i2v, s2v extension, Ace Step voice clone을 연결하는 CLI 중심 오프닝 제작 파이프라인"으로 정의하는 것이 맞다.
