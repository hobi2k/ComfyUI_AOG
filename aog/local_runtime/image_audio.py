"""Tensor conversion helpers shared by local Wan and Ace runtimes."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import soundfile as sf
import torch
from PIL import Image


def load_image_tensor(path: str | Path) -> torch.Tensor:
    """
    Load an image file into the tensor layout expected by Comfy image nodes.

    Returns:
        Shape `[1, H, W, C]`, float32, range `[0, 1]`.
    """
    image = Image.open(path).convert("RGB")
    array = np.asarray(image).astype("float32") / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def save_image_frames(images: torch.Tensor, frame_dir: str | Path) -> list[Path]:
    """
    Save a Comfy image tensor batch as sequential PNG frames.

    Args:
        images: Shape `[T, H, W, C]` or `[1, H, W, C]`.
        frame_dir: 저장할 프레임 디렉터리다.
    """
    target_dir = Path(frame_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    batch = images.detach().cpu()
    if batch.ndim == 3:
        batch = batch.unsqueeze(0)
    frame_paths: list[Path] = []
    for index, frame in enumerate(batch):
        frame_uint8 = np.clip(frame.numpy() * 255.0, 0, 255).astype(np.uint8)
        path = target_dir / f"frame_{index:05d}.png"
        Image.fromarray(frame_uint8).save(path)
        frame_paths.append(path)
    return frame_paths


def load_audio_waveform(path: str | Path) -> tuple[torch.Tensor, int]:
    """
    Load an audio file into a tensor suitable for Comfy audio nodes.

    Returns:
        Tuple of waveform tensor `[1, channels, samples]` and sample rate.
    """
    waveform, sample_rate = sf.read(str(path), always_2d=True, dtype="float32")
    tensor = torch.from_numpy(waveform.T).unsqueeze(0)
    return tensor, sample_rate


def save_audio_waveform(waveform: torch.Tensor, sample_rate: int, path: str | Path) -> Path:
    """
    Save a waveform tensor to disk using SoundFile.

    Args:
        waveform: Shape `[1, channels, samples]` or `[channels, samples]`.
        sample_rate: 저장 sample rate다.
        path: 출력 파일 경로다.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio = waveform.detach().cpu()
    if audio.ndim == 3:
        audio = audio[0]
    if audio.ndim != 2:
        raise ValueError(f"Expected audio tensor with 2 dims, got shape {tuple(audio.shape)}")
    sf.write(str(output_path), audio.transpose(0, 1).numpy(), sample_rate)
    return output_path
