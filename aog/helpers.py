import hashlib
import importlib.util
import json
import math
import sys
import types
from functools import lru_cache
from pathlib import Path
from typing import Any

import torch


ROOT_DIR = Path(__file__).resolve().parents[1]
COMFY_DIR = ROOT_DIR.parent.parent
CUSTOM_NODES_DIR = COMFY_DIR / "custom_nodes"


@lru_cache(maxsize=None)
def load_module_from_path(module_name: str, path: str) -> Any:
    module_path = Path(path)
    package_dir = module_path.parent
    package_init = package_dir / "__init__.py"

    if package_init.exists():
        package_name = f"{module_name}_pkg"
        if package_name not in sys.modules:
            package_spec = importlib.util.spec_from_file_location(
                package_name,
                package_init,
                submodule_search_locations=[str(package_dir)],
            )
            if package_spec is None or package_spec.loader is None:
                raise ImportError(f"Failed to load package module: {package_init}")
            package_module = importlib.util.module_from_spec(package_spec)
            sys.modules[package_name] = package_module
            package_spec.loader.exec_module(package_module)

        submodule_name = f"{package_name}.{module_path.stem}"
        if submodule_name in sys.modules:
            return sys.modules[submodule_name]
        spec = importlib.util.spec_from_file_location(submodule_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load module from path: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[submodule_name] = module
        spec.loader.exec_module(module)
        return module

    package_name = f"{module_name}_pkg"
    if package_name not in sys.modules:
        package_module = types.ModuleType(package_name)
        package_module.__path__ = [str(package_dir)]
        sys.modules[package_name] = package_module
    submodule_name = f"{package_name}.{module_path.stem}"
    if submodule_name in sys.modules:
        return sys.modules[submodule_name]
    spec = importlib.util.spec_from_file_location(submodule_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load module from path: {path}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = package_name
    sys.modules[submodule_name] = module
    spec.loader.exec_module(module)
    return module

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load module from path: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def ensure_audio_dict(audio: dict[str, Any]) -> dict[str, Any]:
    if "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError("AUDIO payload must contain waveform and sample_rate.")
    return {"waveform": audio["waveform"], "sample_rate": int(audio["sample_rate"])}


def summarize_video_frames(images: torch.Tensor, duration: float) -> dict[str, Any]:
    frames = images.detach().float().cpu()
    frame_count = int(frames.shape[0])
    brightness_curve = frames.mean(dim=(1, 2, 3))
    motion_values: list[float] = []
    if frame_count > 1:
        previous = frames[0]
        for index in range(1, frame_count):
            current = frames[index]
            motion_values.append(float((current - previous).abs().mean().item()))
            previous = current
        motion_tensor = torch.tensor(motion_values, dtype=torch.float32)
        motion_mean = float(motion_tensor.mean().item())
        motion_peak = float(motion_tensor.max().item())
        motion_std = float(motion_tensor.std().item()) if motion_tensor.numel() > 1 else 0.0
    else:
        motion_mean = 0.0
        motion_peak = 0.0
        motion_std = 0.0
    return {
        "frame_count": frame_count,
        "duration_sec": float(duration),
        "fps_estimate": float(frame_count / duration) if duration > 0 else 0.0,
        "mean_brightness": float(brightness_curve.mean().item()),
        "peak_brightness": float(brightness_curve.max().item()),
        "motion_mean": motion_mean,
        "motion_peak": motion_peak,
        "motion_std": motion_std,
    }


def build_timeline(images: torch.Tensor, duration: float, segment_count: int = 8) -> list[dict[str, Any]]:
    frames = images.detach().float().cpu()
    frame_count = int(frames.shape[0])
    if frame_count == 0:
        return []
    segment_count = max(1, min(segment_count, frame_count))
    boundaries = torch.linspace(0, frame_count, steps=segment_count + 1, dtype=torch.int64)
    timeline = []
    for index in range(segment_count):
        start = int(boundaries[index].item())
        end = int(boundaries[index + 1].item())
        if end <= start:
            continue
        chunk = frames[start:end]
        brightness = chunk.mean(dim=(1, 2, 3))
        if chunk.shape[0] > 1:
            motion_values: list[float] = []
            previous = chunk[0]
            for idx in range(1, int(chunk.shape[0])):
                current = chunk[idx]
                motion_values.append(float((current - previous).abs().mean().item()))
                previous = current
            motion_tensor = torch.tensor(motion_values, dtype=torch.float32)
            motion_value = float(motion_tensor.mean().item())
            motion_peak = float(motion_tensor.max().item())
        else:
            motion_value = 0.0
            motion_peak = 0.0
        start_sec = float((start / frame_count) * duration) if duration > 0 else 0.0
        end_sec = float((end / frame_count) * duration) if duration > 0 else 0.0
        timeline.append(
            {
                "segment_index": index,
                "start_frame": start,
                "end_frame": end,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "duration_sec": max(0.0, end_sec - start_sec),
                "mean_brightness": float(brightness.mean().item()),
                "peak_brightness": float(brightness.max().item()),
                "motion_mean": motion_value,
                "motion_peak": motion_peak,
            }
        )
    return timeline


def derive_semantic_cues(summary: dict[str, Any], timeline: list[dict[str, Any]]) -> list[str]:
    cues: list[str] = []
    duration = float(summary.get("duration_sec", 0.0))
    motion_mean = float(summary.get("motion_mean", 0.0))
    motion_peak = float(summary.get("motion_peak", 0.0))
    brightness = float(summary.get("mean_brightness", 0.0))

    if duration >= 20:
        cues.append("long-form opening pacing")
    elif duration >= 8:
        cues.append("standard opening pacing")
    else:
        cues.append("short promo pacing")

    if motion_peak > max(0.03, motion_mean * 1.7):
        cues.append("strong visual climax")
    if motion_mean < 0.01:
        cues.append("calm motion profile")
    elif motion_mean < 0.025:
        cues.append("moderate motion profile")
    else:
        cues.append("high-energy motion profile")

    if brightness < 0.3:
        cues.append("dark visual mood")
    elif brightness > 0.65:
        cues.append("bright visual mood")
    else:
        cues.append("balanced visual mood")

    if timeline:
        first = timeline[0]
        last = timeline[-1]
        max_motion_segment = max(timeline, key=lambda item: item["motion_mean"])
        min_motion_segment = min(timeline, key=lambda item: item["motion_mean"])
        if first["motion_mean"] < last["motion_mean"]:
            cues.append("energy ramps upward over time")
        elif first["motion_mean"] > last["motion_mean"]:
            cues.append("energy cools down over time")
        cues.append(f"climax near segment {max_motion_segment['segment_index'] + 1}")
        cues.append(f"quietest segment {min_motion_segment['segment_index'] + 1}")
    return cues


def summarize_conditioning_payload(clip_features: torch.Tensor | None, sync_features: torch.Tensor | None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if clip_features is not None:
        payload["clip_shape"] = list(clip_features.shape)
        payload["clip_mean_norm"] = float(torch.linalg.vector_norm(clip_features, dim=-1).mean().cpu().item())
        payload["clip_seq_len"] = int(clip_features.shape[1])
    if sync_features is not None:
        payload["sync_shape"] = list(sync_features.shape)
        payload["sync_mean_norm"] = float(torch.linalg.vector_norm(sync_features, dim=-1).mean().cpu().item())
        payload["sync_seq_len"] = int(sync_features.shape[1])
    return payload


def build_feature_prompt(features: dict[str, Any]) -> str:
    summary = features["summary"]
    timeline = features.get("timeline", [])
    semantic_cues = features.get("semantic_cues", [])
    parts = [
        f"video energy {summary['motion_mean']:.4f}",
        f"motion peak {summary['motion_peak']:.4f}",
        f"brightness {summary['mean_brightness']:.4f}",
        f"duration {summary['duration_sec']:.2f}s",
    ]
    if timeline:
        peak_segment = max(timeline, key=lambda item: item["motion_mean"])
        parts.append(f"visual climax around {peak_segment['start_sec']:.2f}-{peak_segment['end_sec']:.2f}s")
    if semantic_cues:
        parts.append("cues: " + ", ".join(semantic_cues[:6]))
    return ", ".join(parts)


def build_sfx_prompt(features: dict[str, Any], base_prompt: str) -> str:
    timeline = features.get("timeline", [])
    semantic_cues = features.get("semantic_cues", [])
    cue_lines: list[str] = []
    if timeline:
        ranked = sorted(timeline, key=lambda item: item["motion_peak"], reverse=True)
        for cue in ranked[:3]:
            cue_lines.append(
                f"accent {cue['start_sec']:.2f}-{cue['end_sec']:.2f}s motion={cue['motion_peak']:.4f} brightness={cue['mean_brightness']:.4f}"
            )
    prompt_parts = [base_prompt.strip()]
    if semantic_cues:
        prompt_parts.append("visual cues: " + ", ".join(semantic_cues[:4]))
    if cue_lines:
        prompt_parts.append("timing cues: " + " | ".join(cue_lines))
    prompt_parts.append("generate effect accents only, no music bed, no vocals, no dialogue")
    return "\n".join(part for part in prompt_parts if part)


def build_llm_context(features: dict[str, Any]) -> dict[str, Any]:
    context = {
        "summary": features.get("summary", {}),
        "timeline": features.get("timeline", []),
        "semantic_cues": features.get("semantic_cues", []),
        "qwenvl_scene_analysis": features.get("qwenvl_scene_analysis", ""),
        "qwenvl_analysis_language": features.get("qwenvl_analysis_language", ""),
        "conditioning_summary": features.get("conditioning_summary", {}),
        "latent_structure_cues": features.get("latent_structure_cues", []),
        "source_duration_sec": features.get("source_duration_sec", features.get("duration_sec", 0.0)),
        "loaded_duration_sec": features.get("loaded_duration_sec", features.get("duration_sec", 0.0)),
        "mmaudio_condition_duration_sec": features.get("mmaudio_condition_duration_sec", 0.0),
        "feature_contract": features.get("feature_contract", ""),
        "source_path": features.get("source_path", ""),
        "context_version": "aog.llm_context.v2",
    }
    context["context_sha256"] = hashlib.sha256(json.dumps(context, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return context


def to_pretty_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def interpolate_waveform(waveform: torch.Tensor, target_samples: int) -> torch.Tensor:
    if waveform.shape[-1] == target_samples:
        return waveform
    if waveform.ndim == 2:
        original = waveform.unsqueeze(0)
        resized = torch.nn.functional.interpolate(original, size=target_samples, mode="linear", align_corners=False)
        return resized.squeeze(0)
    if waveform.ndim == 3:
        return torch.nn.functional.interpolate(waveform, size=target_samples, mode="linear", align_corners=False)
    raise ValueError(f"Unsupported waveform ndim for interpolation: {waveform.ndim}")


def mix_audio_dicts(audio_a: dict[str, Any], audio_b: dict[str, Any], gain_b: float = 0.35) -> dict[str, Any]:
    audio_a = ensure_audio_dict(audio_a)
    audio_b = ensure_audio_dict(audio_b)
    sample_rate = audio_a["sample_rate"]
    waveform_a = audio_a["waveform"]
    waveform_b = audio_b["waveform"]
    if audio_b["sample_rate"] != sample_rate:
        ratio = sample_rate / audio_b["sample_rate"]
        target_samples = int(round(waveform_b.shape[-1] * ratio))
        waveform_b = interpolate_waveform(waveform_b, target_samples)
    target_samples = max(waveform_a.shape[-1], waveform_b.shape[-1])
    waveform_a = interpolate_waveform(waveform_a, target_samples)
    waveform_b = interpolate_waveform(waveform_b, target_samples)
    mixed = waveform_a + waveform_b * gain_b
    peak = float(mixed.abs().max().item()) if mixed.numel() > 0 else 0.0
    if peak > 1.0:
        mixed = mixed / peak
    return {"waveform": mixed, "sample_rate": sample_rate}


def audio_duration_sec(audio: dict[str, Any]) -> float:
    audio = ensure_audio_dict(audio)
    waveform = audio["waveform"]
    return float(waveform.shape[-1] / audio["sample_rate"]) if waveform.shape[-1] > 0 else 0.0


def pad_audio_to_duration(audio: dict[str, Any], target_duration_sec: float) -> dict[str, Any]:
    audio = ensure_audio_dict(audio)
    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])
    target_samples = max(1, int(round(target_duration_sec * sample_rate)))
    current_samples = int(waveform.shape[-1])
    if current_samples >= target_samples:
        return {"waveform": waveform, "sample_rate": sample_rate}
    pad_shape = list(waveform.shape)
    pad_shape[-1] = target_samples - current_samples
    padding = torch.zeros(pad_shape, dtype=waveform.dtype, device=waveform.device)
    return {"waveform": torch.cat([waveform, padding], dim=-1), "sample_rate": sample_rate}


def normalize_audio_duration(audio: dict[str, Any], target_duration_sec: float) -> dict[str, Any]:
    audio = ensure_audio_dict(audio)
    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])
    target_samples = max(1, int(round(target_duration_sec * sample_rate)))
    current_samples = int(waveform.shape[-1])
    if current_samples == target_samples:
        return {"waveform": waveform, "sample_rate": sample_rate}
    if current_samples < target_samples:
        return pad_audio_to_duration(audio, target_duration_sec)
    return {"waveform": waveform[..., :target_samples], "sample_rate": sample_rate}


def make_silent_audio(duration_sec: float, sample_rate: int = 44100, channels: int = 2) -> dict[str, Any]:
    sample_count = max(1, int(round(duration_sec * sample_rate)))
    waveform = torch.zeros((1, channels, sample_count), dtype=torch.float32)
    return {"waveform": waveform, "sample_rate": int(sample_rate)}


def chunk_list(items: list[Any], size: int) -> list[list[Any]]:
    if size <= 0:
        return [items]
    return [items[index:index + size] for index in range(0, len(items), size)]


def infer_song_sections(duration_sec: float) -> list[str]:
    if duration_sec < 10:
        return ["intro", "hook", "outro"]
    if duration_sec < 25:
        return ["intro", "verse", "pre-chorus", "chorus", "outro"]
    return ["intro", "verse", "pre-chorus", "chorus", "verse 2", "chorus", "outro"]
