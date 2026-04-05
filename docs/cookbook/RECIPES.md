# Recipes

자주 쓰는 조합만 바로 가져다 쓸 수 있게 정리한 레시피입니다.

## 1. 영상 분석만 하고 프롬프트/가사 확인

추천 노드 순서:

1. `VHS_LoadVideo`
2. `AOG VHS Video Batch Adapter`
3. `AOG MMAudio Feature Bundle` 선택
4. `AOG Video Feature Extract`
5. `AOG QwenVL Bundle`
6. `AOG QwenVL Semantic Extract`
7. `AOG Prompt Draft`
8. `AOG Lyrics Draft`
9. `PreviewAny` for prompt
10. `PreviewAny` for lyrics
11. `AOG Merge Summary JSON`
12. `AOG Save Summary JSON`

언제 쓰나:

- prompt가 영상에 맞는지 먼저 보고 싶을 때
- lyrics 언어와 이미지가 맞는지 먼저 보고 싶을 때

## 2. ACE-Step music only

추천 노드 순서:

1. `VHS_LoadVideo`
2. `AOG VHS Video Batch Adapter`
3. `AOG MMAudio Feature Bundle`
4. `AOG Video Feature Extract`
5. `AOG QwenVL Bundle`
6. `AOG Prompt Draft`
7. `AOG Lyrics Draft`
8. `AOG Music Plan`
9. `UNETLoader`
10. `DualCLIPLoader`
11. `VAELoader`
12. `AOG ACE-Step Compose`
13. `AOG Merge Summary JSON`
14. `AOG Save Summary JSON`
15. `AOG Preview Video Combine`
16. `VHS_VideoCombine`

핵심:

- prompt/lyrics는 LLM 또는 human 둘 다 가능
- `AOG Music Plan`이 bpm, duration, timesignature, language, keyscale을 결정
- GUI preview는 `VHS_VideoCombine`

## 3. MMAudio SFX only

추천 노드 순서:

1. `VHS_LoadVideo`
2. `AOG VHS Video Batch Adapter`
3. `AOG MMAudio Feature Bundle`
4. `AOG Video Feature Extract`
5. `AOG MMAudio SFX Bundle`
6. 필요 시 `AOG QwenVL Bundle`
7. `AOG SFX Compose`
8. `AOG Merge Summary JSON`
9. `AOG Save Summary JSON`
10. `AOG Preview Video Combine`
11. `VHS_VideoCombine`

언제 쓰나:

- 음악 없이 효과음만 테스트하고 싶을 때
- SFX steps/cfg/gain만 따로 튜닝하고 싶을 때

## 4. full music + SFX + mux

추천 노드 순서:

1. `VHS_LoadVideo`
2. `AOG VHS Video Batch Adapter`
3. `AOG MMAudio Feature Bundle`
4. `AOG Video Feature Extract`
5. `AOG QwenVL Bundle`
6. `AOG Prompt Draft`
7. `AOG Lyrics Draft`
8. `AOG Music Plan`
9. `UNETLoader`
10. `DualCLIPLoader`
11. `VAELoader`
12. `AOG ACE-Step Compose`
13. `AOG MMAudio SFX Bundle`
14. `AOG SFX Compose`
15. `AOG Final Audio Mix`
16. `AOG Merge Summary JSON`
17. `AOG Save Summary JSON`
18. `AOG Preview Video Combine`
19. `VHS_VideoCombine`

캔버스 팁:

- Prompt Preview와 Lyrics Preview는 따로 눈에 띄는 위치에 둔다.
- Save Summary JSON은 preview 근처에 둔다.
- GUI preview는 맨 오른쪽 output 영역에 둔다.

## 5. 토글은 어떻게 관리하나

권장:

- AOG 노드 자체에 토글 책임을 몰지 않는다.
- `rgthree`로 그룹 mute/bypass를 만든다.

추천 그룹:

- Input
- Video Features
- Authoring
- ACE-Step
- MMAudio SFX
- Output

이렇게 두면 노드는 독립적으로 유지되고, 워크플로우 UX만 좋아집니다.
