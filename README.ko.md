# ComfyUI_AOG

Cookbook: [docs/cookbook/INDEX.md](./docs/cookbook/INDEX.md)

`ComfyUI_AOG`는 완성된 오프닝 영상을 입력으로 받아, 영상에 맞는 음악과 선택적 SFX, 요약 JSON, 미리보기 가능한 최종 비디오를 만드는 ComfyUI 커스텀 노드 팩입니다.

## 범위

- `ComfyUI-QwenVL`로 입력 영상을 의미적으로 분석
- 필요 시 `MMAudio`로 타이밍, 리듬감, 모션 강도 cue를 보강
- 영상 기반 컨텍스트로 `ACE-Step`용 프롬프트 생성
- 영상 기반 컨텍스트로 `ACE-Step`용 가사 생성
- `bpm`, `duration`, `timesignature`, `ace_language`, `keyscale` 자동 계획
- 필요 시 `MMAudio SFX` 레이어 생성
- 요약 JSON 저장
- 원본 영상 길이를 줄이지 않고 최종 오디오를 다시 mux

이 프로젝트는 영상을 새로 생성하지 않습니다.  
영상 자체는 팀이 이미 검증한 외부 SVI 워크플로우를 기준으로 사용합니다.

예:

- `user/default/workflows/svi.pro_workflow_mmmmn.json`

오디오 참고 워크플로우:

- `user/default/workflows/audio_ace_step_1_5_split_4b.json`
- `user/default/workflows/mmaudio_test.json`

## 역할 분리

### AOG

AOG는 기능을 담당합니다.

- 비디오 배치 적응
- feature 추출
- QwenVL 의미 분석
- 프롬프트 작성
- 가사 작성
- 음악 계획
- ACE-Step 음악 생성
- MMAudio SFX 생성
- 최종 오디오 믹스
- summary JSON 저장
- 비디오 저장 및 프리뷰

주요 AOG 노드:

- `AOG Quality Preset`
- `AOG Load Video Frames`
- `AOG MMAudio Feature Bundle`
- `AOG MMAudio SFX Bundle`
- `AOG QwenVL Bundle`
- `AOG VHS Video Batch Adapter`
- `AOG Video Feature Extract`
- `AOG QwenVL Semantic Extract`
- `AOG Prompt Draft`
- `AOG Lyrics Draft`
- `AOG Music Plan`
- `AOG ACE-Step Compose`
- `AOG SFX Compose`
- `AOG Final Audio Mix`
- `AOG Mux Video Audio`
- `AOG Preview Video Combine`
- `AOG Save Summary JSON`

### rgthree

`rgthree`는 shipped example workflow에서 캔버스 수준 토글 UX만 담당합니다.

- 그룹 단위 mute / bypass
- branch 실행 건너뛰기 시각화
- 워크플로우 조립 UX

즉 정리하면:

- `AOG`는 기능
- `rgthree`는 토글 UX

## 워크플로우 계약

- 업로드 중심 워크플로우는 `VHS_LoadVideo`에서 시작해야 합니다.
- `VHS_LoadVideo` 출력은 `AOG VHS Video Batch Adapter`로 넘깁니다.
- shipped workflow에서는 `source_path`를 직접 입력하지 않습니다.
- 실행 가능한 워크플로우는 `AOG Preview Video Combine`에서 끝내야 저장과 미리보기가 같이 동작합니다.
- summary 메타데이터는 `AOG Save Summary JSON`으로 저장합니다.
- 예시 워크플로우는 하나의 블랙박스가 아니라 분해된 그래프입니다.

권장 흐름:

`VHS_LoadVideo -> AOG VHS Video Batch Adapter -> AOG Quality Preset -> AOG 분석 / 작성 / 계획 / 생성 / 저장 / 프리뷰`

선택 branch on/off는 `rgthree` 그룹 mute / bypass로 제어합니다.

## 언어 정책

권장 기본값:

- `authoring_language = en`
- `lyrics_language = ja` 또는 목표 가창 언어
- `ace_language = lyrics_language`

예:

- 프롬프트: 영어
- 가사: 일본어
- ACE-Step 언어: 일본어

권장 SFX 기본값:

- `sfx_prompt_mode = llm`
- `llm_provider = qwenvl`
- `authoring_language = en`

## 음악 계획

`AOG Music Plan`은 아래 값을 자동으로 정합니다.

- `bpm`
- `duration`
- `timesignature`
- `ace_language`
- `keyscale`

정책:

- `duration`은 입력 영상 길이에서 자동 결정
- `plan_mode = llm`이면 분석된 영상 컨텍스트를 바탕으로 나머지 값을 자동 결정
- `plan_mode = human`이면 수동 override 가능

