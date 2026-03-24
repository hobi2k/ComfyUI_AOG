# Experiment Setup

## 목적

이 문서는 현재 실험용 자산 경로를 기준으로 `ComfyUI_AOG` 파이프라인을 어떻게 테스트할지 정리한 문서다.

기준 경로:

- `/mnt/d/Stable Diffusion/aog/test`

확인된 파일:

- `/mnt/d/Stable Diffusion/aog/test/t1.png`
- `/mnt/d/Stable Diffusion/aog/test/t2.png`
- `/mnt/d/Stable Diffusion/aog/test/t3.png`
- `/mnt/d/Stable Diffusion/aog/test/voice_clone.flac`

---

## 자산 사용 규칙

### 1. source image

기본 시작 이미지로는 `t1.png`를 사용한다.

### 2. extension image

영상 extension 시 입력 이미지는 아래 규칙을 따른다.

- `last_frame` 사용 실험:
  - 시작 이미지는 `t1.png`
  - extension 입력은 렌더된 이전 샷의 마지막 프레임

- `custom_image` 사용 실험:
  - 시작 이미지는 `t1.png`
  - extension 입력 후보 이미지는 `t2.png`, `t3.png`

즉:

- `last_frame` 실험은 `t1`
- `custom_image` 실험은 `t2`, `t3`

### 3. voice clone

Ace Step voice clone 참조 음성은 아래를 사용한다.

- `/mnt/d/Stable Diffusion/aog/test/voice_clone.flac`

---

## 실험 시나리오

### 시나리오 A. Last Frame Extension

목표:

- i2v로 시작한 샷을 `last_frame` 기반으로 자연스럽게 이어붙이는지 확인

입력:

- source image: `t1.png`
- extension mode: `last_frame`
- custom_image: 비워둠
- voice clone: `voice_clone.flac`

추천 용도:

- continuity 테스트
- chaining 품질 테스트
- SVI LoRA 효과 테스트

### 시나리오 B. Custom Image Extension with t2

목표:

- 사용자가 지정한 이미지로 extension 구간 분위기 또는 장면 전환을 의도적으로 바꿀 수 있는지 확인

입력:

- source image: `t1.png`
- extension mode: `custom_image`
- custom_image: `t2.png`
- voice clone: `voice_clone.flac`

추천 용도:

- 수동 장면 전환 테스트
- 특정 포즈/구도 고정 전환

### 시나리오 C. Custom Image Extension with t3

목표:

- `t3.png`를 전환 기준 이미지로 썼을 때 연결 감과 장면 분위기 변화 확인

입력:

- source image: `t1.png`
- extension mode: `custom_image`
- custom_image: `t3.png`
- voice clone: `voice_clone.flac`

추천 용도:

- 강한 장면 전환 테스트
- 음악 클라이맥스 구간 전환 테스트

---

## 예제 YAML 수정 가이드

### 공통 입력 자산

아래 값들로 교체하면 된다.

```yaml
inputs:
  source_images:
    - "/mnt/d/Stable Diffusion/aog/test/t1.png"
  reference_images: []
  text_prompt: "anime opening, dramatic character reveal, cinematic framing, stylish motion, emotional energy"

audio:
  vocal:
    enabled: true
    lyrics_mode: "manual"
    lyrics_path: "./assets/lyrics/experiment_opening.txt"
    style_prompt: "bright emotional anime vocal, clean female lead, energetic chorus"
  voice_clone:
    enabled: true
    clone_id: "test_voice_clone"
    reference_audio_dir: "/mnt/d/Stable Diffusion/aog/test"
    mix_mode: "separate_stems"
```

### Last Frame Extension 설정

```yaml
video:
  extension:
    enabled: true
    max_extension_seconds_per_shot: 3.0
    source_mode: "last_frame"
    custom_image: ""
    apply_when:
      - "hold"
      - "music_gap"
```

### Custom Image Extension with t2

```yaml
video:
  extension:
    enabled: true
    max_extension_seconds_per_shot: 3.0
    source_mode: "custom_image"
    custom_image: "/mnt/d/Stable Diffusion/aog/test/t2.png"
    apply_when:
      - "hold"
      - "music_gap"
```

### Custom Image Extension with t3

```yaml
video:
  extension:
    enabled: true
    max_extension_seconds_per_shot: 3.0
    source_mode: "custom_image"
    custom_image: "/mnt/d/Stable Diffusion/aog/test/t3.png"
    apply_when:
      - "chorus_hold"
      - "scene_shift"
```

---

## Ace Step 실험용 프롬프트

아래는 실험용으로 바로 쓸 수 있는 임시 프롬프트다.

### Prompt A

```text
Energetic anime opening song with bright synth lead, emotional build-up, punchy drums, and a strong chorus. Stylish and cinematic mood, fast intro, confident vocal tone, dramatic ending hit.
```

### Prompt B

```text
Anime game opening soundtrack with vivid electronic melody, emotional female vocal, fast tempo, glowing atmosphere, uplifting chorus, and polished cinematic finish.
```

### Prompt C

```text
Modern anime opening with pop-rock energy, sparkling synth arpeggios, emotional lead vocal, strong rhythmic drive, and a bright triumphant final section.
```

---

## Ace Step 실험용 임시 가사

아래는 테스트용 수동 가사 예시다.

```text
[Intro]
The night is calling out my name
I feel the sparks inside the rain

[Verse]
Running through the lights we know
Chasing all the signs that glow
Every beat becomes a flame
Nothing here will stay the same

[Pre-Chorus]
Hold your breath and count to three
This is where we're meant to be

[Chorus]
Shine again, we rise tonight
Cross the dark into the light
Take my hand and don't let go
This is our opening glow

[Outro]
One more step, one more sign
Leave the restless world behind
```

---

## 권장 실험 순서

1. `last_frame` 모드로 먼저 실행해 continuity를 본다.
2. `custom_image = t2.png`로 바꿔 장면 전환 강도를 본다.
3. `custom_image = t3.png`로 바꿔 다른 전환 패턴을 본다.
4. voice clone을 켠 상태와 끈 상태의 음악 결과를 비교한다.

---

## 검증 명령

실제 렌더 전 구조 검증:

```bash
cd /home/hosung/pytorch-demo/ComfyUI_AOG
uv run aog validate examples/project.test_lastframe.yaml --validation-mode runtime --no-write
uv run aog validate examples/project.test_custom_t2.yaml --validation-mode runtime --no-write
uv run aog validate examples/project.test_custom_t3.yaml --validation-mode runtime --no-write
```

실행 계획까지 보고 싶다면:

```bash
uv run aog plan examples/project.test_lastframe.yaml --validation-mode runtime --no-write
uv run aog run examples/project.test_lastframe.yaml --validation-mode runtime --no-write
```

`run --no-write`는 dry-run이다.
`run`은 실제로 Wan/Ace Step local runtime 추론을 수행하며, 실행 전후에 아래 파일들을 기준 산출물로 사용한다.

- shot별 `job.json`
- `audio_job.json`
- `music_plan.json`
- `execution_plan.json`
- `run_summary.json`

즉 지금 CLI는 "manifest를 쓰고 바로 local runtime까지 실행하는 파이프라인"을 기준 경로로 둔다.
