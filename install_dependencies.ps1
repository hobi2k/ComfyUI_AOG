$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ComfyRoot = Split-Path -Parent $Root
$Python = Join-Path $ComfyRoot "venv\Scripts\python.exe"
$CustomNodes = Join-Path $ComfyRoot "custom_nodes"
$Models = Join-Path $ComfyRoot "models"

function Ensure-Repo {
    param(
        [string]$Path,
        [string]$GitUrl
    )
    if (Test-Path $Path) {
        Write-Host "[skip] repo exists: $Path"
        return
    }
    Write-Host "[install] cloning $GitUrl -> $Path"
    git clone $GitUrl $Path
}

function Ensure-Dir {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Ensure-HFModel {
    param(
        [string]$LocalDir,
        [string]$RepoId
    )
    if (Test-Path $LocalDir) {
        Write-Host "[skip] model exists: $LocalDir"
        return
    }
    Write-Host "[install] hf download $RepoId -> $LocalDir"
    hf download $RepoId --local-dir $LocalDir
}

Write-Host "[step] installing python requirements"
& $Python -m pip install -r (Join-Path $Root "requirements.txt")

Write-Host "[step] ensuring external custom nodes"
Ensure-Repo -Path (Join-Path $CustomNodes "ComfyUI-QwenVL") -GitUrl "https://github.com/1038lab/ComfyUI-QwenVL.git"
if (-not (Test-Path (Join-Path $CustomNodes "ComfyUI-MMAudio"))) {
    Write-Host "[warn] ComfyUI-MMAudio is missing. Install it manually if this environment does not already provide it."
} else {
    Write-Host "[skip] repo exists: $(Join-Path $CustomNodes 'ComfyUI-MMAudio')"
}
if (-not (Test-Path (Join-Path $CustomNodes "ComfyUI-VideoHelperSuite"))) {
    Write-Host "[warn] ComfyUI-VideoHelperSuite is missing. Install it manually if this environment does not already provide it."
} else {
    Write-Host "[skip] repo exists: $(Join-Path $CustomNodes 'ComfyUI-VideoHelperSuite')"
}

Write-Host "[step] ensuring QwenVL models"
Ensure-Dir (Join-Path $Models "LLM\Qwen-VL")
Ensure-HFModel -LocalDir (Join-Path $Models "LLM\Qwen-VL\Qwen3-VL-4B-Instruct") -RepoId "Qwen/Qwen3-VL-4B-Instruct"

Write-Host "[note] ACE-Step and MMAudio checkpoints are expected to be managed in the normal ComfyUI model folders."
Write-Host "[done] dependency bootstrap finished."
