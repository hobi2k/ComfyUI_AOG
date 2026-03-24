"""Helpers for directly invoking Wan 2.2 nodes from local Python."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .bootstrap import ComfyRuntimeModules
from .image_audio import load_image_tensor
from .paths import ComfyPaths


@dataclass(slots=True)
class WanRuntime:
    """Cache Wan node classes and loaded models for repeated shot renders."""

    modules: ComfyRuntimeModules
    comfy_paths: ComfyPaths
    model_bundles: dict[str, Any]
    runtime_validation: dict[str, Any]
    low_model: Any | None = None
    high_model: Any | None = None
    vae: Any | None = None
    t5: Any | None = None

    def ensure_loaded(self) -> None:
        """Load Wan high/low models, VAE, and T5 encoder once per process."""
        if self.low_model is None:
            loader = self.modules.wan_model_loading.WanVideoModelLoader()
            self.low_model = loader.loadmodel(
                model=self.comfy_paths.relative_model_name(self.model_bundles["video"]["i2v"]["low"], "diffusion_models"),
                base_precision="fp16_fast",
                load_device="offload_device",
                quantization="disabled",
                attention_mode=_map_attention_mode(self.runtime_validation.get("selected_attention_backend", "sdpa")),
            )[0]
            self.high_model = loader.loadmodel(
                model=self.comfy_paths.relative_model_name(self.model_bundles["video"]["i2v"]["high"], "diffusion_models"),
                base_precision="fp16_fast",
                load_device="offload_device",
                quantization="disabled",
                attention_mode=_map_attention_mode(self.runtime_validation.get("selected_attention_backend", "sdpa")),
            )[0]
        if self.vae is None:
            self.vae = self.modules.wan_model_loading.WanVideoVAELoader().loadmodel(
                model_name=self.comfy_paths.relative_model_name(self.model_bundles["video"]["bundle"]["vae"], "vae"),
                precision="bf16",
            )[0]
        if self.t5 is None:
            self.t5 = self.modules.wan_model_loading.LoadWanVideoT5TextEncoder().loadmodel(
                model_name=self.comfy_paths.relative_model_name(
                    self.model_bundles["video"]["bundle"]["text_encoder_primary"],
                    "text_encoders",
                ),
                precision="bf16",
                load_device="offload_device",
                quantization="disabled",
            )[0]

    def render_shot(
        self,
        *,
        shot_job: dict[str, Any],
        source_image_path: str,
        seed: int,
    ) -> Any:
        """
        Render one shot through the Wan node stack.

        Returns:
            Decoded image tensor batch from `WanVideoDecode`.
        """
        self.ensure_loaded()
        start_image = load_image_tensor(source_image_path)
        text_embeds = self.modules.wan_nodes.WanVideoTextEncode().process(
            positive_prompt=shot_job["text_prompt"],
            negative_prompt=shot_job["negative_prompt"],
            t5=self.t5,
            force_offload=True,
            device="gpu",
        )[0]
        num_frames = _coerce_frame_count(float(shot_job["duration"]), int(shot_job["fps"]))
        image_embeds = self.modules.wan_nodes.WanVideoImageToVideoEncode().process(
            width=int(shot_job["resolution"]["width"]),
            height=int(shot_job["resolution"]["height"]),
            num_frames=num_frames,
            force_offload=True,
            noise_aug_strength=0.0,
            start_latent_strength=1.0,
            end_latent_strength=1.0,
            start_image=start_image,
            vae=self.vae,
        )[0]
        low_steps = max(1, int(shot_job["steps"]) // 3)
        low_samples = self.modules.wan_nodes.WanVideoSampler().process(
            model=self.low_model,
            image_embeds=image_embeds,
            text_embeds=text_embeds,
            shift=5.0,
            steps=int(shot_job["steps"]),
            cfg=float(shot_job["guidance_scale"]),
            seed=int(seed),
            scheduler="dpm++_sde",
            riflex_freq_index=0,
            force_offload=True,
            rope_function="comfy",
            end_step=low_steps,
        )[0]
        high_samples = self.modules.wan_nodes.WanVideoSampler().process(
            model=self.high_model,
            image_embeds=image_embeds,
            text_embeds=text_embeds,
            samples=low_samples,
            shift=5.0,
            steps=int(shot_job["steps"]),
            cfg=float(shot_job["guidance_scale"]),
            seed=int(seed),
            scheduler="dpm++_sde",
            riflex_freq_index=0,
            force_offload=True,
            rope_function="comfy",
            start_step=low_steps,
        )[0]
        return self.modules.wan_nodes.WanVideoDecode().decode(
            vae=self.vae,
            samples=high_samples,
            enable_vae_tiling=False,
            tile_x=272,
            tile_y=272,
            tile_stride_x=144,
            tile_stride_y=128,
            normalization="default",
        )[0]


def _coerce_frame_count(duration_seconds: float, fps: int) -> int:
    """Convert duration and fps into the 4n+1 frame count expected by Wan I2V."""
    raw = max(5, round(duration_seconds * fps))
    return ((raw - 1) // 4) * 4 + 1


def _map_attention_mode(selected_backend: str) -> str:
    """Map generic runtime backend names to Wan wrapper attention names."""
    if selected_backend == "sageattention":
        return "sageattn"
    if selected_backend == "sdpa":
        return "sdpa"
    return "comfy"