## 설치

1. 저장소 위치:

```text
ComfyUI/custom_nodes/ComfyUI_AOG
```

2. Python ??? ??:

Windows:

```powershell
cd "<ComfyUI ??>"
& ".\venv\Scripts\python.exe" -m pip install -r ".\custom_nodes\ComfyUI_AOG\requirements.txt"
```

Linux/macOS:

```bash
cd "<ComfyUI ??>"
./venv/bin/python -m pip install -r "./custom_nodes/ComfyUI_AOG/requirements.txt"
```

3. ?? ??/?? ??:

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File ".\custom_nodes\ComfyUI_AOG\install_dependencies.ps1"
```

Linux/macOS:

```bash
bash ./custom_nodes/ComfyUI_AOG/install_dependencies.sh
```

?? ??? ??? ?????.

## 필요한 외부 노드

- `ComfyUI-MMAudio`
- `ComfyUI-QwenVL`
- `ComfyUI-VideoHelperSuite`
- `rgthree-comfy`

## 필요한 모델

### ACE-Step

- `models/diffusion_models/acestep_v1.5_turbo.safetensors`
- `models/text_encoders/qwen_0.6b_ace15.safetensors`
- `models/text_encoders/qwen_4b_ace15.safetensors`
- `models/vae/ace_1.5_vae.safetensors`

### MMAudio

- `models/diffusion_models/mmaudio_large_44k_v2_fp16.safetensors`
- `models/vae/mmaudio_vae_44k_fp16.safetensors`
- `models/audio_encoders/mmaudio_synchformer_fp16.safetensors`
- `models/clip_vision/apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors`

### QwenVL

권장:

- `models/LLM/Qwen-VL/Qwen3-VL-4B-Instruct`

대안:

- `models/LLM/Qwen-VL/Qwen3-VL-2B-Instruct`

## 예시 워크플로우

예시 워크플로우는 [workflows](./workflows) 폴더에 있습니다.

- `AOG_ACE_Music_Only.json`
- `AOG_Full_Music_SFX_Mux.json`
- `AOG_MMAudio_SFX_Only.json`

노드를 독립적으로 조립해서 쓰는 방법, 입출력 계약, 실전 레시피는 [cookbook](./docs/cookbook/INDEX.md)에서 볼 수 있습니다.

설명:

- `AOG_ACE_Music_Only.json`
  - SFX 없이 음악만 생성
  - prompt/lyrics 품질과 ACE-Step 동작 점검용
- `AOG_Full_Music_SFX_Mux.json`
  - ACE-Step, MMAudio SFX, 최종 믹스, summary 저장, 프리뷰 저장까지 포함
  - end-to-end 기준 워크플로우
- `AOG_MMAudio_SFX_Only.json`
  - ACE-Step 없이 MMAudio SFX만 생성
  - SFX 단독 저장, 프리뷰, JSON 저장 점검용

## 워크플로우 재로드 주의

- 예전 `seed` 입력이 남아 있는 빌드에서 올라온 워크플로우를 계속 쓰면 위젯 순서가 깨질 수 있습니다.
- 아래 같은 값이 보이면 구버전 노드 정의가 메모리에 남아 있는 상태입니다.
  - `bpm = NaN`
  - `timesignature = simple`
  - `ace_language = 1`

해결:

- ComfyUI 완전 재시작
- 브라우저 새로고침
- 워크플로우 JSON 다시 열기

## CLI 실행

```powershell
& ".\venv\Scripts\python.exe" ".\custom_nodes\ComfyUI_AOG\run_aog_audio_pipeline.py" `
  --video ".\output\example_input.webm" `
  --output-dir ".\custom_nodes\ComfyUI_AOG\outputs\demo" `
  --prompt-mode llm `
  --lyrics-mode llm `
  --authoring-language en `
  --lyrics-language ja `
  --ace-language ja `
  --llm-provider qwenvl `
  --qwenvl-model "Qwen3-VL-4B-Instruct" `
  --steps 8 `
  --cfg 1.0 `
  --text-cfg-scale 5.0 `
  --sfx-mode auto
```

## 참고

- 파이프라인은 입력 영상 전체 길이를 유지한 채 mux를 수행합니다.
- `QwenVL`은 prompt/lyrics authoring의 핵심 분석 레이어입니다.
- `MMAudio`는 authoring 보강과 선택적 SFX 생성 레이어입니다.
- `ACE-Step`은 음악 생성에 사용됩니다.
- `MMAudio latent`를 `ACE-Step`에 직접 주입하는 방식은 아직 구현되지 않았습니다.
