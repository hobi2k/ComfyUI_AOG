"""Command-line entrypoints for config validation, planning, and CLI execution."""

from __future__ import annotations

import argparse
import json
import sys

from aog.config.loader import load_project_config
from aog.config.schema import ValidationMode
from aog.local_runtime import ComfyPathError, MediaError
from aog.pipeline import run_cli_pipeline, run_plan_pipeline, run_validation_pipeline


def build_parser() -> argparse.ArgumentParser:
    """
    Build the top-level CLI parser for AOG commands.

    Returns:
        `aog` 명령에서 재사용할 argparse parser 객체다.
    """
    parser = argparse.ArgumentParser(prog="aog", description="CLI-first pipeline runner for ComfyUI_AOG")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("validate", "plan", "run"):
        sub = subparsers.add_parser(name)
        sub.add_argument("config", help="Path to project YAML")
        sub.add_argument(
            "--validation-mode",
            choices=[mode.value for mode in ValidationMode],
            default=ValidationMode.EXAMPLE.value,
            help="Use `example` for placeholder configs or `runtime` for strict file checks",
        )
        sub.add_argument(
            "--no-write",
            action="store_true",
            help="Do not create manifests or output directories",
        )

    return parser


def main(argv: list[str] | None = None) -> int:
    """
    Parse CLI arguments, run the pipeline, and print JSON output.

    Args:
        argv: 테스트용으로 주입할 선택적 인자 목록이다.

    Returns:
        프로세스 종료 코드다.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    validation_mode = ValidationMode(args.validation_mode)
    try:
        config = load_project_config(args.config, mode=validation_mode)
        if args.command == "validate":
            result = run_validation_pipeline(config, validation_mode=validation_mode, write_files=not args.no_write)
        elif args.command == "plan":
            result = run_plan_pipeline(config, validation_mode=validation_mode, write_files=not args.no_write)
        else:
            result = run_cli_pipeline(config, validation_mode=validation_mode, write_files=not args.no_write)
    except (ComfyPathError, MediaError, RuntimeError, ValueError, FileNotFoundError, ImportError) as exc:
        json.dump({"command": args.command, "status": "error", "error": str(exc)}, sys.stderr, ensure_ascii=True, indent=2)
        sys.stderr.write("\n")
        return 1

    json.dump(result, sys.stdout, ensure_ascii=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
