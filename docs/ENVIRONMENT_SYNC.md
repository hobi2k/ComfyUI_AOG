# Environment Sync

## 목적

이 문서는 `ComfyUI_AOG`의 `uv` 기반 개발 환경을 Windows ComfyUI 실행 환경과 최대한 맞추기 위한 기준 문서다.

현재 개발 순서는 `WSL/Linux에서 먼저 동작 검증 -> 이후 Windows ComfyUI 환경과 정합성 맞추기`를 기본으로 한다.

핵심 원칙은 아래와 같다.

- 먼저 WSL/Linux에서 CLI와 manifest 검증이 동작해야 한다.
- 공통 Python 라이브러리 버전은 Windows ComfyUI 환경과 맞춘다.
- `torch/cu130` 계열은 Windows ComfyUI 환경과 동일한 조합을 사용한다.
- `sageattention`은 Windows wheel을 사용한다.
- `ComfyUI_AOG`는 ComfyUI 전체 환경을 복제하기보다, 파이프라인 검증과 manifest 생성에 필요한 버전을 우선 맞춘다.

---

## 기준 환경

현재 Windows ComfyUI 환경에서 확인된 주요 버전은 아래와 같다.

### Python 런타임

- Python: 3.11 계열로 맞춘다

### PyTorch

- `torch==2.10.0+cu130`
- `torchvision==0.25.0+cu130`
- `torchaudio==2.10.0+cu130`

### 공통 라이브러리

- `numpy==2.3.5`
- `Pillow==12.0.0`
- `PyYAML==6.0.3`
- `httpx==0.28.1`
- `librosa==0.11.0`
- `soundfile==0.13.1`
- `tqdm==4.67.3`

### SageAttention

Windows wheel:

```text
https://github.com/woct0rdho/SageAttention/releases/download/v2.2.0-windows.post4/sageattention-2.2.0+cu130torch2.9.0andhigher.post4-cp39-abi3-win_amd64.whl
```

이 wheel은 `torch 2.9.0 and higher`, `cu130`, `Windows amd64` 기준이다.

---

## uv 설치 절차

프로젝트 루트에서 아래 순서로 설치한다.

```bash
uv venv --python 3.11
uv pip install torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0 --index-url https://download.pytorch.org/whl/cu130
uv pip install "https://github.com/woct0rdho/SageAttention/releases/download/v2.2.0-windows.post4/sageattention-2.2.0+cu130torch2.9.0andhigher.post4-cp39-abi3-win_amd64.whl"
uv pip install -e .
```

WSL에서 먼저 확인할 때는 `sageattention`이 없어도 된다.
이 경우 런타임 검증 노드는 `fallback_attention`으로 전환된 상태를 payload에 기록한다.
즉, `sageattention_required=false`인 설정에서는 WSL 검증이 우선이고, 이후 Windows ComfyUI 쪽에서 가속 경로를 맞춘다.

필요 시 dev 도구:

```bash
uv pip install -e ".[dev]"
```

---

## 설치 확인

### torch / cuda

```bash
uv run python -c "import torch; print(torch.__version__, torch.version.cuda)"
uv run python -c "import torchvision, torchaudio; print(torchvision.__version__, torchaudio.__version__)"
```

기대값:

- `2.10.0+cu130`
- `0.25.0+cu130`
- `2.10.0+cu130`

### sageattention

```bash
uv run python -c "import sageattention; print(sageattention.__file__)"
```

### AOG CLI

```bash
uv run aog validate examples/project.video_first.yaml --validation-mode example --no-write
uv run aog validate examples/project.music_first.yaml --validation-mode example --no-write
```

WSL 기준으로는 아래 항목을 먼저 본다.

- 스키마 파싱 성공
- shot_plan 생성 성공
- extension_source 생성 성공
- output_plan 생성 성공
- `runtime_validation.selected_attention_backend` 확인

즉, WSL에서 `sageattention`이 없더라도 `fallback_attention`으로 검증이 진행되면 1차 구조 검증은 통과한 것으로 본다.

---

## 왜 torch는 pyproject 기본 의존성에 고정하지 않았는가

`torch==2.10.0+cu130` 조합은 일반 Python 패키지 의존성과 다르게 다음 조건에 민감하다.

- 운영체제
- CUDA 버전
- wheel index URL
- GPU 런타임 환경

그래서 `pyproject.toml` 기본 의존성에는 넣지 않고, 환경 동기화 문서에서 `uv pip install ... --index-url ...` 방식으로 설치하는 쪽이 더 안전하다.

---

## 왜 ffmpeg-python은 기본 의존성에 넣지 않았는가

현재 Windows ComfyUI 환경에서 `ffmpeg-python` 패키지는 설치되어 있지 않았다.
프로젝트는 추후 `ffmpeg` 바이너리 직접 호출 방식으로 후처리를 수행하는 편이 ComfyUI 환경 정합성 면에서 더 안전하다.

즉:

- 이미지/오디오 처리 라이브러리는 Python 패키지로 맞춘다.
- 영상 인코딩은 가능하면 시스템 `ffmpeg` 실행으로 분리한다.

---

## 환경 정합성 체크 명령

Windows ComfyUI 쪽 환경 비교용 명령:

```powershell
pip show torch torchvision torchaudio
pip show numpy pillow pyyaml httpx librosa soundfile tqdm
```

`ComfyUI_AOG` 쪽 비교용 명령:

```bash
uv run python -c "import torch, torchvision, torchaudio, numpy, PIL, yaml, httpx, librosa, soundfile, tqdm; print(torch.__version__); print(torchvision.__version__); print(torchaudio.__version__); print(numpy.__version__); print(PIL.__version__); print(yaml.__version__); print(httpx.__version__); print(librosa.__version__); print(soundfile.__version__); print(tqdm.__version__)"
```

---

## 관련 파일

- [pyproject.toml](/home/hosung/pytorch-demo/ComfyUI_AOG/pyproject.toml)
- [requirements.txt](/home/hosung/pytorch-demo/ComfyUI_AOG/requirements.txt)
- [PROJECT_PLAN.md](/home/hosung/pytorch-demo/ComfyUI_AOG/docs/PROJECT_PLAN.md)
