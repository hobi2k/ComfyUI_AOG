"""Resolve which image source each extension segment should use."""

from __future__ import annotations

from aog.config.schema import AOGProjectConfig

from .base import BaseNode, NodeResult


class ExtensionSourceNode(BaseNode):
    """Build the extension input plan from shot outputs and config rules."""

    name = "extension_source"

    def run(self, *, config: AOGProjectConfig, shot_plan: dict) -> NodeResult:
        """
        Build an extension source entry for every planned shot.

        Args:
            config: 현재 프로젝트 설정 객체다.
            shot_plan: shot planning node가 만든 payload다.

        Returns:
            extension 입력 이미지 계획을 담은 결과 객체다.
        """
        mode = config.video.extension.source_mode
        custom_image = config.video.extension.custom_image
        extension_plan = [
            self._build_extension_source_entry(shot, mode, custom_image)
            for shot in shot_plan["shots"]
        ]
        return NodeResult(
            name=self.name,
            payload={
                "source_mode": mode,
                "custom_image": custom_image,
                "extension_plan": extension_plan,
            },
        )

    def _build_extension_source_entry(
        self,
        shot: dict,
        source_mode: str,
        custom_image: str | None,
    ) -> dict[str, str | bool | int | None]:
        """Build the extension image selection for a single shot."""
        source_image = (
            f"shots/{shot['output_stem']}/{shot['output_stem']}_lastframe.png"
            if source_mode == "last_frame"
            else custom_image
        )
        return {
            "shot_index": shot["index"],
            "enabled": bool(shot["extension_needed"]),
            "source_mode": source_mode,
            "source_image": source_image,
        }
