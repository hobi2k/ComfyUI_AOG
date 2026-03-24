"""Resolve ComfyUI root paths and model loader names for local execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ComfyPathError(ValueError):
    """
    ComfyUI 설치 루트를 모델 경로에서 추론할 수 없을 때 발생한다.
    """


@dataclass(slots=True)
class ComfyPaths:
    """
    로컬 런타임이 사용할 ComfyUI 루트와 모델 경로 계산기를 보관한다.

    Args:
        root_dir: ComfyUI 설치 루트다.
        input_dir: ComfyUI 입력 디렉터리다.
        output_dir: ComfyUI 출력 디렉터리다.
    """

    root_dir: Path
    input_dir: Path
    output_dir: Path

    @classmethod
    def from_model_path(cls, model_path: str) -> "ComfyPaths":
        """
        모델 파일 절대경로에서 ComfyUI 루트를 역추적한다.

        Args:
            model_path: `ComfyUI/models/...` 아래에 있는 모델 파일 경로다.

        Returns:
            로컬 실행에 필요한 ComfyUI 경로 묶음이다.
        """
        root_dir = cls._infer_root_dir(Path(model_path))
        return cls(
            root_dir=root_dir,
            input_dir=root_dir / "input",
            output_dir=root_dir / "output",
        )

    @staticmethod
    def _infer_root_dir(path: Path) -> Path:
        """
        모델 경로에서 `models` 디렉터리를 찾고 ComfyUI 루트를 계산한다.

        Args:
            path: 검사할 모델 파일 경로다.

        Returns:
            추론된 ComfyUI 루트 경로다.
        """
        resolved = path.resolve()
        for parent in resolved.parents:
            if parent.name == "models":
                return parent.parent
        raise ComfyPathError(f"Could not infer ComfyUI root from path: {path}")

    def relative_model_name(self, path: str, category: str) -> str:
        """
        절대 모델 경로를 ComfyUI 로더가 요구하는 카테고리 상대경로로 바꾼다.

        Args:
            path: 모델 절대경로다.
            category: `diffusion_models`, `vae` 같은 ComfyUI 카테고리다.

        Returns:
            로더 노드가 바로 쓸 수 있는 카테고리 기준 상대경로다.
        """
        category_root = self.root_dir / "models" / category
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(category_root)
        except ValueError as exc:
            raise ComfyPathError(
                f"Model path is not inside ComfyUI/models/{category}: {path}"
            ) from exc
        return relative.as_posix()
