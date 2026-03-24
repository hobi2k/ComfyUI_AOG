"""Build a simple shot plan from project planning settings."""

from __future__ import annotations

from aog.config.schema import AOGProjectConfig

from .base import BaseNode, NodeResult


class ShotPlanNode(BaseNode):
    """Create a first-pass shot list for validation and manifest generation."""

    name = "shot_plan"

    def run(self, *, config: AOGProjectConfig) -> NodeResult:
        """
        Build a simple evenly spaced shot plan for the current project.

        Args:
            config: 현재 프로젝트 설정 객체다.

        Returns:
            shot count와 shot별 입력 계획을 담은 결과 객체다.
        """
        shot_count = config.planning.target_shot_count
        base_duration = round(config.duration / shot_count, 3)
        shots = self._build_shot_entries(config, shot_count, base_duration)
        payload = {
            "mode": config.mode,
            "shot_template": config.planning.shot_template,
            "shot_count": shot_count,
            "shots": shots,
        }
        return NodeResult(name=self.name, payload=payload)

    def _build_shot_entries(
        self,
        config: AOGProjectConfig,
        shot_count: int,
        base_duration: float,
    ) -> list[dict[str, float | int | bool | str]]:
        """Build every shot entry used by the validation pipeline."""
        shots: list[dict[str, float | int | bool | str]] = []
        shot_start = 0.0
        source_images = config.inputs.source_images or [""]
        for shot_index in range(shot_count):
            shot_end = round(min(config.duration, shot_start + base_duration), 3)
            shots.append(
                self._build_shot_entry(
                    shot_index,
                    shot_start,
                    shot_end,
                    source_images[min(shot_index, len(source_images) - 1)],
                    config.video.extension.enabled and shot_index == shot_count - 1,
                )
            )
            shot_start = shot_end
        return shots

    def _build_shot_entry(
        self,
        shot_index: int,
        shot_start: float,
        shot_end: float,
        input_image: str,
        extension_needed: bool,
    ) -> dict[str, float | int | bool | str]:
        """Build a single shot entry."""
        return {
            "index": shot_index,
            "start": round(shot_start, 3),
            "end": shot_end,
            "duration": round(shot_end - shot_start, 3),
            "input_image": input_image,
            "extension_needed": extension_needed,
            "output_stem": f"shot_{shot_index:03d}",
        }
