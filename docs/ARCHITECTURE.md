# Architecture

`ComfyUI_AOG` is a thin video-to-music orchestration layer on top of a separately verified SVI video workflow.

## Scope

- Video generation stays in `svi.pro_workflow_mmmmn.json`
- AOG consumes the rendered video
- Workflow references:
  - `user/default/workflows/audio_ace_step_1_5_split_4b.json` is the ACE-Step-side reference workflow
  - `user/default/workflows/mmaudio_test.json` is the MMAudio-side reference workflow
  - `ComfyUI-QwenVL` is the preferred video-semantic-analysis reference for prompt and lyric authoring
- Current implementation is summary and derived-cue driven. Highest-tier direct conditioning remains a target.
- Practical core path:
  - use MMAudio-derived latent structure to produce better ACE-Step prompts and lyrics through real LLM authoring
  - do not downgrade latent information into simplistic rules or heuristics
- MMAudio extracts two different kinds of outputs:
  - machine-oriented latent and embedding features for music and SFX conditioning
  - LLM and human authoring features:
    - human-readable summary
    - structured timeline
    - semantic scene cues
- Highest-tier target: ACE-Step-adjacent generation uses:
  - text inputs
  - MMAudio analysis outputs
- Current implementation path:
  - ACE-Step receives text and metadata informed by video analysis
  - raw MMAudio payloads are not kept in the runtime contract
  - only derived summaries and cues are preserved in the runtime contract
- Optional prompt and lyric drafting may be done by a human or by an LLM
- Lyric drafting must support explicit language selection
- Prompt authoring language and ACE-Step generation language should default to the same configured language contract
- Optional video-aware SFX generation may be added as a separate output stem
- AOG muxes the generated audio back into the video
- Recommended authoring path:
  - use `ComfyUI-QwenVL` with `Qwen3-VL-4B-Instruct` for video-aware prompt and lyric authoring
  - keep `qwen_4b_ace15.safetensors` on the ACE-Step conditioning side
  - do not assume the ACE-Step text encoder checkpoint is a robust free-form authoring runtime
- Recommended semantic-analysis path:
  - use `ComfyUI-QwenVL` as the video-understanding layer
  - feed QwenVL with video frames or video frame sequences
  - do not route raw MMAudio latent tensors into QwenVL
  - instead, combine:
    - QwenVL visual-semantic analysis
    - MMAudio-derived timing, rhythm, and structure cues
  - then resolve ACE-Step prompt and lyrics from that merged authoring contract

## Current Validation Status

- `qwenvl_full_loop1`, `qwenvl_full_loop2`, and `qwenvl_full_loop3` proved that:
  - the full input clip can be preserved through music generation and final mux
  - the combined output keeps the original video stream and a generated audio stream
  - QwenVL-authored prompt generation runs from the same video clip plus merged authoring context
  - QwenVL-authored lyric generation runs from the same video clip plus merged authoring context
  - full-length SFX generation runs on top of the same clip
- Current release blockers:
- highest-tier generation conditioning beyond text/meta augmentation
- further prompt and lyric quality tuning
- reducing repeated QwenVL model reload cost in long validation runs
- Length policy is now:
  - preserve full source duration by default
  - normalize generated audio to the exact source duration before mux
  - do not use `-shortest` as the default mux policy
- `authoring_context.json` is part of the runtime trace and should contain:
  - summary
  - timeline
  - semantic cues
  - conditioning summary
  - latent-derived structure cues

## Feature Roles

### 1. Latent And Embedding Features

These are the high-value synchronization features.
They are intended for the generation-facing conditioning contract.
Until direct ACE-Step conditioning is available, they must also feed the LLM authoring contract in derived form.

Examples:

- motion-aligned temporal embedding
- sync-aligned video embedding
- latent pacing and transition cues

These should drive the target-tier generation contract:

- music timing
- intensity shifts
- transition emphasis
- optional effect cues

They should also drive the best currently practical authoring path:

- prompt structure
- lyric section placement
- hook timing
- imagery emphasis
- section-to-section escalation

