# ComfyUI_AOG

애니메이션 오프닝 제작에 특화된 ComfyUI-first 프로젝트입니다.

권장 작업 위치:

- `D:\Stable Diffusion\StabilityMatrix-win-x64\Data\Packages\ComfyUI\custom_nodes\ComfyUI_AOG`

즉 이 프로젝트는 WSL 바깥의 별도 독립 루트보다, Windows에 설치된 ComfyUI 폴더의 `custom_nodes` 아래에서 개발하는 것을 기준으로 합니다.

문서:

- [프로젝트 기획서](/home/hosung/pytorch-demo/ComfyUI_AOG/docs/PROJECT_PLAN.md)
- [ComfyUI 우선 아키텍처](/home/hosung/pytorch-demo/ComfyUI_AOG/docs/COMFYUI_FIRST_ARCHITECTURE.md)
- [이전 CLI 문서](/home/hosung/pytorch-demo/ComfyUI_AOG/docs/CLI_FIRST_ARCHITECTURE.md)
- [환경 정합성 가이드](/home/hosung/pytorch-demo/ComfyUI_AOG/docs/ENVIRONMENT_SYNC.md)
- [실험 세팅 가이드](/home/hosung/pytorch-demo/ComfyUI_AOG/docs/EXPERIMENT_SETUP.md)

설치:

```bash
cd /path/to/ComfyUI/custom_nodes/ComfyUI_AOG
uv venv --python 3.11
uv pip install torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0 --index-url https://download.pytorch.org/whl/cu130
uv pip install sageattention
uv pip install -e .
```

현재 local runtime은 설치된 ComfyUI 런타임과 custom node를 직접 import해 사용한다.

```bash
cd /path/to/ComfyUI/custom_nodes/ComfyUI_AOG
uv pip install safetensors av accelerate gguf ftfy diffusers einops transformers tokenizers sentencepiece aiohttp yarl requests simpleeval blake3 comfy-kitchen comfy-aimdo torchsde
```

CLI 흐름:

```bash
cd /path/to/ComfyUI/custom_nodes/ComfyUI_AOG
uv run aog validate examples/project.test_lastframe.yaml --validation-mode runtime --no-write
uv run aog plan examples/project.test_lastframe.yaml --validation-mode runtime --no-write
uv run aog run examples/project.test_lastframe.yaml --validation-mode runtime --no-write
```

메모:

- 현재 기준 개발 순서는 `ComfyUI 설치 -> custom node 개발 -> workflow 구성 -> 필요 시 headless CLI 보조`입니다.
- 프로젝트 루트는 원칙적으로 `ComfyUI/custom_nodes/ComfyUI_AOG` 아래에 둡니다.
- 현재 `aog/local_runtime`는 ComfyUI 설치본을 사용하는 headless runtime입니다.
- `sageattention_required=false`인 설정에서는 WSL에서 `fallback_attention`으로 검증이 진행될 수 있습니다.
- `validate`는 설정과 런타임 조건을 점검합니다.
- `plan`은 `music_plan`, `execution_plan`, `output_plan`까지 포함한 실행 manifest를 만듭니다.
- `run --no-write`는 dry-run입니다.
- `run`은 설치된 ComfyUI 런타임을 headless로 사용해 실제 추론과 export를 수행하는 보조 경로입니다.
- 현재 세션에서는 GPU 드라이버 접근 제한 때문에 local runtime의 end-to-end 실제 추론 검증은 아직 완료되지 않았다.
- workflow와 custom node가 기준 산출물이고, CLI는 이를 보조하는 자동화 층이다.
