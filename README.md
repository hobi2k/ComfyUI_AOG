# ComfyUI_AOG

Korean documentation: [README.ko.md](./README.ko.md)

`ComfyUI_AOG` is a ComfyUI custom-node pack for turning an already rendered opening video into matching music, optional SFX, saved summary metadata, and a previewable final video.

## Scope

- analyze the uploaded video semantically with `ComfyUI-QwenVL`
- optionally enrich authoring with `MMAudio` timing, rhythm, and motion cues
- generate an ACE-Step prompt from video-derived context
- generate ACE-Step lyrics from video-derived context
- automatically plan `bpm`, `duration`, `timesignature`, `ace_language`, and `keyscale`
- optionally generate an MMAudio SFX layer
- save summary JSON artifacts
- mux the generated audio back onto the original video without shortening the source clip

This project does **not** regenerate the video itself. Video generation stays in the external SVI workflow the team already trusts, for example:

- `user/default/workflows/svi.pro_workflow_mmmmn.json`

Audio-side reference workflows:

- `user/default/workflows/audio_ace_step_1_5_split_4b.json`
- `user/default/workflows/mmaudio_test.json`

## Node Roles

### AOG nodes

AOG owns the functional part of the pipeline:

- video batch adaptation
- feature extraction
- QwenVL semantic analysis
- prompt drafting
- lyrics drafting
- music planning
- ACE-Step composition
- MMAudio SFX composition
- final audio mixing
- summary JSON saving
- preview/save video combine

Main AOG nodes:

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
- `AOG Music Plan`
- `AOG ACE-Step Compose`
- `AOG SFX Compose`
- `AOG Final Audio Mix`
- `AOG Mux Video Audio`
- `AOG Preview Video Combine`
- `AOG Save Summary JSON`

### rgthree

`rgthree` is used in the shipped example workflows for canvas-level toggle UX only.

- group mute / bypass
- branch-level skip visualization
- workflow ergonomics

In other words:

- `AOG` handles functionality
- `rgthree` handles workflow-level toggling

## Workflow Contract

- Upload-first workflows must start from `VHS_LoadVideo`.
- `VHS_LoadVideo` outputs should feed `AOG VHS Video Batch Adapter`.
- No manual `source_path` entry is required in the shipped upload workflows.
- End runnable workflows on `AOG Preview Video Combine` for save + in-UI preview behavior.
- Save summary metadata with `AOG Save Summary JSON`.
- Example workflows are decomposed graphs, not one black-box node.

Recommended canvas pattern:

`VHS_LoadVideo -> AOG VHS Video Batch Adapter -> AOG Quality Preset -> AOG analysis / authoring / planning / compose / save / preview`

Use `rgthree` group controls to mute or bypass optional branches in the canvas.

## Language Policy

Recommended production defaults:

- prompt authoring language: `en`
- lyrics language: `ja` or the target singing language
- ACE-Step language: same as `lyrics language`

Example:

- prompt: English
- lyrics: Japanese
- ACE-Step language: Japanese

Recommended SFX defaults:

- `sfx_prompt_mode = llm`
- `llm_provider = qwenvl`
- `authoring_language = en`

## Music Planning

`AOG Music Plan` resolves:

- `bpm`
- `duration`
- `timesignature`
- `ace_language`
- `keyscale`

Policy:

- `duration` comes from the input video length
- in `plan_mode = llm`, the model resolves the remaining musical settings from analyzed video context
- in `plan_mode = human`, manual overrides are allowed

## Installation

1. Put this repo in:

```text
ComfyUI/custom_nodes/ComfyUI_AOG
```

2. Install Python requirements:

Windows:

```powershell
cd "<ComfyUI root>"
& ".\venv\Scripts\python.exe" -m pip install -r ".\custom_nodes\ComfyUI_AOG\requirements.txt"
```

Linux/macOS:

```bash
cd "<ComfyUI root>"
./venv/bin/python -m pip install -r "./custom_nodes/ComfyUI_AOG/requirements.txt"
```

3. Install external custom nodes and models as needed:

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File ".\custom_nodes\ComfyUI_AOG\install_dependencies.ps1"
```

Linux/macOS:

```bash
bash ./custom_nodes/ComfyUI_AOG/install_dependencies.sh
```

The installers are skip-safe. If a node or model is already present, they leave it alone.

## Required External Nodes

- `ComfyUI-MMAudio`
- `ComfyUI-QwenVL`
- `ComfyUI-VideoHelperSuite`
- `rgthree-comfy`

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

This repo ships three runnable example workflows in [workflows](./workflows):

- `AOG_ACE_Music_Only.json`
- `AOG_Full_Music_SFX_Mux.json`
- `AOG_MMAudio_SFX_Only.json`

Workflow intent:

- `AOG_ACE_Music_Only.json`
  - music-only graph without SFX mixing
  - best for checking prompt/lyric quality and ACE-Step behavior
- `AOG_Full_Music_SFX_Mux.json`
  - full graph with ACE-Step, MMAudio SFX, final mix, summary save, and preview save
  - best reference for end-to-end output
- `AOG_MMAudio_SFX_Only.json`
  - SFX-only graph without ACE-Step music generation
  - best for validating MMAudio SFX generation, save behavior, and preview behavior in isolation

## Workflow Reload Note

- If you updated from an older build where nodes still exposed plain `seed` inputs, restart ComfyUI before reloading example workflows.
- If the canvas still shows broken defaults such as:
  - `bpm = NaN`
  - `timesignature = simple`
  - `ace_language = 1`
  then the server is still serving an old node definition from memory.

Fix:

- fully restart ComfyUI
- refresh the browser tab
- reload the workflow JSON

## CLI Runner

You can also run the current pipeline without opening the ComfyUI canvas:

```powershell
& ".\venv\Scripts\python.exe" ".\custom_nodes\ComfyUI_AOG\run_aog_audio_pipeline.py" `
  --video ".\output\example_input.webm" `
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

- The pipeline preserves full input duration and muxes against the original video.
- `QwenVL` is the primary prompt/lyrics authoring analysis layer.
- `MMAudio` is optional authoring enrichment plus optional SFX generation.
- `ACE-Step` is used for music generation.
- Direct raw MMAudio latent injection into ACE-Step is **not** implemented yet.
