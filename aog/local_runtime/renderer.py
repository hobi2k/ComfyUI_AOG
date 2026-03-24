"""High-level local Python render loop for the CLI-first pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ace_runtime import AceRuntime
from .bootstrap import bootstrap_comfy_runtime
from .image_audio import save_audio_waveform, save_image_frames
from .media import concatenate_videos, copy_last_frame, encode_frames_to_video, mux_video_and_audio
from .paths import ComfyPaths
from .wan_runtime import WanRuntime


def render_project_local(
    *,
    config: Any,
    runtime_validation: dict[str, Any],
    model_bundles: dict[str, Any],
    execution_plan: dict[str, Any],
    output_plan: dict[str, Any],
) -> dict[str, Any]:
    """
    Render the project in-process through the CLI-first local runtime.

    Args:
        config: 현재 프로젝트 설정 객체다.
        runtime_validation: runtime validation node payload다.
        model_bundles: model bundle node payload다.
        execution_plan: execution planning node payload다.
        output_plan: output planning node payload다.
    """
    comfy_paths = ComfyPaths.from_model_path(model_bundles["video"]["i2v"]["high"])
    modules = bootstrap_comfy_runtime(comfy_paths.root_dir)
    wan_runtime = WanRuntime(
        modules=modules,
        comfy_paths=comfy_paths,
        model_bundles=model_bundles,
        runtime_validation=runtime_validation,
    )
    ace_runtime = AceRuntime(
        modules=modules,
        comfy_paths=comfy_paths,
        model_bundles=model_bundles,
    )

    shot_artifacts = _render_shots_local(
        config=config,
        execution_plan=execution_plan,
        wan_runtime=wan_runtime,
    )
    audio_artifact = _render_audio_local(
        execution_plan=execution_plan,
        ace_runtime=ace_runtime,
    )

    intermediate_video = Path(output_plan["dirs"]["video"]) / "assembled_shots.mp4"
    concatenate_videos(video_paths=[item["video_path"] for item in shot_artifacts], output_path=intermediate_video)
    final_output = mux_video_and_audio(
        video_path=intermediate_video,
        audio_path=audio_artifact,
        output_path=output_plan["final_output"],
        video_codec=config.output.export.video_codec,
        audio_codec=config.output.export.audio_codec,
        pixel_format=config.output.export.pixel_format,
        upscale_scale=config.postprocess.upscale.scale if config.postprocess.upscale.enabled else None,
        target_fps=config.postprocess.frame_interpolation.target_fps if config.postprocess.frame_interpolation.enabled else None,
    )

    summary = {
        "status": "completed",
        "stages": [
            {"name": "render_shots", "status": "completed", "details": f"Rendered {len(shot_artifacts)} Wan shots locally."},
            {"name": "generate_music", "status": "completed", "details": f"Generated Ace Step audio locally: {audio_artifact}"},
            {"name": "postprocess", "status": "completed", "details": "Concatenated shots and muxed the final output."},
        ],
        "artifacts": {
            "shot_videos": [item["video_path"] for item in shot_artifacts],
            "last_frames": [item["last_frame_path"] for item in shot_artifacts],
            "audio_path": str(audio_artifact),
            "intermediate_video": str(intermediate_video),
            "final_output": str(final_output),
        },
    }
    Path(output_plan["run_summary"]).write_text(
        json.dumps(summary, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return summary


def _render_shots_local(
    *,
    config: Any,
    execution_plan: dict[str, Any],
    wan_runtime: WanRuntime,
) -> list[dict[str, str]]:
    """Render all planned shots locally with last-frame chaining."""
    previous_last_frame: Path | None = None
    rendered: list[dict[str, str]] = []
    base_seed = 1000
    for shot_job in execution_plan["shot_jobs"]:
        source_image = _resolve_source_image(config=config, shot_job=shot_job, previous_last_frame=previous_last_frame)
        images = wan_runtime.render_shot(
            shot_job=shot_job,
            source_image_path=source_image,
            seed=base_seed + int(shot_job["shot_index"]),
        )
        frame_paths = save_image_frames(images, shot_job["artifacts"]["frames_dir"])
        video_path = encode_frames_to_video(
            frame_dir=shot_job["artifacts"]["frames_dir"],
            fps=int(shot_job["fps"]),
            output_path=shot_job["artifacts"]["video_path"],
        )
        last_frame_path = copy_last_frame(frame_paths, shot_job["artifacts"]["last_frame_path"])
        Path(shot_job["artifacts"]["result_path"]).write_text(
            json.dumps(
                {
                    "source_image": source_image,
                    "frame_count": len(frame_paths),
                    "video_path": str(video_path),
                    "last_frame_path": str(last_frame_path),
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        previous_last_frame = last_frame_path
        rendered.append(
            {
                "video_path": str(video_path),
                "last_frame_path": str(last_frame_path),
            }
        )
    return rendered


def _render_audio_local(
    *,
    execution_plan: dict[str, Any],
    ace_runtime: AceRuntime,
) -> Path:
    """Render the project music locally through Ace Step."""
    audio_job = execution_plan["audio_job"]
    reference_dir = Path(audio_job["voice_clone_reference_dir"])
    reference_path: str | None = None
    if reference_dir.exists():
        for candidate in sorted(reference_dir.iterdir()):
            if candidate.suffix.lower() in {".wav", ".flac", ".mp3", ".ogg", ".m4a"}:
                reference_path = str(candidate)
                break
    audio_payload = ace_runtime.render_audio(
        audio_job=audio_job,
        seed=424242,
        voice_reference_path=reference_path,
    )
    mix_path = save_audio_waveform(
        waveform=audio_payload["waveform"],
        sample_rate=int(audio_payload["sample_rate"]),
        path=audio_job["artifacts"]["mix_path"],
    )
    Path(audio_job["artifacts"]["result_path"]).write_text(
        json.dumps(
            {
                "mix_path": str(mix_path),
                "voice_reference_path": reference_path,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    return mix_path


def _resolve_source_image(*, config: Any, shot_job: dict[str, Any], previous_last_frame: Path | None) -> str:
    """Resolve the source image for a shot based on chaining rules."""
    if int(shot_job["shot_index"]) == 0:
        return str(shot_job["input_image"])
    extension = shot_job.get("extension", {})
    if extension.get("enabled") and extension.get("source_mode") == "custom_image":
        return str(extension["source_image"])
    if config.video.chain_strategy == "last_frame" and previous_last_frame is not None:
        return str(previous_last_frame)
    if previous_last_frame is not None:
        return str(previous_last_frame)
    return str(shot_job["input_image"])
