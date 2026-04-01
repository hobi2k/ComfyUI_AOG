# ComfyUI_AOG

`ComfyUI_AOG` is a ComfyUI custom-node pack for turning a finished opening video into music that matches the video.

Current scope:

- analyze the input video semantically with `ComfyUI-QwenVL`
- optionally enrich authoring with `MMAudio` timing, rhythm, and motion cues
- generate an ACE-Step prompt from video-derived cues
- generate ACE-Step lyrics from video-derived cues
- keep `prompt language` and `lyrics language` configurable
- keep `ACE-Step language` configurable
- optionally generate an MMAudio SFX layer
- mux the final audio back onto the original video without shortening the source clip

This project does **not** regenerate the video itself. The intended video reference is the external SVI workflow the team already trusts, such as:

- `user/default/workflows/svi.pro_workflow_mmmmn.json`

Audio reference workflows:

- `user/default/workflows/audio_ace_step_1_5_split_4b.json`
- `user/default/workflows/mmaudio_test.json`

## Node Groups

The package exposes these main nodes:

- `AOG Pipeline Toggles`
- `AOG Quality Preset`
- `AOG Load Video Frames`
- `AOG MMAudio Feature Bundle`
- `AOG MMAudio SFX Bundle`
- `AOG QwenVL Bundle`
- `AOG VHS Video Batch Adapter`
- `AOG Video Feature Extract`
- `AOG QwenVL Semantic Extract`
- `AOG Prompt Draft`
- `AOG Lyrics Draft`
- `AOG ACE-Step Compose`
- `AOG SFX Compose`
- `AOG Mux Video Audio`
- `AOG Preview Video Combine`
- `AOG Opening Music Pipeline`

Important workflow-facing behavior:

- Use `VHS_LoadVideo` for upload-friendly video selection in the ComfyUI canvas.
- Feed `VHS_LoadVideo` outputs into `AOG VHS Video Batch Adapter`.
- The shipped example workflows are designed so `upload video -> queue prompt` is enough.
  - No manual `source_path` entry is required in the upload workflows.
- End canvas workflows on `AOG Preview Video Combine` for in-UI video preview.
- The shipped example workflows are now decomposed graphs, not a single black-box pipeline node.
- Recommended canvas control path:
  - `AOG Pipeline Toggles`
  - `AOG Quality Preset`
  - `VHS_LoadVideo -> AOG VHS Video Batch Adapter`
  - explicit gate nodes
  - authoring / ACE-Step / SFX / mux nodes
- Graph-level skip behavior is implemented with dedicated gate nodes.
  - If a toggle is off, the related branch is blocked in-graph so ComfyUI can visibly skip it instead of silently running inside one large node.
- `AOG Pipeline Toggles` controls:
  - `enable_ace_step`
  - `enable_mmaudio_features`
  - `enable_qwenvl_analysis`
  - `enable_prompt_authoring`
  - `enable_lyrics_authoring`
  - `enable_sfx`
- `QwenVL analysis` does not require MMAudio feature extraction.
  - QwenVL can analyze the uploaded video directly.
  - MMAudio-derived cues are optional authoring enrichment.
- `QwenVL analysis`, `LLM prompt drafting`, and `LLM lyrics drafting` are intended to be used with `ACE-Step`.
  - If `enable_ace_step=false`, those controls are treated as effectively off inside the pipeline.
- `enable_mmaudio_features` means:
  - derive timing, rhythm, motion-strength, and structure cues from MMAudio
  - use them to enrich authoring context
  - keep them available for optional MMAudio SFX generation
  - it is not a prerequisite for QwenVL itself
- `AOG ACE-Step Compose` now uses `music_seed`, not `seed`.
- `AOG SFX Compose` now uses `sfx_seed`, not `seed`.
  - This is intentional. ComfyUI treats an input literally named `seed` as special and injects an extra frontend widget.
  - Renaming those inputs avoids widget-order corruption in saved workflows.
- Quality defaults are handled by:
  - `AOG Quality Preset`
  - `quality_profile = fast | balanced | high`
  - `apply_quality_profile = true | false`
- With `apply_quality_profile=true`, the pipeline automatically adjusts default:
  - ACE-Step steps / cfg / text cfg scale
  - MMAudio SFX steps / cfg
  - QwenVL frame count / token budget / temperature

## Recommended Language Policy

Recommended production configuration:

- prompt authoring language: `en`
- lyrics language: `ja` or the target singing language
- ACE-Step language: same as `lyrics language`

Example:

