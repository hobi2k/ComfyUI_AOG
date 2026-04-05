# Standalone Usage

이 문서는 AOG 노드를 shipped workflow 밖에서 부분적으로 가져다 쓸 때의 기준을 설명합니다.

## 원칙

### 1. 기능 노드와 UX 노드를 분리한다

AOG는 기능을 담당합니다.

- 분석
- authoring
- planning
- compose
- mix
- save
- preview metadata

토글과 bypass UX는 workflow 레이어에서 담당합니다.

- `rgthree`
- 또는 사용 중인 다른 switch / bypass 노드

### 2. 필요한 노드만 부분 사용해도 된다

예:

- `AOG Prompt Draft`만 가져다 써서 다른 음악 모델에 prompt를 공급
- `AOG Music Plan`만 가져다 써서 BPM과 key를 자동 결정
- `AOG Save Summary JSON`만 가져다 써서 다른 노드 메타를 저장

### 3. Preview는 두 층으로 나눈다

다른 workflow에 붙일 때는 다음처럼 생각하면 안전합니다.

- GUI용 preview: `VHS_VideoCombine`
- 저장/summary용 preview: `AOG Preview Video Combine`

## 예시 1. 다른 음악 생성기 앞에 Prompt Draft만 붙이기

1. `VHS_LoadVideo`
2. `AOG VHS Video Batch Adapter`
3. `AOG Video Feature Extract`
4. `AOG QwenVL Bundle`
5. `AOG Prompt Draft`
6. `PreviewAny`

이 구성은 ACE-Step이 없어도 독립적으로 유효합니다.

## 예시 2. Lyrics Draft만 가져다 쓰기

1. `VHS_LoadVideo`
2. `AOG VHS Video Batch Adapter`
3. `AOG Video Feature Extract`
4. `AOG QwenVL Bundle`
5. `AOG Lyrics Draft`
6. `PreviewAny`
7. `AOG Save Summary JSON`

이 구성은 가사 생성 실험이나 언어 테스트에 적합합니다.

## 예시 3. Music Plan만 다른 생성기에 붙이기

1. `VHS_LoadVideo`
2. `AOG VHS Video Batch Adapter`
3. `AOG Video Feature Extract`
4. `AOG QwenVL Bundle`
5. `AOG Music Plan`

다른 생성기가 아래 값만 받으면 붙일 수 있습니다.

- `bpm`
- `duration`
- `timesignature`
- `language`
- `key`

## 예시 4. SFX만 다른 믹싱 체인에 붙이기

1. `VHS_LoadVideo`
2. `AOG VHS Video Batch Adapter`
3. `AOG Video Feature Extract`
4. `AOG MMAudio SFX Bundle`
5. `AOG SFX Compose`

이후 출력 오디오는 다른 믹서나 mux 노드에 바로 붙이면 됩니다.

## 독립 사용 시 체크리스트

- input은 `AOG_VIDEO_BATCH`로 정규화했는가
- summary JSON이 필요한가
- GUI preview가 필요한가
- 최종 저장이 필요한가
- prompt/lyrics를 사람이 볼 수 있게 `PreviewAny`를 붙였는가
- 토글은 AOG가 아니라 workflow 레이어에서 처리하는가
