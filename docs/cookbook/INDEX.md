# Cookbook

`ComfyUI_AOG` 노드를 다른 워크플로우에 독립적으로 조립해서 쓰기 위한 실전 가이드입니다.

이 폴더는 다음 원칙으로 정리되어 있습니다.

- AOG 노드는 기능 노드로 본다.
- 토글과 bypass UX는 `rgthree` 같은 워크플로우 레이어에서 처리한다.
- 영상 업로드, 프롬프트 작성, 가사 작성, 음악 계획, ACE-Step 생성, MMAudio SFX 생성, 저장과 프리뷰를 서로 독립적으로 조합할 수 있어야 한다.

## 문서 구성

- [노드 레퍼런스](./NODE_REFERENCE.md)
  - 각 AOG 노드의 역할, 언제 쓰는지, 대표 입력과 출력
- [입출력 계약](./INPUT_OUTPUT_CONTRACTS.md)
  - `AOG_VIDEO_BATCH`, `AOG_VIDEO_FEATURES`, summary JSON 흐름 설명
- [조합 레시피](./RECIPES.md)
  - 가장 자주 쓰는 연결 패턴 예시
- [독립 사용 가이드](./STANDALONE_USAGE.md)
  - 다른 워크플로우에 AOG 노드를 부분적으로 가져다 쓰는 방법
- [트러블슈팅](./TROUBLESHOOTING.md)
  - preview, summary JSON, prompt/lyrics 표시, widget 밀림 문제 등

## 빠른 시작

가장 기본적인 연결은 아래 순서입니다.

1. `VHS_LoadVideo`
2. `AOG VHS Video Batch Adapter`
3. `AOG Video Feature Extract`
4. 필요 시:
   - `AOG QwenVL Semantic Extract`
   - `AOG Prompt Draft`
   - `AOG Lyrics Draft`
   - `AOG Music Plan`
5. 생성:
   - `AOG ACE-Step Compose`
   - 또는 `AOG SFX Compose`
6. 정리:
   - `AOG Final Audio Mix`
   - `AOG Merge Summary JSON`
   - `AOG Save Summary JSON`
   - `AOG Preview Video Combine`
   - `VHS_VideoCombine` for GUI preview

## shipped workflow와 cookbook의 관계

`./../../workflows` 아래 shipped workflow는 cookbook 레시피의 완성본 예시입니다.

- `AOG_ACE_Music_Only.json`
- `AOG_Full_Music_SFX_Mux.json`
- `AOG_MMAudio_SFX_Only.json`

Cookbook 문서는 이 예시들을 그대로 따라 하라는 문서가 아니라, 필요한 기능만 안전하게 떼어다 조합할 수 있게 설명하는 문서입니다.
