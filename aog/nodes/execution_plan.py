"""Assemble CLI execution stages and job manifests from validated inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aog.config.schema import AOGProjectConfig

from .base import BaseNode, NodeResult


class ExecutionPlanNode(BaseNode):
    """Translate validated config and manifests into runnable CLI jobs."""

    name = "execution_plan"

    def run(
        self,
        *,
        config: AOGProjectConfig,
        runtime_validation: dict[str, Any],
        model_bundles: dict[str, Any],
        shot_plan: dict[str, Any],
        extension_plan: dict[str, Any],
        music_plan: dict[str, Any],
        output_plan: dict[str, Any],
    ) -> NodeResult:
        """
        Build a CLI-first execution plan with per-stage and per-shot jobs.

        Args:
            config: 현재 프로젝트 설정 객체다.
            runtime_validation: runtime validation node payload다.
            model_bundles: model bundle node payload다.
            shot_plan: shot planning node payload다.
            extension_plan: extension planning node payload다.
            music_plan: music planning node payload다.
            output_plan: output planning node payload다.

        Returns:
            CLI 오케스트레이터가 바로 저장하고 실행할 수 있는 계획 객체다.
        """
        shots_dir = Path(output_plan["dirs"]["shots"])
        payload = {
            "executor": "cli",
            "project_name": config.project_name,
            "mode": config.mode,
            "selected_attention_backend": runtime_validation.get("selected_attention_backend"),
            "final_output": output_plan["final_output"],
            "shot_jobs": self._build_shot_jobs(
                config=config,
                shot_plan=shot_plan,
                extension_plan=extension_plan,
                model_bundles=model_bundles,
                shots_dir=shots_dir,
            ),
            "audio_job": self._build_audio_job(config, music_plan, output_plan),
            "postprocess_job": self._build_postprocess_job(config, output_plan),
            "stages": self._build_stages(config, output_plan),
        }
        return NodeResult(name=self.name, payload=payload)

    def _build_shot_jobs(
        self,
        *,
        config: AOGProjectConfig,
        shot_plan: dict[str, Any],
        extension_plan: dict[str, Any],
        model_bundles: dict[str, Any],
        shots_dir: Path,
    ) -> list[dict[str, Any]]:
        """Build per-shot render jobs for the CLI executor."""
        extension_by_index = {
            int(item["shot_index"]): item
            for item in extension_plan.get("extension_plan", [])
        }
        shot_jobs: list[dict[str, Any]] = []
        for shot in shot_plan.get("shots", []):
            shot_index = int(shot["index"])
            output_stem = str(shot["output_stem"])
            extension_entry = extension_by_index.get(shot_index, {})
            shot_dir = shots_dir / output_stem
            shot_jobs.append(
                {
                    "shot_index": shot_index,
                    "output_stem": output_stem,
                    "input_image": shot["input_image"],
                    "start": shot["start"],
                    "end": shot["end"],
                    "duration": shot["duration"],
                    "text_prompt": config.inputs.text_prompt,
                    "negative_prompt": config.video.generation.negative_prompt,
                    "fps": config.video.generation.fps,
                    "steps": config.video.generation.steps,
                    "guidance_scale": config.video.generation.guidance_scale,
                    "resolution": {
                        "width": config.video.generation.base_resolution.width,
                        "height": config.video.generation.base_resolution.height,
                    },
                    "model_profile": model_bundles["video"]["i2v"]["profile"],
                    "extension": {
                        "enabled": bool(extension_entry.get("enabled", False)),
                        "source_mode": extension_entry.get("source_mode"),
                        "source_image": extension_entry.get("source_image"),
                    },
                    "artifacts": {
                        "shot_dir": str(shot_dir),
                        "frames_dir": str(shot_dir / "frames"),
                        "plan_path": str(shot_dir / "job.json"),
                        "result_path": str(shot_dir / "result.json"),
                        "video_path": str(shot_dir / f"{output_stem}.mp4"),
                        "last_frame_path": str(shot_dir / f"{output_stem}_lastframe.png"),
                    },
                }
            )
        return shot_jobs

    def _build_audio_job(
        self,
        config: AOGProjectConfig,
        music_plan: dict[str, Any],
        output_plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the audio generation job that follows video planning."""
        output_root = Path(output_plan["output_root"])
        return {
            "engine": config.audio.engine,
            "prompt": music_plan["prompt"],
            "duration": music_plan["duration"],
            "bpm_target": music_plan["bpm_target"],
            "lyrics_path": music_plan["lyrics_path"],
            "voice_clone_reference_dir": music_plan["voice_clone_reference_dir"],
            "structure": music_plan["structure"],
            "hit_points": music_plan["hit_points"],
            "artifacts": {
                "plan_path": str(output_root / "manifests" / "audio_job.json"),
                "result_path": str(output_root / "manifests" / "audio_result.json"),
                "music_plan_path": str(output_root / "manifests" / "music_plan.json"),
                "mix_path": str(output_root / "audio" / "theme_mix.wav"),
                "instrumental_path": str(output_root / "audio" / "theme_instrumental.wav"),
                "vocal_path": str(output_root / "audio" / "theme_vocal.wav"),
            },
        }

    def _build_postprocess_job(
        self,
        config: AOGProjectConfig,
        output_plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the final post-process and export job."""
        return {
            "upscale_enabled": config.postprocess.upscale.enabled,
            "frame_interpolation_enabled": config.postprocess.frame_interpolation.enabled,
            "target_fps": config.postprocess.frame_interpolation.target_fps,
            "video_codec": config.output.export.video_codec,
            "audio_codec": config.output.export.audio_codec,
            "pixel_format": config.output.export.pixel_format,
            "final_output": output_plan["final_output"],
        }

    def _build_stages(self, config: AOGProjectConfig, output_plan: dict[str, Any]) -> list[dict[str, Any]]:
        """Describe the high-level stages the CLI executor will walk through."""
        return [
            {
                "name": "prepare_project",
                "status": "pending",
                "description": "Create output directories and persist manifests.",
            },
            {
                "name": "render_shots",
                "status": "pending",
                "description": "Run Wan 2.2 I2V jobs per shot and collect last frames.",
            },
            {
                "name": "extend_video",
                "status": "pending" if config.video.extension.enabled else "skipped",
                "description": "Run extension jobs for shots that need continuation.",
            },
            {
                "name": "generate_music",
                "status": "pending",
                "description": "Generate Ace Step music and optional cloned vocals from the music plan.",
            },
            {
                "name": "postprocess",
                "status": "pending",
                "description": "Upscale, interpolate, and assemble the final export.",
            },
            {
                "name": "export",
                "status": "pending",
                "description": f"Write the final project file to {output_plan['final_output']}.",
            },
        ]
