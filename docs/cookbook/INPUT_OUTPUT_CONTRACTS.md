# Input / Output Contracts

이 문서는 AOG 노드를 독립적으로 조립할 때 꼭 알아야 하는 데이터 계약을 설명합니다.

## `AOG_VIDEO_BATCH`

비디오 원본을 AOG 파이프라인에서 공통으로 다루기 위한 계약입니다.

보통 생성 경로:

1. `VHS_LoadVideo`
2. `AOG VHS Video Batch Adapter`

핵심 의미:

- 원본 프레임 텐서
- frame count
- fps
- loaded duration
- source duration
- source path 또는 provenance

이 계약을 쓰는 노드:

- `AOG Video Feature Extract`
- `AOG QwenVL Semantic Extract`
- `AOG Prompt Draft`
- `AOG Lyrics Draft`
- `AOG Music Plan`
- `AOG SFX Compose`
- `AOG Preview Video Combine`

## `AOG_VIDEO_FEATURES`

영상 기반 authoring과 planning에 쓰는 구조화 분석 결과입니다.

일반적으로 포함되는 내용:

- `summary`
- `timeline`
- `semantic_cues`
- `conditioning_summary`
- `latent_structure_cues`
- `duration_sec`
- `source_duration_sec`
- `loaded_duration_sec`
- `frame_count`
- `fps`

이 계약을 쓰는 노드:

- `AOG Prompt Draft`
- `AOG Lyrics Draft`
- `AOG Music Plan`
- `AOG ACE-Step Compose`
- `AOG SFX Compose`

## `summary_json`

각 단계가 사람이 읽기 쉬운 메타를 JSON 문자열로 돌려주는 계약입니다.

기본 원칙:

- 각 단계는 자기 summary를 만든다.
- 최종 저장 전에는 `AOG Merge Summary JSON`으로 합친다.
- 최종 저장은 `AOG Save Summary JSON`으로 한다.

대표 항목:

- `video_summary`
- `prompt_summary`
- `lyrics_summary`
- `music_plan_summary`
- `ace_summary`
- `sfx_summary`
- `final_mix_summary`
- `preview_summary`
- `scene_analysis`
- `prompt_text`
- `lyrics_text`

## prompt / lyrics 출력

`AOG Prompt Draft`와 `AOG Lyrics Draft`는 두 가지 채널로 결과를 내보내는 것이 좋습니다.

1. 텍스트 출력

- `prompt_text`
- `lyrics_text`

2. 메타 출력

- `summary_json`

실전 팁:

- 캔버스에서 눈으로 확인하려면 `PreviewAny`를 병렬로 붙이십시오.
- 최종 산출물에 남기려면 `AOG Merge Summary JSON`으로 합치십시오.

## preview 계약

최종 비디오 preview는 두 계층으로 생각하면 편합니다.

1. GUI preview

- `VHS_VideoCombine`
- ComfyUI 화면에서 즉시 재생 확인

2. 저장 + AOG 메타

- `AOG Preview Video Combine`
- 저장 결과와 preview summary를 남김

권장:

- shipped workflow처럼 두 노드를 병렬로 함께 사용

## duration 계약

duration 정책은 다음이 기본입니다.

- 입력 영상 전체 길이를 유지
- `AOG Music Plan.duration`은 영상 길이 기준
- 최종 오디오는 원본 영상 길이에 맞춰 정규화
- mux 시 원본 비디오 길이를 줄이지 않음
