"""Build an audio generation plan from project and shot metadata."""

from __future__ import annotations

from typing import Any

from aog.config.schema import AOGProjectConfig

from .base import BaseNode, NodeResult


class MusicPlanNode(BaseNode):
    """Create a structured music plan that the CLI pipeline can persist."""

    name = "music_plan"

    def run(self, *, config: AOGProjectConfig, shot_plan: dict[str, Any]) -> NodeResult:
        """
        Derive music timing and conditioning data from the current project.

        Args:
            config: 현재 프로젝트 설정 객체다.
            shot_plan: shot planning node가 만든 payload다.

        Returns:
            Ace Step 입력에 가까운 음악 계획 payload다.
        """
        shots = shot_plan.get("shots", [])
        payload = {
            "engine": config.audio.engine,
            "generation_mode": config.audio.generation_mode,
            "output_mode": config.audio.output_mode,
            "prompt": config.audio.prompt,
            "duration": config.duration,
            "bpm_target": config.audio.bpm_target,
            "instrumental_enabled": config.audio.instrumental.enabled,
            "vocal_enabled": config.audio.vocal.enabled,
            "voice_clone_enabled": config.audio.voice_clone.enabled,
            "voice_clone_id": config.audio.voice_clone.clone_id,
            "voice_clone_reference_dir": config.audio.voice_clone.reference_audio_dir,
            "lyrics_mode": config.audio.vocal.lyrics_mode,
            "lyrics_path": config.audio.vocal.lyrics_path,
            "style_prompt": config.audio.vocal.style_prompt,
            "structure": self._build_structure(config, shots),
            "hit_points": self._build_hit_points(shots),
            "title_hit_point": config.inputs.title.timing_seconds,
        }
        return NodeResult(name=self.name, payload=payload)

    def _build_structure(
        self,
        config: AOGProjectConfig,
        shots: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build a song structure from config data or fall back to shot timing."""
        if config.audio.structure:
            return [
                {
                    "label": item.label,
                    "start": item.start,
                    "end": item.end,
                }
                for item in config.audio.structure
            ]

        structure: list[dict[str, Any]] = []
        energy_curve = config.planning.energy_curve
        for shot in shots:
            shot_index = int(shot["index"])
            energy_label = energy_curve[min(shot_index, len(energy_curve) - 1)] if energy_curve else "mid"
            structure.append(
                {
                    "label": f"shot_{shot_index:03d}_{energy_label}",
                    "start": shot["start"],
                    "end": shot["end"],
                }
            )
        return structure

    def _build_hit_points(self, shots: list[dict[str, Any]]) -> list[float]:
        """Collect cut points that should influence music accents."""
        hit_points: list[float] = []
        for shot in shots:
            start_time = float(shot["start"])
            if start_time > 0:
                hit_points.append(start_time)
        return hit_points