### 2. Summary Features

These are reduced, human-readable features derived from the same video.

Examples:

- motion level
- motion peak
- brightness level
- duration
- shot pacing summary

These should drive:

- prompt writing
- lyric writing
- human review and editing
- LLM prompt and lyric drafting
- language-aware lyric generation

### 3. Structured Timeline

This is the main authoring bridge between video analysis and LLM writing.

Examples:

- shot boundaries
- transition timing
- local energy ramps
- climax window
- quiet window
- effect cue timings

These should drive:

- verse, pre-chorus, chorus placement
- line density
- cadence changes
- hook timing
- effect placement suggestions

### 4. Semantic Scene Cues

These are scene-level descriptions that help an LLM write text that actually matches what is visible.

Examples:

- subject action
- camera move type
- mood words
- recurring visual motifs
- scene tags

These should drive:

- prompt specificity
- lyric imagery
- repeated lyrical motifs
- section-to-section narrative coherence

## Primary Flow

1. External SVI workflow renders the video clip.
2. `AOG Load Video Frames` or `AOG Workflow Video Batch Adapter` converts that output into `AOG_VIDEO_BATCH`.
3. `AOG MMAudio Feature Bundle` loads MMAudio feature utilities.
4. `AOG Video Feature Extract` produces:
   - analysis-side conditioning summaries derived from latent and embedding analysis
   - reduced summary payloads
   - structured timeline payloads
   - semantic cue payloads
5. `QwenVL` analyzes the same video frames to produce richer scene-aware authoring context.
6. Prompt and lyric inputs are resolved in one of two ways:
   - human-written
   - LLM-generated from:
     - summary
     - structured timeline
     - semantic scene cues
     - latent-derived rhythm and structure cues
   Note:
   LLM inputs are not raw MMAudio latents.
   QwenVL does not require raw MMAudio latent tensors as input.
   The authoring layer should merge:
   - QwenVL video-semantic analysis
   - MMAudio-derived summary, timeline, and latent-derived structure cues
   This is the main practical path for improving ACE-Step alignment today.
   Current practical implementation:
   use `ComfyUI-QwenVL` with `Qwen3-VL-4B-Instruct` as the authoring runtime.
   QwenVL consumes the video directly and also receives merged MMAudio-derived authoring context in the prompt contract.
7. Lyric generation resolves two language-facing settings:
   - `authoring_language` for prompt and lyric generation
   - `ace_language` for the downstream ACE-Step generation contract
   Default policy:
   - `authoring_language == ace_language`
   - explicit mismatch should be treated as an advanced override, not the default
8. `AOG ACE-Step Compose` generates music from:
   - prompt
   - lyrics
   - timing and language metadata
   - optional reference audio
   while being informed by video analysis outputs
9. Optional SFX generation is a target-tier branch that may produce an additional effect stem from the same video features.
10. `AOG Mux Video Audio` combines the original video stream with generated audio.

## Supported Product Modes

### Mode 1: Human Prompt And Human Lyrics

- prompt source: human
- lyrics source: human
- lyrics language: explicitly selected
- music conditioning source: video analysis outputs, with raw conditioning payload preserved for future direct integration

### Mode 2: LLM Prompt And LLM Lyrics

- prompt source: LLM
- lyrics source: LLM
- lyrics language: explicitly selected
- drafting inputs:
  - video summary
  - structured timeline
  - semantic scene cues
  - latent-derived rhythm and structure cues
- music conditioning source: video analysis outputs, with authoring driven by summary, timeline, semantic cues, and latent-derived cues

### Mode 3: Optional SFX Layer

- available alongside mode 1 or mode 2
- MMAudio-derived video features also guide effect generation
- outputs may include:
  - music bed
  - optional SFX stem
  - final muxed video

## Custom Nodes

- `AOG MMAudio Feature Bundle`
- `AOG Load Video Frames`
- `AOG Workflow Video Batch Adapter`
- `AOG Video Feature Extract`
- `AOG Prompt Draft`
- `AOG Lyrics Draft`
- `AOG ACE-Step Compose`
- `AOG SFX Compose`
- `AOG Mux Video Audio`
- `AOG Opening Music Pipeline`

