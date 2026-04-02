# ComfyUI_AOG

`ComfyUI_AOG`는 완성된 오프닝 영상을 입력으로 받아, 영상과 어울리는 음악을 생성하기 위한 ComfyUI 커스텀 노드 팩입니다.

현재 범위:

- `ComfyUI-QwenVL`로 입력 영상을 의미적으로 분석
- 필요 시 `MMAudio`로 타이밍, 리듬감, 모션 강도 같은 cue를 보강
- 영상 기반 cue로 `ACE-Step`용 프롬프트 생성
- 영상 기반 cue로 `ACE-Step`용 가사 생성
- `프롬프트 언어`와 `가사 언어`를 분리 설정 가능
- `ACE-Step 언어` 설정 가능
- 필요 시 `MMAudio SFX` 레이어 생성
- 원본 영상 길이를 줄이지 않고 최종 오디오를 다시 mux

이 프로젝트는 영상을 새로 생성하지 않습니다.  
영상 자체는 팀이 이미 검증한 외부 SVI 워크플로우를 기준으로 사용하는 것이 전제입니다.

예:

- `user/default/workflows/svi.pro_workflow_mmmmn.json`

오디오 참고 워크플로우:

- `user/default/workflows/audio_ace_step_1_5_split_4b.json`
- `user/default/workflows/mmaudio_test.json`

## 주요 노드

이 패키지는 아래 노드들을 제공합니다.

- `AOG Pipeline Toggles`
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
- `AOG Opening Music Pipeline`

## 워크플로우 사용 방식

권장 흐름:

`VHS_LoadVideo -> AOG VHS Video Batch Adapter -> AOG Pipeline Toggles / AOG Quality Preset -> 각 stage gate -> authoring / music plan / ACE-Step / SFX / mux -> AOG Preview Video Combine`

중요한 동작:

- ComfyUI 캔버스에서 영상 업로드는 `VHS_LoadVideo`를 사용합니다.
- `VHS_LoadVideo` 출력은 `AOG VHS Video Batch Adapter`로 넘깁니다.
- 예시 워크플로우는 `영상 업로드 -> Queue Prompt`만으로 실행되는 것을 목표로 구성되어 있습니다.
  - 업로드용 워크플로우에서는 `source_path`를 직접 입력할 필요가 없습니다.
- 캔버스 마지막 출력은 `AOG Preview Video Combine`으로 끝내는 것을 권장합니다.
- 예시 워크플로우는 하나의 블랙박스 노드가 아니라, 분해된 그래프로 제공됩니다.
- 토글 off 시에는 관련 branch가 그래프에서 실제로 막히도록 gate 노드를 사용합니다.
  - 즉, 큰 파이프라인 노드 안에서 조용히 무시되는 방식이 아니라 ComfyUI 상에서 skip이 보이는 구조입니다.

## 토글과 품질 프리셋

`AOG Pipeline Toggles`:

- `enable_ace_step`
- `enable_mmaudio_features`
- `enable_qwenvl_analysis`
- `enable_prompt_authoring`
- `enable_lyrics_authoring`
- `enable_sfx`

`AOG SFX Compose`는 두 가지 작성 모드를 지원합니다.

- `sfx_prompt_mode = human | llm`
- `llm_provider = qwenvl | local_qwen`
- `human` 모드에서는 `sfx_prompt`에 적은 문장을 그대로 사용합니다.
- `llm` 모드에서는 먼저 영상 기반으로 SFX 프롬프트를 작성한 뒤, MMAudio 타이밍/모션 cue를 덧붙여 최종 프롬프트를 만듭니다.

의미:

- `QwenVL`은 `MMAudio feature extraction` 없이도 직접 영상을 분석할 수 있습니다.
- `MMAudio`는 authoring 보강 정보와 선택적 SFX 생성을 위한 레이어입니다.
- `enable_mmaudio_features`는 QwenVL 자체의 필수 조건이 아닙니다.
- `enable_ace_step=false`이면 prompt/lyrics authoring branch도 실질적으로 꺼진 상태로 취급됩니다.

`AOG Quality Preset`:

- `quality_profile = fast | balanced | high`
- `apply_quality_profile = true | false`

`apply_quality_profile=true`이면 아래 기본값이 자동 조정됩니다.

- ACE-Step `steps / cfg / text_cfg_scale`
- MMAudio SFX `steps / cfg`
- QwenVL `frame_count / token budget / temperature`