- prompt: English
- lyrics: Japanese
- ACE-Step language: Japanese

## Installation

1. Put this repo in:

```text
ComfyUI/custom_nodes/ComfyUI_AOG
```

2. Install Python requirements:

```powershell
cd "D:\Stable Diffusion\StabilityMatrix-win-x64\Data\Packages\ComfyUI"
& ".\venv\Scripts\python.exe" -m pip install -r ".\custom_nodes\ComfyUI_AOG\requirements.txt"
```

3. Install external custom nodes and models as needed:

```powershell
powershell -ExecutionPolicy Bypass -File ".\custom_nodes\ComfyUI_AOG\install_dependencies.ps1"
```

The installer is skip-safe. If a node or model is already present, it leaves it alone.

## Required External Nodes

- `ComfyUI-MMAudio`
- `ComfyUI-QwenVL`
- `ComfyUI-VideoHelperSuite`

## Required Models

### ACE-Step

- `models/diffusion_models/acestep_v1.5_turbo.safetensors`
- `models/text_encoders/qwen_0.6b_ace15.safetensors`
- `models/text_encoders/qwen_4b_ace15.safetensors`
- `models/vae/ace_1.5_vae.safetensors`

### MMAudio

- `models/diffusion_models/mmaudio_large_44k_v2_fp16.safetensors`
- `models/vae/mmaudio_vae_44k_fp16.safetensors`
- `models/audio_encoders/mmaudio_synchformer_fp16.safetensors`
- `models/clip_vision/apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors`

### QwenVL

Recommended:

- `models/LLM/Qwen-VL/Qwen3-VL-4B-Instruct`

Also supported:

- `models/LLM/Qwen-VL/Qwen3-VL-2B-Instruct`

## Example Workflows

This repo ships three example workflows in [workflows](/d:/Stable%20Diffusion/StabilityMatrix-win-x64/Data/Packages/ComfyUI/custom_nodes/ComfyUI_AOG/workflows):

- `AOG_QwenVL_Authoring.json`
- `AOG_ACE_Music_Only.json`
- `AOG_Full_Music_SFX_Mux.json`

The example workflows now follow this recommended ComfyUI pattern:

`VHS_LoadVideo -> AOG VHS Video Batch Adapter -> AOG Pipeline Toggles / AOG Quality Preset -> explicit gate nodes -> authoring / ACE-Step / SFX / mux -> AOG Preview Video Combine`

Notes on the three example workflows:

- `AOG_QwenVL_Authoring.json`
  - authoring-focused graph
  - shows QwenVL analysis plus prompt/lyric drafting branches
- `AOG_ACE_Music_Only.json`
  - music-only graph without SFX mixing
  - best for checking prompt/lyric quality and ACE-Step behavior
- `AOG_Full_Music_SFX_Mux.json`
  - full graph with optional MMAudio SFX and final mux
  - best reference for preview-ready end-to-end output

## Workflow Reload Note

- If you updated from an older build where the nodes still exposed plain `seed` inputs, you must restart ComfyUI before reloading the example workflows.
- If the canvas still shows broken defaults such as:
  - `bpm = NaN`
  - `timesignature = simple`
  - `ace_language = 1`
  then the server is still serving the old node definition from memory.
- Fix:
  - fully restart ComfyUI
  - refresh the browser tab
  - reload the workflow JSON

## CLI Runner

You can also run the current pipeline without opening the ComfyUI canvas:

```powershell
& ".\venv\Scripts\python.exe" ".\custom_nodes\ComfyUI_AOG\run_aog_audio_pipeline.py" `
  --video "D:\Stable Diffusion\aog\test\test.webm" `
  --output-dir ".\custom_nodes\ComfyUI_AOG\outputs\demo" `
  --prompt-mode llm `
  --lyrics-mode llm `
  --authoring-language en `
  --lyrics-language ja `
  --ace-language ja `
  --llm-provider qwenvl `
  --qwenvl-model "Qwen3-VL-4B-Instruct" `
  --steps 8 `
  --cfg 1.0 `
  --text-cfg-scale 5.0 `
  --sfx-mode auto
```

## Notes

- The pipeline preserves the full input video duration and muxes against the original video.
- `QwenVL` is the primary prompt/lyrics authoring analysis layer.
- `MMAudio` is optional authoring enrichment plus optional SFX generation.
- `ACE-Step` is used for music generation.
- Direct raw MMAudio latent injection into ACE-Step is **not** implemented yet. The current system uses video-derived context to author better prompt and lyric inputs.
