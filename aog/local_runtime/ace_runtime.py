"""Helpers for directly invoking Ace Step nodes from local Python."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .bootstrap import ComfyRuntimeModules
from .image_audio import load_audio_waveform
from .paths import ComfyPaths


@dataclass(slots=True)
class AceRuntime:
    """Cache Ace Step loaders and run audio generation in local Python."""

    modules: ComfyRuntimeModules
    comfy_paths: ComfyPaths
    model_bundles: dict[str, Any]
    unet: Any | None = None
    clip: Any | None = None
    vae: Any | None = None

    def ensure_loaded(self) -> None:
        """Load Ace Step model components once per process."""
        if self.unet is None:
            self.unet = self.modules.nodes.UNETLoader().load_unet(
                unet_name=self.comfy_paths.relative_model_name(self.model_bundles["audio"]["diffusion_model"], "diffusion_models"),
                weight_dtype="default",
            )[0]
        if self.clip is None:
            self.clip = self.modules.nodes.DualCLIPLoader().load_clip(
                clip_name1=self.comfy_paths.relative_model_name(self.model_bundles["audio"]["text_encoder_1"], "text_encoders"),
                clip_name2=self.comfy_paths.relative_model_name(self.model_bundles["audio"]["text_encoder_2"], "text_encoders"),
                type="ace",
                device="default",
            )[0]
        if self.vae is None:
            self.vae = self.modules.nodes.VAELoader().load_vae(
                vae_name=self.comfy_paths.relative_model_name(self.model_bundles["audio"]["vae"], "vae"),
            )[0]

    def render_audio(
        self,
        *,
        audio_job: dict[str, Any],
        seed: int,
        voice_reference_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate one Ace Step audio clip and return the decoded waveform payload.

        Returns:
            `{"waveform": tensor, "sample_rate": int}` 형태의 오디오 payload다.
        """
        self.ensure_loaded()
        lyrics = ""
        if audio_job.get("lyrics_path"):
            from pathlib import Path

            lyrics = Path(audio_job["lyrics_path"]).read_text(encoding="utf-8")
        positive = self.modules.nodes_ace.TextEncodeAceStepAudio15.execute(
            clip=self.clip,
            tags=audio_job["prompt"],
            lyrics=lyrics,
            seed=int(seed),
            bpm=int(audio_job["bpm_target"] or 132),
            duration=float(audio_job["duration"]),
            timesignature="4",
            language="ko",
            keyscale="A minor",
            generate_audio_codes=True,
            cfg_scale=2.0,
            temperature=0.85,
            top_p=0.9,
            top_k=0,
            min_p=0.0,
        )[0]
        if voice_reference_path:
            waveform, sample_rate = load_audio_waveform(voice_reference_path)
            reference_audio = {"waveform": waveform[0], "sample_rate": sample_rate}
            latent = self.modules.nodes_audio.VAEEncodeAudio.execute(
                vae=self.vae,
                audio=reference_audio,
            )[0]
            positive = self.modules.nodes_ace.ReferenceAudio.execute(
                conditioning=positive,
                latent=latent,
            )[0]
        negative = self.modules.nodes_ace.TextEncodeAceStepAudio15.execute(
            clip=self.clip,
            tags="",
            lyrics="",
            seed=int(seed),
            bpm=int(audio_job["bpm_target"] or 132),
            duration=float(audio_job["duration"]),
            timesignature="4",
            language="ko",
            keyscale="A minor",
            generate_audio_codes=False,
            cfg_scale=1.0,
            temperature=0.85,
            top_p=0.9,
            top_k=0,
            min_p=0.0,
        )[0]
        latent_audio = self.modules.nodes_ace.EmptyAceStep15LatentAudio.execute(
            seconds=float(audio_job["duration"]),
            batch_size=1,
        )[0]
        sampled = self.modules.nodes.KSampler().sample(
            model=self.unet,
            seed=int(seed),
            steps=30,
            cfg=3.5,
            sampler_name="dpmpp_2m",
            scheduler="normal",
            positive=positive,
            negative=negative,
            latent_image=latent_audio,
            denoise=1.0,
        )[0]
        return self.modules.nodes_audio.VAEDecodeAudio.execute(
            vae=self.vae,
            samples=sampled,
        )[0]
