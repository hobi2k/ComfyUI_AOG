#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_ROOT="$(cd "${ROOT}/../.." && pwd)"
CUSTOM_NODES="${COMFY_ROOT}/custom_nodes"
MODELS="${COMFY_ROOT}/models"

if [[ -x "${COMFY_ROOT}/venv/bin/python" ]]; then
  PYTHON="${COMFY_ROOT}/venv/bin/python"
elif [[ -x "${COMFY_ROOT}/venv/Scripts/python.exe" ]]; then
  PYTHON="${COMFY_ROOT}/venv/Scripts/python.exe"
else
  echo "[error] Could not find a ComfyUI venv python at:"
  echo "        ${COMFY_ROOT}/venv/bin/python"
  echo "        ${COMFY_ROOT}/venv/Scripts/python.exe"
  exit 1
fi

ensure_repo() {
  local path="$1"
  local git_url="$2"
  if [[ -d "$path" ]]; then
    echo "[skip] repo exists: $path"
    return
  fi
  echo "[install] cloning $git_url -> $path"
  git clone "$git_url" "$path"
}

ensure_dir() {
  local path="$1"
  mkdir -p "$path"
}

ensure_hf_model() {
  local local_dir="$1"
  local repo_id="$2"
  if [[ -d "$local_dir" ]]; then
    echo "[skip] model exists: $local_dir"
    return
  fi
  echo "[install] hf download $repo_id -> $local_dir"
  hf download "$repo_id" --local-dir "$local_dir"
}

echo "[step] installing python requirements"
"$PYTHON" -m pip install -r "${ROOT}/requirements.txt"

echo "[step] ensuring external custom nodes"
ensure_repo "${CUSTOM_NODES}/ComfyUI-QwenVL" "https://github.com/1038lab/ComfyUI-QwenVL.git"
if [[ ! -d "${CUSTOM_NODES}/ComfyUI-MMAudio" ]]; then
  echo "[warn] ComfyUI-MMAudio is missing. Install it manually if this environment does not already provide it."
else
  echo "[skip] repo exists: ${CUSTOM_NODES}/ComfyUI-MMAudio"
fi
if [[ ! -d "${CUSTOM_NODES}/ComfyUI-VideoHelperSuite" ]]; then
  echo "[warn] ComfyUI-VideoHelperSuite is missing. Install it manually if this environment does not already provide it."
else
  echo "[skip] repo exists: ${CUSTOM_NODES}/ComfyUI-VideoHelperSuite"
fi

echo "[step] ensuring QwenVL models"
ensure_dir "${MODELS}/LLM/Qwen-VL"
ensure_hf_model "${MODELS}/LLM/Qwen-VL/Qwen3-VL-4B-Instruct" "Qwen/Qwen3-VL-4B-Instruct"

echo "[note] ACE-Step and MMAudio checkpoints are expected to be managed in the normal ComfyUI model folders."
echo "[done] dependency bootstrap finished."
