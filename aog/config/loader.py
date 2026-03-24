"""Load YAML project configs and convert them into typed runtime objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .schema import AOGProjectConfig, ValidationMode, parse_project_config


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """
    Read a YAML file and return the top-level mapping.

    Args:
        path: 읽을 YAML 파일 경로다.

    Returns:
        프로젝트 설정의 최상위 매핑이다.
    """
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Top-level YAML document must be a mapping: {config_path}")
    return data


def load_project_config(path: str | Path, mode: ValidationMode = ValidationMode.EXAMPLE) -> AOGProjectConfig:
    """
    Load a YAML file and parse it as an AOG project config.

    Args:
        path: 프로젝트 YAML 경로다.
        mode: 예제 검증인지 런타임 검증인지 결정한다.

    Returns:
        스키마 검증을 통과한 프로젝트 설정 객체다.
    """
    return parse_project_config(load_yaml_file(path), mode=mode)
