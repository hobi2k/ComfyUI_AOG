# ComfyUI_AOG

애니메이션 오프닝 제작에 특화된 CLI-first 프로젝트입니다.

문서:

- [프로젝트 기획서](/home/hosung/pytorch-demo/ComfyUI_AOG/docs/PROJECT_PLAN.md)
- [CLI 우선 아키텍처](/home/hosung/pytorch-demo/ComfyUI_AOG/docs/CLI_FIRST_ARCHITECTURE.md)
- [환경 정합성 가이드](/home/hosung/pytorch-demo/ComfyUI_AOG/docs/ENVIRONMENT_SYNC.md)
- [실험 세팅 가이드](/home/hosung/pytorch-demo/ComfyUI_AOG/docs/EXPERIMENT_SETUP.md)

설치:

```bash
cd /home/hosung/pytorch-demo/ComfyUI_AOG
uv venv --python 3.11
uv pip install torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0 --index-url https://download.pytorch.org/whl/cu130
uv pip install sageattention
uv pip install -e .
```

현재 local runtime 구현에 필요한 추가 의존성도 사용한다.

```bash
cd /home/hosung/pytorch-demo/ComfyUI_AOG
uv pip install safetensors av accelerate gguf einops transformers tokenizers sentencepiece aiohttp yarl requests simpleeval blake3 comfy-kitchen comfy-aimdo torchsde
```

CLI 흐름:

```bash
cd /home/hosung/pytorch-demo/ComfyUI_AOG
uv run aog validate examples/project.test_lastframe.yaml --validation-mode runtime --no-write
uv run aog plan examples/project.test_lastframe.yaml --validation-mode runtime --no-write
uv run aog run examples/project.test_lastframe.yaml --validation-mode runtime --no-write
```

메모:

- 현재 기준 개발 순서는 `ComfyUI와 독립적인 CLI 코어 구현 -> local python executor 완성 -> 이후 workflow/custom node 이식`입니다.
- 현재는 `aog/local_runtime` 아래에 local executor 골격이 추가된 상태입니다.
- `sageattention_required=false`인 설정에서는 WSL에서 `fallback_attention`으로 검증이 진행될 수 있습니다.
- `validate`는 설정과 런타임 조건을 점검합니다.
- `plan`은 `music_plan`, `execution_plan`, `output_plan`까지 포함한 실행 manifest를 만듭니다.
- `run --no-write`는 dry-run입니다.
- `run`은 현재 기준으로 local python executor를 통해 실제 추론과 export를 수행하는 주 경로입니다.
- 현재 세션에서는 GPU 드라이버 접근 제한 때문에 local runtime의 end-to-end 실제 추론 검증은 아직 완료되지 않았다.
- workflow와 custom node는 CLI 코어가 안정화된 뒤에 이식하는 단계다.
