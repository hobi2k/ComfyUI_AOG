"""Inspect the active Python runtime and resolve acceleration choices."""

from __future__ import annotations

import importlib.util
import shutil
from typing import Any

from aog.config.schema import AOGProjectConfig
from aog.local_runtime.paths import ComfyPathError, ComfyPaths

from .base import BaseNode, NodeResult


class RuntimeValidationNode(BaseNode):
    """Check whether the current environment can satisfy runtime settings."""

    name = "runtime_validation"

    def run(self, *, config: AOGProjectConfig) -> NodeResult:
        """
        Inspect torch, CUDA, SageAttention, and local-runtime prerequisites.

        Args:
            config: 현재 프로젝트 설정 객체다.

        Returns:
            런타임 상태와 attention backend 선택 결과를 담은 결과 객체다.
        """
        payload = self._build_runtime_payload(config)
        warnings: list[str] = []

        selected_attention_backend = self._resolve_attention_backend(config, payload, warnings)
        payload["selected_attention_backend"] = selected_attention_backend

        self._collect_comfy_runtime_info(config, payload, warnings)

        if not payload["torch_installed"]:
            warnings.append("torch is not importable in current environment")
            return NodeResult(name=self.name, payload=payload, warnings=warnings)

        self._collect_torch_runtime_info(payload, warnings)
        self._collect_runtime_warnings(config, payload, warnings)
        return NodeResult(name=self.name, payload=payload, warnings=warnings)

    def _build_runtime_payload(self, config: AOGProjectConfig) -> dict[str, Any]:
        """Build the base runtime payload before torch-specific inspection."""
        torch_spec = importlib.util.find_spec("torch")
        sageattention_spec = importlib.util.find_spec("sageattention")
        return {
            "attention_backend": config.video.acceleration.attention_backend,
            "sageattention_enabled": config.video.acceleration.sageattention_enabled,
            "sageattention_required": config.video.acceleration.sageattention_required,
            "fallback_attention": config.video.acceleration.fallback_attention,
            "require_cuda": config.video.acceleration.require_cuda,
            "torch_installed": torch_spec is not None,
            "sageattention_installed": sageattention_spec is not None,
            "sageattention_fallback_applied": False,
            "ffmpeg_available": shutil.which("ffmpeg") is not None,
        }

    def _resolve_attention_backend(
        self,
        config: AOGProjectConfig,
        payload: dict[str, Any],
        warnings: list[str],
    ) -> str:
        """Resolve which attention backend should actually be used."""
        selected_attention_backend = config.video.acceleration.attention_backend
        if config.video.acceleration.sageattention_enabled and not payload["sageattention_installed"]:
            selected_attention_backend = config.video.acceleration.fallback_attention
            payload["sageattention_fallback_applied"] = True
            if config.video.acceleration.sageattention_required:
                warnings.append("sageattention is enabled in config but not importable in current environment")
        return selected_attention_backend

    def _collect_comfy_runtime_info(
        self,
        config: AOGProjectConfig,
        payload: dict[str, Any],
        warnings: list[str],
    ) -> None:
        """Collect filesystem prerequisites for the local runtime bootstrap."""
        try:
            comfy_paths = ComfyPaths.from_model_path(config.video.i2v_model.path_high)
        except ComfyPathError as exc:
            payload["comfy_root"] = None
            warnings.append(str(exc))
            return

        comfy_root = comfy_paths.root_dir
        payload["comfy_root"] = str(comfy_root)

        expected_paths = {
            "comfy_root_exists": comfy_root.exists(),
            "comfy_nodes_module_exists": (comfy_root / "nodes.py").exists(),
            "ace_nodes_module_exists": (comfy_root / "comfy_extras" / "nodes_ace.py").exists(),
            "audio_nodes_module_exists": (comfy_root / "comfy_extras" / "nodes_audio.py").exists(),
            "wan_wrapper_exists": (comfy_root / "custom_nodes" / "ComfyUI-WanVideoWrapper").exists(),
        }
        payload.update(expected_paths)

        missing = [name for name, exists in expected_paths.items() if not exists]
        if missing:
            warnings.append(
                "Local runtime bootstrap prerequisites are missing: "
                + ", ".join(missing)
            )

    def _collect_torch_runtime_info(self, payload: dict[str, Any], warnings: list[str]) -> None:
        """Import torch and collect CUDA runtime information."""
        try:
            import torch  # type: ignore
        except Exception as exc:  # pragma: no cover
            warnings.append(f"torch import failed: {exc}")
            return

        payload["torch_version"] = getattr(torch, "__version__", None)
        payload["cuda_version"] = getattr(getattr(torch, "version", None), "cuda", None)
        payload["cuda_available"] = bool(torch.cuda.is_available())

        if payload["cuda_available"]:
            try:
                payload["cuda_device"] = torch.cuda.get_device_name(0)
            except Exception:
                payload["cuda_device"] = None
        else:
            payload["cuda_device"] = None

    def _collect_runtime_warnings(
        self,
        config: AOGProjectConfig,
        payload: dict[str, Any],
        warnings: list[str],
    ) -> None:
        """Add warnings that depend on the collected runtime state."""
        if config.video.acceleration.require_cuda and not payload.get("cuda_available", False):
            warnings.append("CUDA is required by config but not available")
        if not payload.get("ffmpeg_available", False):
            warnings.append("ffmpeg is not available in PATH")
