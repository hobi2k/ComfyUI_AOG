# ComfyUI-First Architecture

## 목적

이 문서는 `ComfyUI_AOG`의 현재 구현 기준을 고정하기 위한 아키텍처 문서다.

현재 프로젝트의 방향은 다음과 같다.

- `ComfyUI를 먼저 설치한다.`
- `프로젝트 루트는 Windows의 ComfyUI 설치본 아래 custom_nodes/ComfyUI_AOG 로 잡는다.`
- `ComfyUI 위에서 오프닝 전용 workflow와 custom node를 개발한다.`
- `CLI는 독립 실행 본체가 아니라, 설치된 ComfyUI 런타임을 headless로 다루는 보조 실행층이다.`

즉 이 프로젝트는 더 이상 `ComfyUI와 완전히 분리된 CLI-first 제품`을 우선 목표로 두지 않는다.
기준 구현은 `ComfyUI-first custom node / workflow 프로젝트`다.

---

## 1. 왜 이 방향으로 가는가

이번 프로젝트의 최종 목표는 다음이다.

- 애니메이션 오프닝 전용 ComfyUI workflow 제작
- 오프닝 도메인에 맞춘 custom node 제작
- Wan 2.2 / Ace Step / 관련 후처리를 ComfyUI 문맥에 맞게 재구성

이 목표에서는 `ComfyUI 설치본 위에서 바로 개발`하는 편이 더 자연스럽다.

이유:

- custom node는 원래 ComfyUI 런타임 안에서 동작하는 플러그인이다.
- 입력 타입, 출력 타입, 모델 로더, VRAM 관리, offload 정책이 ComfyUI 문맥과 강하게 연결된다.
- `ComfyUI-MMAudio`, `ComfyUI-WanVideoWrapper` 같은 선행 프로젝트들도 같은 방식으로 개발된다.
- workflow와 node를 최종 산출물로 삼는다면, 처음부터 그 환경에서 검증하는 것이 설계 왜곡이 적다.
- 경로, venv, models, custom_nodes, folder_paths가 하나의 설치 루트에 모여 있어 디버깅이 쉽다.

---

## 2. 현재 기준 구현

현재 저장소의 기준 구현은 아래다.

1. `ComfyUI 설치본`을 기준 런타임으로 사용한다.
2. 프로젝트 루트는 `ComfyUI/custom_nodes/ComfyUI_AOG`에 둔다.
3. 필요한 custom node와 모델들을 같은 ComfyUI 설치본 기준으로 관리한다.
4. `aog/local_runtime`는 ComfyUI 내부 모듈과 custom node를 로컬 파이썬에서 직접 import해서 사용한다.
5. `aog/cli.py`는 이 설치된 ComfyUI 런타임을 headless로 실행하는 보조 도구다.

즉 `CLI = ComfyUI 없는 독립 추론기`가 아니다.
현재의 CLI는 `ComfyUI 설치 환경을 대상으로 하는 headless orchestrator`다.

---

## 3. 무엇을 전제로 하는가

이 구조는 아래 전제를 가진다.

- ComfyUI 본체가 설치되어 있다.
- 현재 작업 디렉터리도 원칙적으로 그 ComfyUI 설치본 아래에 있다.
- `comfy`, `comfy_extras`, `folder_paths` 같은 ComfyUI 내부 모듈을 사용할 수 있다.
- 필요한 custom node가 설치되어 있다.
  - 예: `ComfyUI-WanVideoWrapper`
  - 예: Ace Step 관련 Comfy 노드
- 모델은 ComfyUI의 모델 폴더 구조에 맞춰 배치된다.

즉 현재 코드에서 `ComfyPathError` 같은 개념이 남아 있는 이유도 여기 있다.
이 경로는 API 서버 때문이 아니라, 설치된 ComfyUI 루트와 그 안의 모델/노드 위치를 계산하기 위해 필요하다.

---

## 4. 구현 순서

이제부터 권장 구현 순서는 다음이다.

1. `Windows ComfyUI/custom_nodes/ComfyUI_AOG`에 프로젝트를 둔다.
2. `ComfyUI 설치 환경`을 기준으로 런타임 정합성을 맞춘다.
3. 오프닝용 custom node 단위를 먼저 설계한다.
4. 오프닝용 workflow를 만든다.
5. 필요한 경우 동일 로직을 CLI에서 headless 실행할 수 있게 한다.

즉 우선순위는:

1. `custom node`
2. `workflow`
3. `CLI orchestration`

이다.

---

## 5. CLI의 역할

CLI는 여전히 유용하다.
다만 역할이 바뀐다.

CLI가 담당할 일:

- 설정 검증
- 배치 실행
- manifest 생성
- headless run
- 실험 자동화

CLI가 더 이상 담당하지 않는 것으로 보는 것:

- ComfyUI 설치본과 완전히 분리된 독립 추론 엔진
- ComfyUI 없이 동일 책임을 모두 수행하는 별도 런타임

즉 CLI는 `원본 제품`이 아니라 `ComfyUI 기반 프로젝트의 자동화 인터페이스`다.

---

## 6. custom node 설계 원칙

새 노드는 아래 원칙으로 만든다.

- 오프닝 제작에서 반복되는 책임을 분리한다.
- workflow에서 배선이 복잡한 부분을 줄인다.
- Wan 2.2 / Ace Step 호출을 오프닝 문맥에 맞춰 캡슐화한다.

예상 노드:

- `AOGShotPlanner`
- `AOGLastFrameExtractor`
- `AOGExtensionSourceResolver`
- `AOGMusicPlanBuilder`
- `AOGExport`

---

## 7. workflow 설계 원칙

workflow는 단순히 기존 공개 workflow를 그대로 복사하는 게 아니라,
오프닝 문법에 맞게 재구성한다.

핵심 구성:

- 입력 이미지
- 텍스트 조건
- shot 계획
- i2v 샷 생성
- last-frame 추출
- extension image 선택
- 음악 생성
- 최종 export

즉 workflow는 `오프닝 제작 흐름`을 드러내는 형태여야 한다.

---

## 8. 현재 저장소에 대한 적용 규칙

앞으로 이 저장소에서는 아래 기준을 따른다.

- 문서는 `ComfyUI-first` 관점으로 작성한다.
- 프로젝트 위치는 `ComfyUI/custom_nodes/ComfyUI_AOG`를 기준으로 설명한다.
- `aog/local_runtime`는 ComfyUI 설치본을 사용하는 headless runtime으로 본다.
- implementation의 기준은 `custom node`와 `workflow`다.
- CLI는 이를 보조하는 자동화/검증 층으로 유지한다.

---

## 9. 현재 상태

현재 저장소에는 다음이 들어가 있다.

- config/schema/manifest 계층
- `validate -> plan -> run` CLI 구조
- ComfyUI 설치본을 가져다 쓰는 `aog/local_runtime`
- Wan/Ace direct-call wrapper 초안

이제 다음 구현은 아래 순서로 진행한다.

1. 오프닝 전용 custom node 설계
2. workflow 구조 설계
3. headless CLI가 그 workflow/custom node 책임을 보조하도록 정리
