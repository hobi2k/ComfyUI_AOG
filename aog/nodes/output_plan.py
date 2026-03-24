"""Build output paths and optional manifest files for a planned render."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aog.config.schema import AOGProjectConfig

from .base import BaseNode, NodeResult


class OutputPlanNode(BaseNode):
    """Prepare output paths and write planning manifests when requested."""

    name = "output_plan"

    def run(
        self,
        *,
        config: AOGProjectConfig,
        runtime_validation: dict[str, Any] | None = None,
        model_bundles: dict[str, Any] | None = None,
        shot_plan: dict[str, Any],
        extension_plan: dict[str, Any],
        music_plan: dict[str, Any] | None = None,
        execution_plan: dict[str, Any] | None = None,
        write_files: bool = True,
    ) -> NodeResult:
        """
        Build output paths and optionally persist manifest files.

        Args:
            config: 현재 프로젝트 설정 객체다.
            shot_plan: shot planning node가 만든 payload다.
            extension_plan: extension source node가 만든 payload다.
            write_files: manifest 파일을 실제로 쓸지 결정한다.

        Returns:
            출력 경로와 manifest 위치를 담은 결과 객체다.
        """
        payload = self._build_output_paths(config)

        if write_files:
            self._write_manifests(
                output_payload=payload,
                runtime_validation=runtime_validation,
                model_bundles=model_bundles,
                shot_plan=shot_plan,
                extension_plan=extension_plan,
                music_plan=music_plan,
                execution_plan=execution_plan,
            )

        return NodeResult(name=self.name, payload=payload)

    def _build_output_paths(self, config: AOGProjectConfig) -> dict[str, Any]:
        """Calculate the output directories and manifest paths for a project."""
        output_root = Path(config.output.dir)
        manifests_dir = output_root / "manifests"
        shots_dir = output_root / "shots"
        logs_dir = output_root / "logs"
        audio_dir = output_root / "audio"
        video_dir = output_root / "video"
        return {
            "output_root": str(output_root),
            "dirs": {
                "manifests": str(manifests_dir),
                "shots": str(shots_dir),
                "logs": str(logs_dir),
                "audio": str(audio_dir),
                "video": str(video_dir),
            },
            "final_output": str(output_root / f"{config.project_name}.{config.output_format}"),
            "shot_manifest": str(manifests_dir / "shot_plan.json"),
            "extension_manifest": str(manifests_dir / "extension_plan.json"),
            "run_summary": str(logs_dir / "run_summary.json"),
        }

    def _write_manifests(
        self,
        *,
        output_payload: dict[str, Any],
        runtime_validation: dict[str, Any] | None,
        model_bundles: dict[str, Any] | None,
        shot_plan: dict[str, Any],
        extension_plan: dict[str, Any],
        music_plan: dict[str, Any] | None,
        execution_plan: dict[str, Any] | None,
    ) -> None:
        """Create output directories and write manifest files to disk."""
        manifests_dir = Path(output_payload["dirs"]["manifests"])
        shots_dir = Path(output_payload["dirs"]["shots"])
        logs_dir = Path(output_payload["dirs"]["logs"])
        audio_dir = Path(output_payload["dirs"]["audio"])
        video_dir = Path(output_payload["dirs"]["video"])
        manifests_dir.mkdir(parents=True, exist_ok=True)
        shots_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)
        video_dir.mkdir(parents=True, exist_ok=True)
        (manifests_dir / "shot_plan.json").write_text(
            json.dumps(shot_plan, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        (manifests_dir / "extension_plan.json").write_text(
            json.dumps(extension_plan, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        if runtime_validation is not None:
            (manifests_dir / "runtime_validation.json").write_text(
                json.dumps(runtime_validation, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
        if model_bundles is not None:
            (manifests_dir / "model_bundles.json").write_text(
                json.dumps(model_bundles, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
        if music_plan is not None:
            (manifests_dir / "music_plan.json").write_text(
                json.dumps(music_plan, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
        if execution_plan is not None:
            (manifests_dir / "execution_plan.json").write_text(
                json.dumps(execution_plan, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
