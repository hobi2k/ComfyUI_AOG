# ComfyUI_AOG

`ComfyUI_AOG` is a ComfyUI custom-node pack for turning a finished opening video into music that matches the video.

Current scope:

- analyze the input video with `MMAudio`
- analyze the same video semantically with `ComfyUI-QwenVL`
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

- `AOG Load Video Frames`
- `AOG MMAudio Feature Bundle`
- `AOG MMAudio SFX Bundle`
- `AOG QwenVL Bundle`
- `AOG Video Feature Extract`
- `AOG QwenVL Semantic Extract`
- `AOG Prompt Draft`
- `AOG Lyrics Draft`
- `AOG ACE-Step Compose`
- `AOG SFX Compose`
- `AOG Mux Video Audio`
- `AOG Opening Music Pipeline`

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

## CLI Runner

You can also run the current pipeline without opening the ComfyUI canvas:

```powershell
& ".\venv\Scripts\python.exe" ".\custom_nodes\ComfyUI_AOG\run_aog_audio_pipeline.py" `
  --video "D:\Stable Diffusion\aog\test\test.webm" `
  --output-dir ".\custom_nodes\ComfyUI_AOG\outputs\demo" `
  --title "Neon Run" `
  --theme "determined heroine racing through a dramatic city opening" `
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
- `QwenVL` is used for prompt and lyrics authoring.
- `MMAudio` is used for video feature extraction and optional SFX generation.
- `ACE-Step` is used for music generation.
- Direct raw MMAudio latent injection into ACE-Step is **not** implemented yet. The current system uses video-derived context to author better prompt and lyric inputs.
