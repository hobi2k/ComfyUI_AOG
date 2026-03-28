# Environment And Experiment Runbook

## Baseline

- ComfyUI environment provides:
  - SVI video workflow
  - MMAudio custom node
  - ACE-Step models
  - ffmpeg
- Workflow references for implementation and verification:
  - `user/default/workflows/audio_ace_step_1_5_split_4b.json`
  - `user/default/workflows/mmaudio_test.json`
  - `ComfyUI-QwenVL` for video-semantic authoring analysis
- Preferred authoring stack:
  - `ComfyUI-QwenVL`
  - `models/LLM/Qwen-VL/Qwen3-VL-4B-Instruct`
  - keep `qwen_4b_ace15.safetensors` on the ACE-Step conditioning side

## Experiment Axes

### 1. Prompt Mode

- `human`
- `llm`

`llm` must use a real provider. No heuristic or fallback authoring path is allowed.

### 2. Lyrics Mode

- `human`
- `llm`

### 3. Lyrics Language

- `ko`
- `ja`
- `en`
- additional supported ACE-Step languages

`lyrics_language` should be tracked separately from `ace_language`, even if the default keeps them the same.

### 3a. Authoring Language

- `authoring_language`

Default policy:

- `authoring_language == lyrics_language == ace_language`

This should be treated as the standard mode unless a deliberate advanced override is needed.

### 4. Authoring Input Mode

- `summary_only`
- `summary_timeline_semantic`
- `summary_timeline_semantic_latent_derived`
- `qwenvl_semantic + mmaudio_structure`

`summary_only` is acceptable only as a temporary baseline.
The target authoring contract is `qwenvl_semantic + mmaudio_structure`.
This is the main practical path for improving ACE-Step quality before direct latent conditioning exists.
QwenVL should analyze the video directly.
MMAudio latent tensors do not need to be passed into QwenVL.
Instead, MMAudio contributes timing, rhythm, sync, and structure cues to the merged authoring contract.

### 5. Generation Conditioning Mode

- `text_meta_from_video_analysis`
- `direct_latent_conditioning_target`

`direct_latent_conditioning_target` is the highest-tier goal, not the baseline assumption.

### 6. SFX Mode

- `off`
- `auto_target`

## Recommended Experiment Order

1. Render a short clip in `svi.pro_workflow_mmmmn.json`.
2. Run feature extraction and inspect:
   - summary payload
   - structured timeline payload
   - semantic cue payload
   - conditioning summary contract
3. Compare music generation with:
   - text and metadata authored from video analysis
   - future direct conditioning targets
   Prioritize improvement of LLM-authored prompt and lyrics before attempting direct latent-conditioning research.
4. Compare prompt and lyric authoring with:
   - human prompt and human lyrics
   - LLM prompt and LLM lyrics
   - multiple lyric language settings
   - preferred authoring runtime: `ComfyUI-QwenVL` with `Qwen3-VL-4B-Instruct`
   - verify that LLM inputs include:
     - QwenVL scene analysis
     - summary
     - structured timeline
     - semantic scene cues
     - latent-derived structure cues
5. Add optional SFX generation after music-only quality is stable.
6. Review:
   - `ace_audio.wav`
   - optional `sfx_audio.wav`
   - `opening_final.mp4`
   - `feature_summary.json`
   - `run_summary.json`

## Current Focus

- improve music quality
- improve video-to-music synchronization
- improve latent-derived LLM authoring quality for ACE-Step prompt and lyrics
- separate summary features from latent and embedding features
- add structured timeline extraction
- add semantic scene cue extraction
- add human versus LLM authoring modes
- add explicit lyric language selection
- prepare optional effect generation

## Required Work Before Full Validation

- make MMAudio process the entire input video duration end to end
- finalize the full feature contract:
  - summary
  - structured timeline
  - semantic scene cues
  - latent-derived structure cues
- use `ComfyUI-QwenVL` with `Qwen3-VL-4B-Instruct` as the real authoring runtime
- generate ACE-Step-ready prompt text from the full feature contract
- generate ACE-Step-ready lyrics from the same contract and target language
- generate optional MMAudio SFX from the same analyzed clip
- mix music and SFX with controlled levels
- review the final mux by actual listening and viewing

## Definition Of A Meaningful Test

A test does not count as meaningful unless all of the following are true:

- the source clip duration is preserved end to end
- the authoring path uses a real LLM, not a substitute
- the prompt and lyrics are derived from the analyzed clip
- the final output contains the intended music bed and optional SFX
- the combined video is manually reviewed for real sync quality

## Implementation Checkpoint

- `qwenvl_full_loop1`, `qwenvl_full_loop2`, and `qwenvl_full_loop3` currently satisfy:
  - full-duration preservation
  - final video combine
  - QwenVL-based prompt and lyric authoring from analyzed video context
  - full target-tier SFX completion
- `authoring_context.json` should be inspected whenever prompt or lyric authoring is under review.
- Current release blockers:
  - higher-quality prompt and lyric refinement
  - repeated QwenVL model reload cost
  - stronger-than-text/meta generation conditioning

## Out Of Scope

- vocal conversion
- stem separation
- remix tuning
## Verified Local Runtime

- Authoring runtime: `ComfyUI-QwenVL`
- Verified model: `Qwen3-VL-4B-Instruct`
- No paid API dependency is required for the current authoring path.

## Latest Validated End-to-End Command

```powershell
& '.\venv\Scripts\python.exe' '.\custom_nodes\ComfyUI_AOG\run_aog_audio_pipeline.py' `
  --video 'D:\Stable Diffusion\aog\test\test.webm' `
  --output-dir '.\custom_nodes\ComfyUI_AOG\outputs\qwenvl_full_loop3' `
  --title 'Neon Run' `
  --theme 'determined heroine racing through a dramatic city opening' `
  --prompt-mode llm `
  --lyrics-mode llm `
  --authoring-language ja `
  --lyrics-language ja `
  --ace-language ja `
  --llm-provider qwenvl `
  --qwenvl-model 'Qwen3-VL-4B-Instruct' `
  --qwenvl-frame-count 8 `
  --seed 2 `
  --bpm 120 `
  --steps 1 `
  --cfg 1.0 `
  --max-seconds 0 `
  --video-force-rate 25 `
  --analysis-width 640 `
  --sfx-mode auto `
  --sfx-steps 4 `
  --sfx-cfg 3.5
```

## Expected Success Criteria

- `ace_audio.wav`, `sfx_audio.wav`, `final_mix.wav`, and `opening_final.mp4` all preserve full input duration
- `run_summary.json` contains authoring artifact paths
- `llm_prompt_request.json` and `llm_lyrics_request.json` contain `authoring_context_sha256`
- `opening_final.mp4` is muxed without `-shortest`
