# CLI-First Architecture

## 목적

이 문서는 `ComfyUI_AOG`의 구현 방향을 고정하기 위한 별도 아키텍처 원칙 문서다.
프로젝트의 목표는 "ComfyUI를 호출하는 래퍼"를 만드는 것이 아니라, 애니메이션 오프닝 제작용 독립 파이프라인을 먼저 구축한 뒤 그 로직을 ComfyUI workflow와 커스텀 노드로 이식하는 것이다.

핵심 원칙은 하나다.

- `CLI 파이프라인이 원본이고, ComfyUI workflow와 custom node는 그 원본을 이식한 표현층이다.`

---

## 1. 왜 CLI를 먼저 독립적으로 만들어야 하는가

이 프로젝트는 최종적으로 새로운 애니메이션 오프닝용 workflow와 커스텀 노드를 만들기 위한 것이다.
따라서 먼저 검증되어야 하는 것은 다음이다.

- 샷 플래닝
- 이미지 입력 규칙
- last-frame chaining
- custom image extension
- 음악 생성 구조
- voice clone 연동
- 최종 합성/export

이 핵심 로직을 처음부터 기존 workflow 호출에 의존해 구현하면 아래 문제가 생긴다.

- CLI가 독립 실행기가 아니라 ComfyUI 클라이언트가 된다.
- 파이프라인 설계가 노드 배선 방식에 끌려간다.
- 추론 단계와 편집/오케스트레이션 단계의 책임이 흐려진다.
- 나중에 custom node를 만들 때 "검증된 로직"이 아니라 "기존 workflow 호출 방식"만 남는다.

그래서 올바른 순서는 다음이다.

1. `CLI 파이프라인을 ComfyUI와 독립적으로 완성`
2. `직접 모델 추론이 되는 local python executor 구현`
3. `로직과 데이터 계약 안정화`
4. `ComfyUI workflow로 이식`
5. `커스텀 노드로 캡슐화`

---

## 2. 금지되는 방향

아래 방식은 프로젝트의 주 경로가 아니다.

- CLI가 외부 workflow 실행기에 종속되는 구조를 본체로 삼는 것
- 기존 ComfyUI workflow를 그대로 호출하는 래퍼로 끝나는 것
- "workflow를 빌려 쓰는 것"을 1차 구현의 중심에 두는 것

이런 방식은 참고용 검증에는 쓸 수 있어도 프로젝트의 기준 구현이 되어서는 안 된다.

즉 현재 저장소의 기준 구현은 `CLI local executor` 하나다.
예전 외부 실행기 경로는 제거 대상이며 본체로 유지하지 않는다.

---

## 3. 공식 구현 순서

### 단계 1. 독립 CLI 코어 구축

이 단계의 목표는 ComfyUI 없이도 아래가 가능해지는 것이다.

- `validate`
- `plan`
- `run`

여기서 `run`은 실제 모델 추론을 수행해야 한다.

필수 범위:

- Wan 2.2 i2v 직접 호출
- shot loop
- last-frame 추출
- 다음 shot 입력으로 chaining
- custom image extension 처리
- Ace Step 직접 호출
- voice clone conditioning
- ffmpeg 기반 최종 합성

### 단계 2. 실행 계층 분리

CLI 파이프라인은 아래 계층으로 나눈다.

- `core`
  - Wan / Ace Step 로더와 추론 호출
- `pipeline`
  - shot planning / chaining / music planning / export orchestration
- `cli`
  - validate / plan / run
- `artifacts`
  - manifest / intermediate outputs / logs

이 구조에서 ComfyUI는 아직 등장하지 않는다.

### 단계 3. ComfyUI workflow 이식

CLI 코어가 안정화된 후, 각 단계를 workflow 노드 그래프로 옮긴다.

옮겨야 할 대상:

- image input
- prompt assembly
- shot generation
- last-frame extraction
- extension source switching
- music generation
- final export

이 단계의 목적은 CLI 로직을 UI와 workflow 환경에서도 재현 가능하게 만드는 것이다.

### 단계 4. 커스텀 노드 제작

반복되거나 도메인 특화된 단위는 커스텀 노드로 만든다.

예시:

- `AOGShotPlanner`
- `AOGLastFrameExtractor`
- `AOGExtensionSourceResolver`
- `AOGMusicPlanBuilder`
- `AOGOpeningExport`

