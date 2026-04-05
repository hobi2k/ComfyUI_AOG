# Troubleshooting

자주 부딪히는 문제를 AOG 노드 관점에서 정리합니다.

## 1. prompt와 lyrics가 노드에서 안 보인다

원인:

- 텍스트 출력만 있고 캔버스에 보여줄 preview 노드가 없음

권장 해결:

- `AOG Prompt Draft -> PreviewAny`
- `AOG Lyrics Draft -> PreviewAny`

추가 확인:

- final summary JSON에 `prompt_text`, `lyrics_text`가 병합되는지

## 2. summary JSON에 메타가 빈약하다

원인:

- 각 단계 summary를 병합하지 않았음

권장 해결:

1. `AOG Merge Summary JSON`
2. `AOG Save Summary JSON`

확인 항목:

- `prompt_summary`
- `lyrics_summary`
- `music_plan_summary`
- `ace_summary`
- `sfx_summary`
- `preview_summary`
- `prompt_text`
- `lyrics_text`

## 3. final video preview가 안 보인다

원인:

- 저장 노드만 있고 GUI preview 노드가 없음

권장 해결:

- `AOG Preview Video Combine`는 저장/preview summary용
- `VHS_VideoCombine`를 병렬로 추가해 GUI preview용으로 사용

## 4. widget 값이 밀린다

증상 예:

- `bpm = NaN`
- `timesignature = simple`
- `ace_language = 1`

원인:

- workflow JSON의 `widgets_values` 순서가 현재 node 정의와 안 맞음

권장 해결:

- shipped workflow를 다시 불러온다
- 오래된 캔버스를 재사용하지 않는다
- seed 계열 special widget 영향을 받는 입력 순서를 특히 점검한다

## 5. SFX만 켰더니 저장이 안 된다

권장 체크:

- final output 체인이 audio 없음 상태에서 끊기지 않는지
- `AOG Final Audio Mix`가 sfx-only를 허용하는지
- preview/save 노드가 최종 오디오를 실제로 받고 있는지

## 6. 노드는 독립적인데 토글이 복잡하다

권장:

- AOG 노드에 토글 책임을 넣지 않는다
- `rgthree` group mute/bypass를 쓴다

## 7. duration이 영상 길이와 안 맞는다

확인:

- `AOG Music Plan.duration`
- `AOG_VIDEO_BATCH.loaded_duration_sec`
- final normalize / mux 단계

정책:

- 입력 영상 전체 길이를 유지하는 것이 기본이다
