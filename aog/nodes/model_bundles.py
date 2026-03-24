"""Collect model bundle paths into a downstream-friendly manifest payload."""

from __future__ import annotations

from aog.config.schema import AOGProjectConfig

from .base import BaseNode, NodeResult


class ModelBundleNode(BaseNode):
    """Summarize all model bundle locations used by the pipeline."""

    name = "model_bundles"

    def run(self, *, config: AOGProjectConfig) -> NodeResult:
        """
        Collect the video, audio, and post-process model bundles.

        Args:
            config: 현재 프로젝트 설정 객체다.

        Returns:
            하위 executor가 읽기 쉬운 모델 번들 payload다.
        """
        payload = {
            "video": self._build_video_bundle_payload(config),
            "audio": self._build_audio_bundle_payload(config),
            "postprocess": self._build_postprocess_payload(config),
        }
        return NodeResult(name=self.name, payload=payload)

    def _build_video_bundle_payload(self, config: AOGProjectConfig) -> dict[str, object]:
        """Build the video model manifest for downstream executors."""
        return {
            "i2v": {
                "high": config.video.i2v_model.path_high,
                "low": config.video.i2v_model.path_low,
                "format": config.video.i2v_model.format,
                "profile": config.video.i2v_model.profile,
            },
            "bundle": {
                "vae": config.video.bundle.vae.path,
                "text_encoder_primary": config.video.bundle.text_encoder_primary.path,
                "text_encoder_secondary": config.video.bundle.text_encoder_secondary.path,
                "clip_vision": config.video.bundle.clip_vision.path if config.video.bundle.clip_vision else None,
            },
            "s2v": {
                "high": config.video.s2v_model.path_high,
                "low": config.video.s2v_model.path_low,
                "format": config.video.s2v_model.format,
                "profile": config.video.s2v_model.profile,
            },
            "svi_lora": {
                "enabled": config.video.use_svi_lora,
                "high": config.video.svi_lora.path_high if config.video.svi_lora else None,
                "low": config.video.svi_lora.path_low if config.video.svi_lora else None,
                "strength": config.video.svi_lora.strength if config.video.svi_lora else None,
            },
            "acceleration": {
                "attention_backend": config.video.acceleration.attention_backend,
                "sageattention_enabled": config.video.acceleration.sageattention_enabled,
                "sageattention_required": config.video.acceleration.sageattention_required,
                "fallback_attention": config.video.acceleration.fallback_attention,
                "require_cuda": config.video.acceleration.require_cuda,
            },
        }

    def _build_audio_bundle_payload(self, config: AOGProjectConfig) -> dict[str, str]:
        """Build the audio model manifest for Ace Step."""
        return {
            "diffusion_model": config.audio.bundle.diffusion_model.path,
            "text_encoder_1": config.audio.bundle.text_encoders.clip_file_1,
            "text_encoder_2": config.audio.bundle.text_encoders.clip_file_2,
            "vae": config.audio.bundle.vae.path,
        }

    def _build_postprocess_payload(self, config: AOGProjectConfig) -> dict[str, str]:
        """Build the post-process model manifest."""
        return {
            "upscale_model": config.postprocess.upscale.model_path,
            "frame_interpolation_model": config.postprocess.frame_interpolation.model_path,
        }
