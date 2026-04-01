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
MMAudio feature extraction is optional for this authoring path.
MMAudio latent tensors do not need to be passed into QwenVL.
Instead, when enabled, MMAudio contributes timing, rhythm, sync, and structure cues to the merged authoring contract.

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
     - optional summary
     - optional structured timeline
     - optional semantic scene cues
     - optional latent-derived structure cues
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

## Bug Fixes Applied (2026-04-01)

The following bugs were found and corrected:

### `run_aog_audio_pipeline.py`

- All node method calls were missing the `enabled` positional argument added when the `enabled` parameter was introduced to each node.
  Affected: `AOGVideoFeatureExtract.extract_features`, `AOGQwenVLSemanticExtract.extract`, `AOGPromptDraft.draft`, `AOGLyricsDraft.draft`, `AOGAceStepCompose.compose`, `AOGSFXCompose.compose`.
- `AOGPromptDraft.draft` and `AOGLyricsDraft.draft` were called with `llm_model`, `title`, and `theme` keyword arguments that do not exist in the node method signatures.
  These have been removed from the CLI calls. `title` and `theme` remain as CLI arguments and appear in run metadata artifacts only.
- `keep_model_loaded` in the QwenVL bundle was respecting `--qwenvl-keep-model-loaded` (default False), causing the QwenVL model to reload three times during a single run (scene analysis, prompt, lyrics), each taking approximately 3.5 minutes.
  Fixed by forcing `keep_model_loaded=True` in the CLI bundle. The existing `unload_all_models()` call before ACE-Step loading handles VRAM cleanup.

### All three workflow JSON files

- `AOGLyricsDraft` (`AOG Lyrics Draft` node) had `qwenvl_bundle` connected to input slot 7.
  The correct slot is 8, because `authoring_language` occupies slot 7 ahead of the optional `qwenvl_bundle`.
  Fixed in `AOG_ACE_Music_Only.json`, `AOG_QwenVL_Authoring.json`, and `AOG_Full_Music_SFX_Mux.json`.

### `AOG_Full_Music_SFX_Mux.json` only

- `AOG SFX Stage Gate` (node 22) had stale link references for `pipeline_toggles` (link 34) and `mmaudio_featureutils` (link 35).
  The actual `links` array had link 34 going from `UNETLoader` to `AOG ACE Stage Gate` (MODEL), and link 35 going from `DualCLIPLoader` to `AOG ACE Stage Gate` (CLIP).
  The SFX Stage Gate was effectively disconnected for both required inputs.
  Fixed by adding link 48 (`AOG_PIPELINE_TOGGLES` from Pipeline Toggles to SFX Stage Gate slot 0) and link 49 (`MMAUDIO_FEATUREUTILS` from MMAudio Feature Bundle to SFX Stage Gate slot 1).

## Bug Fixes Applied (2026-04-02)

- Saved workflow widget corruption was traced to custom nodes exposing an input literally named `seed`.
- ComfyUI injects an extra frontend control for such inputs, which caused downstream widget values to shift in saved JSON workflows.
- Symptoms included:
  - `bpm = NaN`
  - `timesignature = simple`
  - `ace_language = 1`
- Fix:
  - `AOG ACE-Step Compose`: renamed `seed` -> `music_seed`
  - `AOG SFX Compose`: renamed `seed` -> `sfx_seed`
  - example workflow defaults were rewritten against the new input order
- Operational note:
  - a full ComfyUI restart is required after this node-definition change
  - otherwise the server may continue serving the old `seed`-based node schema from memory

## Out Of Scope

- vocal conversion
- stem separation
- remix tuning
## Verified Local Runtime

- Authoring runtime: `ComfyUI-QwenVL`
- Verified model: `Qwen3-VL-4B-Instruct`
- No paid API dependency is required for the current authoring path.

## Latest Validated End-to-End Command

Validated 2026-04-01 with `120752-01_00001.webm`.
Run from the ComfyUI root directory.

```powershell
python '.\custom_nodes\ComfyUI_AOG\run_aog_audio_pipeline.py' `
  --video 'D:\Stable Diffusion\StabilityMatrix-win-x64\Data\Packages\ComfyUI\output\WAN\04-01\120752-01_00001.webm' `
  --output-dir '.\custom_nodes\ComfyUI_AOG\outputs\run_04-01' `
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
  --steps 8 `
  --cfg 1.0 `
  --text-cfg-scale 5.0 `
  --max-seconds 0 `
  --video-force-rate 25 `
  --analysis-width 640 `
  --sfx-mode off
```

Notes on CLI arguments:
- `--title` and `--theme` are accepted but appear only in run metadata artifacts, not in the LLM authoring context.
- `--qwenvl-keep-model-loaded` is ignored by the CLI; the pipeline forces `keep_model_loaded=True` internally to avoid three separate model reloads across scene analysis, prompt, and lyrics steps. `unload_all_models()` before ACE-Step loading handles VRAM cleanup.
- A QwenVL FPS warning ("Asked to sample fps frames per second but no video metadata was provided, defaulting to fps=24") appears during video processing. This is a transformers internal warning and does not affect output quality or frame selection.
- A `ModelPatcher.__del__ AttributeError` appears at process exit. This is a ComfyUI-internal shutdown cleanup issue, not an AOG error. All outputs are fully written before this occurs.

## Expected Success Criteria

- `ace_audio.wav`, `sfx_audio.wav`, `final_mix.wav`, and `opening_final.mp4` all preserve full input duration
- `run_summary.json` contains authoring artifact paths
- `llm_prompt_request.json` and `llm_lyrics_request.json` contain `authoring_context_sha256`
- `opening_final.mp4` is muxed without `-shortest`