커스텀 노드는 "새 알고리즘의 본체"가 아니라, CLI 코어에서 검증된 로직을 ComfyUI 문맥에 맞게 캡슐화한 것이다.

---

## 4. 아키텍처 원칙

### 원칙 1. 로직은 ComfyUI 바깥에 둔다

도메인 로직의 진실 원본은 Python CLI 코드다.

예:

- shot planning 규칙
- chaining 규칙
- extension 규칙
- music plan 규칙
- export 규칙

이 규칙을 workflow JSON에만 넣어두면 유지보수가 어려워진다.

### 원칙 2. workflow는 코어를 재현해야 한다

workflow는 독립적인 별도 설계물이 아니라, CLI 코어를 시각적으로 재현한 결과물이어야 한다.

즉:

- 먼저 workflow를 설계하고 CLI가 따라가는 것: 안 됨
- 먼저 CLI 코어를 설계하고 workflow가 따라오는 것: 맞음

### 원칙 3. custom node는 adapter다

custom node는 ComfyUI 내부에서 CLI 코어의 일부 책임을 수행하는 adapter다.

따라서 custom node를 만들 때도 기준은 아래다.

- 이미 CLI에서 검증된 로직인가
- workflow에서 반복되거나 복잡한 부분을 줄이는가
- 노드 단위 책임이 명확한가

### 원칙 4. 외부 실행기 의존은 최소화한다

외부 서버 orchestration이나 기존 workflow import는 본체가 아니다.

프로젝트의 기준 구현은 다음이어야 한다.

- `local python executor`
- `headless CLI`
- `reproducible manifests`

---

## 5. 구현 우선순위

앞으로의 우선순위는 아래와 같다.

1. `local python executor`로 Wan 2.2 i2v 직접 호출
2. shot chaining을 실제 추론 루프에 연결
3. Ace Step 직접 호출 및 voice clone 연결
4. ffmpeg 최종 export 안정화
5. `video-first` / `music-first` 둘 다 지원
6. 그 다음에 ComfyUI workflow 제작
7. 마지막에 custom node 제작

즉 당분간 구현의 초점은 다음 두 가지다.

- `ComfyUI 독립 실행`
- `CLI 본체 완성`

---

## 6. 현재 프로젝트에 대한 적용 규칙

앞으로 이 저장소에서 아래 규칙을 따른다.

- 새 기능은 우선 `CLI local executor` 관점에서 설계한다.
- 외부 실행기 연동은 기준 경로로 두지 않는다.
- 문서, 스키마, 실행 계층은 `CLI가 원본`이라는 가정 위에서 유지한다.
- workflow와 custom node 작업은 CLI 코어가 안정화된 이후 진행한다.

이 문서는 이후 구현 판단의 기준 문서로 사용한다.

---

## 7. 현재 구현 상태

현재 저장소에는 아래 단계까지 구현이 들어가 있다.

- `validate -> plan -> run` CLI 구조
- config schema / loader / manifest writer
- shot plan / extension plan / music plan / execution plan
- `aog/local_runtime` 아래 local python runtime 골격
- Wan 2.2 direct-call wrapper 초안
- Ace Step direct-call wrapper 초안
- local renderer 골격

현재 `local_runtime` 구성 파일:

- [bootstrap.py](/home/hosung/pytorch-demo/ComfyUI_AOG/aog/local_runtime/bootstrap.py)
- [wan_runtime.py](/home/hosung/pytorch-demo/ComfyUI_AOG/aog/local_runtime/wan_runtime.py)
- [ace_runtime.py](/home/hosung/pytorch-demo/ComfyUI_AOG/aog/local_runtime/ace_runtime.py)
- [renderer.py](/home/hosung/pytorch-demo/ComfyUI_AOG/aog/local_runtime/renderer.py)
- [image_audio.py](/home/hosung/pytorch-demo/ComfyUI_AOG/aog/local_runtime/image_audio.py)

아직 남아 있는 작업은 아래와 같다.

- Wan single-shot 실제 추론 검증
- last-frame chaining 실추론 검증
- Ace Step 실제 오디오 생성 검증
- 최종 mux/export 안정화

현재 기준 `run`의 기본 실행 경로는 `local python executor`다.
다음 구현은 문서 원칙대로 이 경로의 실제 추론 안정화에 집중한다.