## 언어 정책

권장 기본 정책:

- `authoring_language = en`
- `lyrics_language = ja` 또는 실제 목표 가창 언어
- `ace_language = lyrics_language`와 동일

예:

- 프롬프트: 영어
- 가사: 일본어
- ACE-Step 언어: 일본어

권장 SFX 기본값:

- `sfx_prompt_mode = llm`
- `llm_provider = qwenvl`
- `authoring_language = en`

즉 기본 full workflow는 영상 기반으로 SFX 프롬프트를 자동 작성하도록 맞춰져 있습니다.

정리:

- `authoring_language`
  - QwenVL/LLM이 분석과 작성에 사용하는 언어
- `lyrics_language`
  - 최종 가사를 어떤 언어로 생성할지
- `ace_language`
  - ACE-Step에 전달되는 가창 언어

## 음악 계획 자동화

`AOG Music Plan`은 아래 값을 자동으로 정합니다.

- `bpm`
- `duration`
- `timesignature`
- `ace_language`
- `keyscale`

정책:

- `duration`은 항상 입력 영상 길이 기준으로 자동 결정됩니다.
- `plan_mode=llm`이면 `QwenVL` 또는 `local_qwen`이 영상 분석 결과를 바탕으로
  - BPM
  - 박자
  - 조성
  - 가창 언어
  를 정합니다.
- `plan_mode=human`이면 수동 override가 가능합니다.

즉, 사람이 직접 수동 모드로 쓰지 않는 이상 `bpm / keyscale / timesignature / duration`은 자동 계획되는 구조입니다.

## 설치

1. 이 저장소를 아래 위치에 둡니다.

```text
ComfyUI/custom_nodes/ComfyUI_AOG
```

2. Python 의존성을 설치합니다.

```powershell
cd "D:\Stable Diffusion\StabilityMatrix-win-x64\Data\Packages\ComfyUI"
& ".\venv\Scripts\python.exe" -m pip install -r ".\custom_nodes\ComfyUI_AOG\requirements.txt"
```

3. 외부 커스텀 노드와 모델을 설치합니다.

```powershell
powershell -ExecutionPolicy Bypass -File ".\custom_nodes\ComfyUI_AOG\install_dependencies.ps1"
```

설치 스크립트는 skip-safe입니다. 이미 설치된 항목은 건너뜁니다.

## 필요한 외부 노드

- `ComfyUI-MMAudio`
- `ComfyUI-QwenVL`
- `ComfyUI-VideoHelperSuite`

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

- `AOG_QwenVL_Authoring.json`
- `AOG_ACE_Music_Only.json`
- `AOG_Full_Music_SFX_Mux.json`

각 워크플로우 설명:

- `AOG_QwenVL_Authoring.json`
  - authoring 확인용 그래프
  - QwenVL 분석과 prompt/lyrics draft branch를 보기 좋게 분리
- `AOG_ACE_Music_Only.json`
  - SFX 없이 음악만 생성
  - prompt/lyrics 품질과 ACE-Step 동작을 보기 좋음
- `AOG_Full_Music_SFX_Mux.json`
  - SFX와 최종 mux까지 포함
  - 미리보기 가능한 end-to-end 결과 확인용
  - 기본 SFX 작성 방식은 `llm + qwenvl`
  - 직접 쓰고 싶으면 `sfx_prompt_mode = human`으로 바꾸면 됩니다

## 워크플로우 재로드 주의

이전 빌드에서 저장된 워크플로우를 계속 쓰고 있으면, 예전 노드 정의가 메모리에 남아 위젯이 밀려 보일 수 있습니다.

예:

- `bpm = NaN`
- `timesignature = simple`
- `ace_language = 1`

이 경우:

1. ComfyUI 완전 재시작
2. 브라우저 새로고침
3. 워크플로우 JSON 다시 열기

## CLI 실행

캔버스를 열지 않고 현재 파이프라인을 실행할 수도 있습니다.

```powershell
& ".\venv\Scripts\python.exe" ".\custom_nodes\ComfyUI_AOG\run_aog_audio_pipeline.py" `
  --video "D:\Stable Diffusion\aog\test\test.webm" `
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
  - 현재는 영상 기반 context를 더 잘 정리해서 prompt/lyrics 품질을 높이는 방향입니다.