`AOG Prompt Draft`, `AOG Lyrics Draft`, and `AOG SFX Compose` represent the target-tier interface. Some implementations may still expose only a subset of that contract.
`AOG Prompt Draft` and `AOG Lyrics Draft` are the most important near-term quality path because ACE-Step currently benefits most from better authored inputs.

## Explicit Non-Goals

- No custom SVI video generation runtime inside AOG
- No vocal conversion
- No stem splitting or remix pipeline

## CLI Contract

The CLI runner should eventually support:

- external video input
- MMAudio feature extraction
- prompt mode selection:
  - `human`
  - `llm`
- lyrics mode selection:
  - `human`
  - `llm`
- lyrics language selection
- ACE-Step language selection
- when `llm` is used, authoring inputs should include:
  - summary
  - structured timeline
  - semantic scene cues
  - latent-derived structure cues
- ACE-Step composition informed by video analysis
- optional SFX generation
- final video mux

Core outputs:

- `ace_audio.wav`
- optional `sfx_audio.wav`
- `opening_final.mp4`
- `video_summary.json`
- `feature_summary.json`
- `run_summary.json`

## Language Contract

- `lyrics_language` controls the language that the lyric text is written in
- `ace_language` controls the language metadata passed into ACE-Step
- default behavior should keep them equal
- advanced mode may allow them to differ when intentionally needed
- No heuristic, fallback, or rule-based authoring path is allowed

## Recommended Authoring Runtime

- Preferred authoring model: `models/text_encoders/qwen_4b_ace15.safetensors`
- This model may be reused for two different roles:
  - ACE-Step internal text-conditioning path
  - AOG external authoring path for prompt and lyric generation
- These roles should be implemented as separate loads or separate runtime wrappers
- Do not assume the ACE-Step text encoder object can be directly reused as a general authoring LLM without a dedicated wrapper

## What Is Still Required

Before the final system can be considered complete, the following must exist:

- full-length MMAudio extraction for the full input video duration without unintended truncation
- a stable feature contract that preserves:
  - summary
  - structured timeline
  - semantic scene cues
  - latent-derived structure cues
- a real Qwen authoring runtime built on `qwen_4b_ace15.safetensors`
- prompt generation that produces ACE-Step-ready text aligned with the video arc
- lyric generation that produces ACE-Step-ready sectioned lyrics aligned with the same arc
- optional MMAudio-driven SFX generation that can be mixed without overwhelming the music bed
- final mux and review outputs that allow human verification of sync quality
## Current Verified Status

- `svi.pro_workflow_mmmmn.json` remains the authoritative video-generation workflow baseline.
- `audio_ace_step_1_5_split_4b.json` remains the authoritative ACE-Step workflow baseline.
- `mmaudio_test.json` remains the authoritative MMAudio and SFX workflow baseline.
- The current AOG implementation has verified `full input video duration` preservation through:
  - `AOGLoadVideoFrames`
  - `AOGVideoFeatureExtract`
  - `AOGAceStepCompose`
  - `AOGSFXCompose`
  - final mix normalization
  - final `ffmpeg` mux without `-shortest`
- Verified local LLM runtime is `Ollama + qwen3:4b`.
- Verified artifact chain is:
  - `authoring_context.json`
  - `llm_prompt_request/response.json`
  - `llm_lyrics_request/response.json`
  - `resolved_prompt.txt`
  - `resolved_lyrics.txt`
  - `run_summary.json`

## Current Verified Limits

- AOG currently proves `video-derived cues -> LLM authoring -> ACE-Step text conditioning`.
- AOG does not yet prove `raw MMAudio latent -> ACE-Step direct conditioning`.
- `conditioning_summary` and `latent_structure_cues` are preserved for future direct integration work.
- The prompt path is usable; the lyrics path is still not production-safe enough to treat as final-quality authoring.
