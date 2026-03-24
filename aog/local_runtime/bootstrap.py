"""Bootstrap ComfyUI internals as importable modules for local execution."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


@dataclass(slots=True)
class ComfyRuntimeModules:
    """Container for imported ComfyUI and Wan/Ace runtime modules."""

    comfy_root: Path
    nodes: ModuleType
    nodes_ace: ModuleType
    nodes_audio: ModuleType
    wan_nodes: ModuleType
    wan_model_loading: ModuleType


def bootstrap_comfy_runtime(comfy_root: str | Path) -> ComfyRuntimeModules:
    """
    Import the ComfyUI modules needed by the local executor.

    Args:
        comfy_root: ComfyUI 설치 루트다.

    Returns:
        로컬 추론에 필요한 모듈 묶음이다.
    """
    root = Path(comfy_root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    nodes = importlib.import_module("nodes")
    nodes_ace = importlib.import_module("comfy_extras.nodes_ace")
    nodes_audio = importlib.import_module("comfy_extras.nodes_audio")

    wan_package_dir = root / "custom_nodes" / "ComfyUI-WanVideoWrapper"
    _load_package(
        package_name="aog_wan_wrapper",
        init_path=wan_package_dir / "__init__.py",
        package_dir=wan_package_dir,
    )
    wan_nodes = importlib.import_module("aog_wan_wrapper.nodes")
    wan_model_loading = importlib.import_module("aog_wan_wrapper.nodes_model_loading")

    return ComfyRuntimeModules(
        comfy_root=root,
        nodes=nodes,
        nodes_ace=nodes_ace,
        nodes_audio=nodes_audio,
        wan_nodes=wan_nodes,
        wan_model_loading=wan_model_loading,
    )


def _load_package(package_name: str, init_path: Path, package_dir: Path) -> ModuleType:
    """Load a package from an arbitrary filesystem path under a stable alias."""
    if package_name in sys.modules:
        return sys.modules[package_name]
    spec = importlib.util.spec_from_file_location(
        package_name,
        init_path,
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create module spec for {package_name} from {init_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return module
