"""Run CLI pipeline stages and persist planning artifacts for local execution."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aog.config.schema import AOGProjectConfig, ValidationMode
from aog.local_runtime import render_project_local
from aog.nodes import (
    AssetValidationNode,
    ExecutionPlanNode,
    ExtensionSourceNode,
    ModelBundleNode,
    MusicPlanNode,
    OutputPlanNode,
    RuntimeValidationNode,
    ShotPlanNode,
)


def execute_validation_nodes(
    config: AOGProjectConfig,
    validation_mode: ValidationMode,
) -> dict[str, Any]:
    """
    Execute nodes needed to validate config and derive planning payloads.

    Args:
        config: 현재 프로젝트 설정 객체다.
        validation_mode: 예제 검증인지 런타임 검증인지 나타낸다.

    Returns:
        output plan 전까지의 노드 결과 매핑이다.
    """
    asset_result = AssetValidationNode().run(config=config, validation_mode=validation_mode)
    runtime_result = RuntimeValidationNode().run(config=config)
    model_result = ModelBundleNode().run(config=config)
    shot_result = ShotPlanNode().run(config=config)
    extension_result = ExtensionSourceNode().run(config=config, shot_plan=shot_result.payload)
    music_result = MusicPlanNode().run(config=config, shot_plan=shot_result.payload)
    return {
        "asset_validation": asdict(asset_result),
        "runtime_validation": asdict(runtime_result),
        "model_bundles": asdict(model_result),
        "shot_plan": asdict(shot_result),
        "extension_source": asdict(extension_result),
        "music_plan": asdict(music_result),
    }


def execute_plan_nodes(
    config: AOGProjectConfig,
    validation_mode: ValidationMode,
    write_files: bool,
) -> dict[str, Any]:
    """
    Execute validation plus planning nodes and optionally persist manifests.

    Args:
        config: 현재 프로젝트 설정 객체다.
        validation_mode: 예제 검증인지 런타임 검증인지 나타낸다.
        write_files: manifest 파일을 실제로 쓸지 결정한다.

    Returns:
        계획과 output manifest를 포함한 노드 결과 매핑이다.
    """
    node_results = execute_validation_nodes(config, validation_mode)
    execution_result = ExecutionPlanNode().run(
        config=config,
        runtime_validation=node_results["runtime_validation"]["payload"],
        model_bundles=node_results["model_bundles"]["payload"],
        shot_plan=node_results["shot_plan"]["payload"],
        extension_plan=node_results["extension_source"]["payload"],
        music_plan=node_results["music_plan"]["payload"],
        output_plan=_build_output_paths(config),
    )
    output_result = OutputPlanNode().run(
        config=config,
        runtime_validation=node_results["runtime_validation"]["payload"],
        model_bundles=node_results["model_bundles"]["payload"],
        shot_plan=node_results["shot_plan"]["payload"],
        extension_plan=node_results["extension_source"]["payload"],
        music_plan=node_results["music_plan"]["payload"],
        execution_plan=execution_result.payload,
        write_files=write_files,
    )
    node_results["execution_plan"] = asdict(execution_result)
    node_results["output_plan"] = asdict(output_result)
    return node_results


def run_validation_pipeline(
    config: AOGProjectConfig,
    validation_mode: ValidationMode,
    write_files: bool = False,
) -> dict[str, Any]:
    """
    Run config validation and return a lightweight CLI summary.

    Args:
        config: 현재 프로젝트 설정 객체다.
        validation_mode: 예제 검증인지 런타임 검증인지 나타낸다.
        write_files: output manifest까지 쓰고 싶을 때만 사용한다.

    Returns:
        검증 노드 결과만 담은 응답 객체다.
    """
    node_results = execute_validation_nodes(config, validation_mode)
    output_result = OutputPlanNode().run(
        config=config,
        runtime_validation=node_results["runtime_validation"]["payload"],
        model_bundles=node_results["model_bundles"]["payload"],
        shot_plan=node_results["shot_plan"]["payload"],
        extension_plan=node_results["extension_source"]["payload"],
        music_plan=node_results["music_plan"]["payload"],
        execution_plan=None,
        write_files=write_files,
    )
    node_results["output_plan"] = asdict(output_result)
    return build_pipeline_summary(config, node_results, command="validate")


def run_plan_pipeline(
    config: AOGProjectConfig,
    validation_mode: ValidationMode,
    write_files: bool = True,
) -> dict[str, Any]:
    """
    Build and optionally persist the CLI execution plan.

    Args:
        config: 현재 프로젝트 설정 객체다.
        validation_mode: 예제 검증인지 런타임 검증인지 나타낸다.
        write_files: manifest 파일을 실제로 쓸지 결정한다.

    Returns:
        실행용 planning payload를 담은 응답 객체다.
    """
    node_results = execute_plan_nodes(config, validation_mode, write_files)
    return build_pipeline_summary(config, node_results, command="plan")


def run_cli_pipeline(
    config: AOGProjectConfig,
    validation_mode: ValidationMode,
    write_files: bool = True,
) -> dict[str, Any]:
    """
    Run the CLI-first orchestration and emit executor-ready job files.

    Args:
        config: 현재 프로젝트 설정 객체다.
        validation_mode: 예제 검증인지 런타임 검증인지 나타낸다.
        write_files: 작업 파일을 실제로 쓸지 결정한다.

    Returns:
        실행 계획과 stage 상태를 담은 응답 객체다.
    """
    node_results = execute_plan_nodes(config, validation_mode, write_files)
    run_result = build_run_result(
        config=config,
        runtime_validation=node_results["runtime_validation"]["payload"],
        model_bundles=node_results["model_bundles"]["payload"],
        execution_plan=node_results["execution_plan"]["payload"],
        output_plan=node_results["output_plan"]["payload"],
        write_files=write_files,
    )
    node_results["run_result"] = run_result
    return build_pipeline_summary(config, node_results, command="run")


def build_pipeline_summary(
    config: AOGProjectConfig,
    node_results: dict[str, Any],
    *,
    command: str,
) -> dict[str, Any]:
    """
    Build the top-level CLI response from node execution results.

    Args:
        config: 현재 프로젝트 설정 객체다.
        node_results: 각 노드 실행 결과 매핑이다.
        command: 현재 실행한 CLI 명령이다.

    Returns:
        CLI가 출력할 최종 요약 객체다.
    """
    return {
        "command": command,
        "project": {
            "name": config.project_name,
            "mode": config.mode,
            "duration": config.duration,
            "aspect_ratio": config.aspect_ratio,
            "output_format": config.output_format,
            "output_dir": config.output.dir,
        },
        "nodes": node_results,
    }


def build_run_result(
    *,
    config: AOGProjectConfig,
    runtime_validation: dict[str, Any],
    model_bundles: dict[str, Any],
    execution_plan: dict[str, Any],
    output_plan: dict[str, Any],
    write_files: bool,
) -> dict[str, Any]:
    """
    Create local-runtime job files and a run summary for the CLI pipeline.

    Args:
        config: 현재 프로젝트 설정 객체다.
        execution_plan: execution planning node가 만든 payload다.
        output_plan: output planning node가 만든 payload다.
        write_files: 작업 파일을 실제로 쓸지 결정한다.

    Returns:
        stage 상태와 생성된 job 파일 경로를 담은 실행 결과다.
    """
    planned_stage_results = [
        {
            "name": "prepare_project",
            "status": "completed",
            "details": "Output directories and manifests are ready.",
        },
        {
            "name": "render_shots",
            "status": "planned",
            "details": "Shot job manifests were generated for the local renderer.",
        },
        {
            "name": "extend_video",
            "status": "planned" if config.video.extension.enabled else "skipped",
            "details": "Extension inputs were resolved for extension-capable shots.",
        },
        {
            "name": "generate_music",
            "status": "planned",
            "details": "Ace Step music job manifest was generated from the music plan.",
        },
        {
            "name": "postprocess",
            "status": "planned",
            "details": "Post-process export instructions were generated.",
        },
    ]

    job_paths: list[str] = []
    if write_files:
        job_paths = _write_job_files(output_plan, execution_plan, planned_stage_results)
        render_summary = render_project_local(
            config=config,
            runtime_validation=runtime_validation,
            model_bundles=model_bundles,
            execution_plan=execution_plan,
            output_plan=output_plan,
        )
        return {
            "executor": "cli",
            "status": render_summary["status"],
            "job_files_written": True,
            "job_paths": job_paths,
            "stage_results": render_summary["stages"],
            "artifacts": render_summary["artifacts"],
            "final_output": render_summary["artifacts"]["final_output"],
        }

    return {
        "executor": "cli",
        "status": "planned",
        "job_files_written": write_files,
        "job_paths": job_paths,
        "stage_results": planned_stage_results,
        "final_output": output_plan["final_output"],
    }


def _write_job_files(
    output_plan: dict[str, Any],
    execution_plan: dict[str, Any],
    stage_results: list[dict[str, Any]],
) -> list[str]:
    """Persist shot, audio, and run summary job files for downstream executors."""
    manifests_dir = Path(output_plan["dirs"]["manifests"])
    logs_dir = Path(output_plan["dirs"]["logs"])
    shots_dir = Path(output_plan["dirs"]["shots"])
    manifests_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    shots_dir.mkdir(parents=True, exist_ok=True)

    job_paths: list[str] = []
    for shot_job in execution_plan["shot_jobs"]:
        shot_dir = Path(shot_job["artifacts"]["shot_dir"])
        shot_dir.mkdir(parents=True, exist_ok=True)
        (shot_dir / "frames").mkdir(parents=True, exist_ok=True)
        plan_path = Path(shot_job["artifacts"]["plan_path"])
        plan_path.write_text(json.dumps(shot_job, ensure_ascii=True, indent=2), encoding="utf-8")
        job_paths.append(str(plan_path))

    audio_plan_path = Path(execution_plan["audio_job"]["artifacts"]["plan_path"])
    audio_plan_path.parent.mkdir(parents=True, exist_ok=True)
    audio_plan_path.write_text(json.dumps(execution_plan["audio_job"], ensure_ascii=True, indent=2), encoding="utf-8")
    job_paths.append(str(audio_plan_path))

    run_summary_path = logs_dir / "run_summary.json"
    run_summary_path.write_text(
        json.dumps(
            {
                "stage_results": stage_results,
                "final_output": output_plan["final_output"],
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    job_paths.append(str(run_summary_path))
    return job_paths


def _build_output_paths(config: AOGProjectConfig) -> dict[str, Any]:
    """Mirror the output path calculation used by the output node."""
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
        "run_summary": str(logs_dir / "run_summary.json"),
    }
