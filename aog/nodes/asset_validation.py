"""Validate project assets before the pipeline builds render manifests."""

from __future__ import annotations

from pathlib import Path

from aog.config.schema import AOGProjectConfig, ValidationMode

from .base import BaseNode, NodeResult


class AssetValidationNode(BaseNode):
    """Check input assets and mark placeholders versus runtime failures."""

    name = "asset_validation"

    def run(self, *, config: AOGProjectConfig, validation_mode: ValidationMode) -> NodeResult:
        """
        Validate source images, references, lyrics, and voice clone inputs.

        Args:
            config: 현재 프로젝트 설정 객체다.
            validation_mode: 예제 검증인지 런타임 검증인지 나타낸다.

        Returns:
            자산 존재 여부와 경고 목록을 담은 결과 객체다.
        """
        warnings: list[str] = []
        payload = {
            "source_images": self._validate_image_assets(
                config.inputs.source_images,
                "source image",
                validation_mode,
                warnings,
            ),
            "reference_images": self._validate_image_assets(
                config.inputs.reference_images,
                "reference image",
                validation_mode,
                warnings,
            ),
            "lyrics_path": self._validate_single_asset(config.audio.vocal.lyrics_path),
            "voice_clone_dir": self._validate_single_asset(config.audio.voice_clone.reference_audio_dir),
        }
        return NodeResult(name=self.name, payload=payload, warnings=warnings)

    def _validate_image_assets(
        self,
        paths: list[str],
        asset_label: str,
        validation_mode: ValidationMode,
        warnings: list[str],
    ) -> list[dict[str, str | bool]]:
        """Validate a list of image paths and accumulate warnings."""
        results: list[dict[str, str | bool]] = []
        for path in paths:
            asset_exists = Path(path).exists()
            if validation_mode == ValidationMode.RUNTIME and not asset_exists:
                warnings.append(f"Missing {asset_label}: {path}")
            elif validation_mode == ValidationMode.EXAMPLE and not asset_exists:
                warnings.append(f"Placeholder {asset_label}: {path}")
            results.append({"path": path, "exists": asset_exists})
        return results

    def _validate_single_asset(self, path: str) -> dict[str, str | bool]:
        """Build a simple existence payload for a single asset path."""
        return {"path": path, "exists": Path(path).exists()}
