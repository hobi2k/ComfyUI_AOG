"""Typed config schema and validation helpers for the AOG pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ValidationMode(str, Enum):
    """Choose whether config validation should allow example placeholders."""

    EXAMPLE = "example"
    RUNTIME = "runtime"


class ConfigError(ValueError):
    """Raised when config data does not match the expected schema."""


def _expect_mapping(value: Any, field_name: str) -> dict[str, Any]:
    """Ensure a raw config value is a mapping."""
    if not isinstance(value, dict):
        raise ConfigError(f"`{field_name}` must be a mapping")
    return value


def _expect_list(value: Any, field_name: str) -> list[Any]:
    """Ensure a raw config value is a list."""
    if not isinstance(value, list):
        raise ConfigError(f"`{field_name}` must be a list")
    return value


def _require(value: Any, field_name: str) -> Any:
    """Ensure a required config value is present."""
    if value is None:
        raise ConfigError(f"`{field_name}` is required")
    return value


def _as_str(value: Any, field_name: str) -> str:
    """Convert a raw value into a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"`{field_name}` must be a non-empty string")
    return value


def _as_bool(value: Any, field_name: str) -> bool:
    """Convert a raw value into a boolean."""
    if not isinstance(value, bool):
        raise ConfigError(f"`{field_name}` must be a boolean")
    return value


def _as_int(value: Any, field_name: str) -> int:
    """Convert a raw value into an integer without accepting booleans."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"`{field_name}` must be an integer")
    return value


def _as_float(value: Any, field_name: str) -> float:
    """Convert a raw value into a numeric float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"`{field_name}` must be a number")
    return float(value)


def _check_path(path: str, field_name: str, mode: ValidationMode) -> None:
    """Check that a filesystem path exists when runtime validation is enabled."""
    if mode == ValidationMode.RUNTIME and not Path(path).exists():
        raise ConfigError(f"`{field_name}` path does not exist: {path}")


def _get_optional_mapping_value(mapping: dict[str, Any], key: str) -> dict[str, Any] | None:
    """Return a child mapping when it exists and has the expected shape."""
    value = mapping.get(key)
    if value is None:
        return None
    return _expect_mapping(value, key)


def _read_named_file_ref(
    container: dict[str, Any],
    key: str,
    field_name: str,
    mode: ValidationMode,
) -> "FileRef":
    """
    Read a named file reference from a parent mapping.

    Args:
        container: 여러 파일 참조를 담은 상위 매핑이다.
        key: 꺼낼 하위 키 이름이다.
        field_name: 오류 메시지에 사용할 전체 경로 이름이다.
        mode: 현재 검증 모드다.

    Returns:
        파싱된 파일 참조 객체다.
    """
    nested_value = _get_optional_mapping_value(container, key)
    if nested_value is None:
        raise ConfigError(f"`{field_name}` is required")
    return FileRef.from_dict(nested_value, field_name, mode)


def _validate_runtime_extension_assets(config: "AOGProjectConfig", mode: ValidationMode) -> None:
    """
    Validate runtime-only extension assets that depend on cross-field rules.

    Args:
        config: 이미 파싱된 프로젝트 설정 객체다.
        mode: 예제 검증인지 런타임 검증인지 나타낸다.
    """
    if mode != ValidationMode.RUNTIME:
        return
    if config.video.extension.source_mode == "custom_image":
        _check_path(
            config.video.extension.custom_image or "",
            "video.extension.custom_image",
            mode,
        )


@dataclass(slots=True)
class FileRef:
    """Describe a single file-based dependency used by the pipeline."""

    path: str
    format: str | None = None
    profile: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "FileRef":
        """Parse a file reference from raw config data."""
        path = _as_str(_require(data.get("path"), f"{field_name}.path"), f"{field_name}.path")
        _check_path(path, f"{field_name}.path", mode)
        fmt = data.get("format")
        if fmt is not None:
            fmt = _as_str(fmt, f"{field_name}.format")
        profile = data.get("profile")
        if profile is not None:
            profile = _as_str(profile, f"{field_name}.profile")
        return cls(path=path, format=fmt, profile=profile)


@dataclass(slots=True)
class HighLowModelRef:
    """Describe a paired high-noise and low-noise model bundle entry."""

    family: str
    variant: str
    format: str
    path_high: str
    path_low: str
    profile: str
    runtime_backend: str

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], field_name: str, mode: ValidationMode
    ) -> "HighLowModelRef":
        """Parse a high/low model pair from raw config data."""
        path_high = _as_str(_require(data.get("path_high"), f"{field_name}.path_high"), f"{field_name}.path_high")
        path_low = _as_str(_require(data.get("path_low"), f"{field_name}.path_low"), f"{field_name}.path_low")
        _check_path(path_high, f"{field_name}.path_high", mode)
        _check_path(path_low, f"{field_name}.path_low", mode)
        return cls(
            family=_as_str(_require(data.get("family"), f"{field_name}.family"), f"{field_name}.family"),
            variant=_as_str(_require(data.get("variant"), f"{field_name}.variant"), f"{field_name}.variant"),
            format=_as_str(_require(data.get("format"), f"{field_name}.format"), f"{field_name}.format"),
            path_high=path_high,
            path_low=path_low,
            profile=_as_str(_require(data.get("profile"), f"{field_name}.profile"), f"{field_name}.profile"),
            runtime_backend=_as_str(
                _require(data.get("runtime_backend"), f"{field_name}.runtime_backend"),
                f"{field_name}.runtime_backend",
            ),
        )


@dataclass(slots=True)
class WanBundle:
    """Group the supporting files needed to run Wan-based video generation."""

    vae: FileRef
    text_encoder_primary: FileRef
    text_encoder_secondary: FileRef
    clip_vision: FileRef | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "WanBundle":
        """Parse the Wan support bundle from raw config data."""
        text_encoders = _expect_mapping(_require(data.get("text_encoders"), f"{field_name}.text_encoders"), f"{field_name}.text_encoders")
        clip_vision_data = data.get("clip_vision")
        return cls(
            vae=FileRef.from_dict(_expect_mapping(_require(data.get("vae"), f"{field_name}.vae"), f"{field_name}.vae"), f"{field_name}.vae", mode),
            text_encoder_primary=_read_named_file_ref(
                text_encoders,
                "primary",
                f"{field_name}.text_encoders.primary",
                mode,
            ),
            text_encoder_secondary=_read_named_file_ref(
                text_encoders,
                "secondary",
                f"{field_name}.text_encoders.secondary",
                mode,
            ),
            clip_vision=(
                FileRef.from_dict(_expect_mapping(clip_vision_data, f"{field_name}.clip_vision"), f"{field_name}.clip_vision", mode)
                if clip_vision_data is not None
                else None
            ),
        )


@dataclass(slots=True)
class SviLoraConfig:
    """Store the paired LoRA files used for Wan continuity support."""

    path_high: str
    path_low: str
    strength: float

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "SviLoraConfig":
        path_high = _as_str(_require(data.get("path_high"), f"{field_name}.path_high"), f"{field_name}.path_high")
        path_low = _as_str(_require(data.get("path_low"), f"{field_name}.path_low"), f"{field_name}.path_low")
        _check_path(path_high, f"{field_name}.path_high", mode)
        _check_path(path_low, f"{field_name}.path_low", mode)
        return cls(
            path_high=path_high,
            path_low=path_low,
            strength=_as_float(_require(data.get("strength"), f"{field_name}.strength"), f"{field_name}.strength"),
        )


@dataclass(slots=True)
class BaseResolution:
    """Represent a concrete output resolution for a render pass."""

    width: int
    height: int

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "BaseResolution":
        return cls(
            width=_as_int(_require(data.get("width"), f"{field_name}.width"), f"{field_name}.width"),
            height=_as_int(_require(data.get("height"), f"{field_name}.height"), f"{field_name}.height"),
        )


@dataclass(slots=True)
class VideoGenerationConfig:
    """Store the common generation parameters used for Wan shots."""

    fps: int
    base_resolution: BaseResolution
    guidance_scale: float
    steps: int
    negative_prompt: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "VideoGenerationConfig":
        return cls(
            fps=_as_int(_require(data.get("fps"), f"{field_name}.fps"), f"{field_name}.fps"),
            base_resolution=BaseResolution.from_dict(
                _expect_mapping(_require(data.get("base_resolution"), f"{field_name}.base_resolution"), f"{field_name}.base_resolution"),
                f"{field_name}.base_resolution",
            ),
            guidance_scale=_as_float(_require(data.get("guidance_scale"), f"{field_name}.guidance_scale"), f"{field_name}.guidance_scale"),
            steps=_as_int(_require(data.get("steps"), f"{field_name}.steps"), f"{field_name}.steps"),
            negative_prompt=_as_str(_require(data.get("negative_prompt"), f"{field_name}.negative_prompt"), f"{field_name}.negative_prompt"),
        )


@dataclass(slots=True)
class AccelerationConfig:
    """Describe which attention backend the runtime should prefer."""

    attention_backend: str
    sageattention_enabled: bool
    sageattention_required: bool
    fallback_attention: str
    require_cuda: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "AccelerationConfig":
        attention_backend = _as_str(_require(data.get("attention_backend"), f"{field_name}.attention_backend"), f"{field_name}.attention_backend")
        fallback_attention = _as_str(_require(data.get("fallback_attention"), f"{field_name}.fallback_attention"), f"{field_name}.fallback_attention")
        if attention_backend not in {"sageattention", "xformers", "sdpa", "comfy_default"}:
            raise ConfigError(
                f"`{field_name}.attention_backend` must be one of: sageattention, xformers, sdpa, comfy_default"
            )
        if fallback_attention not in {"xformers", "sdpa", "comfy_default"}:
            raise ConfigError(
                f"`{field_name}.fallback_attention` must be one of: xformers, sdpa, comfy_default"
            )
        return cls(
            attention_backend=attention_backend,
            sageattention_enabled=_as_bool(
                _require(data.get("sageattention_enabled"), f"{field_name}.sageattention_enabled"),
                f"{field_name}.sageattention_enabled",
            ),
            sageattention_required=_as_bool(
                _require(data.get("sageattention_required"), f"{field_name}.sageattention_required"),
                f"{field_name}.sageattention_required",
            ),
            fallback_attention=fallback_attention,
            require_cuda=_as_bool(
                _require(data.get("require_cuda"), f"{field_name}.require_cuda"),
                f"{field_name}.require_cuda",
            ),
        )


@dataclass(slots=True)
class ExtensionConfig:
    """Describe how an extended video segment should pick its input image."""

    enabled: bool
    max_extension_seconds_per_shot: float
    source_mode: str
    custom_image: str | None
    apply_when: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "ExtensionConfig":
        apply_when = [_as_str(item, f"{field_name}.apply_when[]") for item in _expect_list(_require(data.get("apply_when"), f"{field_name}.apply_when"), f"{field_name}.apply_when")]
        source_mode = _as_str(_require(data.get("source_mode"), f"{field_name}.source_mode"), f"{field_name}.source_mode")
        custom_image = data.get("custom_image")
        if custom_image is not None and custom_image != "":
            custom_image = _as_str(custom_image, f"{field_name}.custom_image")
        else:
            custom_image = None
        if source_mode not in {"last_frame", "custom_image"}:
            raise ConfigError(f"`{field_name}.source_mode` must be `last_frame` or `custom_image`")
        if source_mode == "custom_image" and not custom_image:
            raise ConfigError(f"`{field_name}.custom_image` is required when source_mode is `custom_image`")
        return cls(
            enabled=_as_bool(_require(data.get("enabled"), f"{field_name}.enabled"), f"{field_name}.enabled"),
            max_extension_seconds_per_shot=_as_float(
                _require(data.get("max_extension_seconds_per_shot"), f"{field_name}.max_extension_seconds_per_shot"),
                f"{field_name}.max_extension_seconds_per_shot",
            ),
            source_mode=source_mode,
            custom_image=custom_image,
            apply_when=apply_when,
        )


@dataclass(slots=True)
class VideoConfig:
    """Group all video generation settings for the pipeline."""

    i2v_model: HighLowModelRef
    bundle: WanBundle
    s2v_model: HighLowModelRef
    chain_strategy: str
    use_svi_lora: bool
    svi_lora: SviLoraConfig | None
    generation: VideoGenerationConfig
    acceleration: AccelerationConfig
    extension: ExtensionConfig

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "VideoConfig":
        use_svi_lora = _as_bool(_require(data.get("use_svi_lora"), f"{field_name}.use_svi_lora"), f"{field_name}.use_svi_lora")
        svi_data = data.get("svi_lora")
        svi_lora = SviLoraConfig.from_dict(_expect_mapping(svi_data, f"{field_name}.svi_lora"), f"{field_name}.svi_lora", mode) if svi_data is not None else None
        if use_svi_lora and svi_lora is None:
            raise ConfigError(f"`{field_name}.svi_lora` is required when `use_svi_lora` is true")
        return cls(
            i2v_model=HighLowModelRef.from_dict(_expect_mapping(_require(data.get("i2v_model"), f"{field_name}.i2v_model"), f"{field_name}.i2v_model"), f"{field_name}.i2v_model", mode),
            bundle=WanBundle.from_dict(_expect_mapping(_require(data.get("bundle"), f"{field_name}.bundle"), f"{field_name}.bundle"), f"{field_name}.bundle", mode),
            s2v_model=HighLowModelRef.from_dict(_expect_mapping(_require(data.get("s2v_model"), f"{field_name}.s2v_model"), f"{field_name}.s2v_model"), f"{field_name}.s2v_model", mode),
            chain_strategy=_as_str(_require(data.get("chain_strategy"), f"{field_name}.chain_strategy"), f"{field_name}.chain_strategy"),
            use_svi_lora=use_svi_lora,
            svi_lora=svi_lora,
            generation=VideoGenerationConfig.from_dict(_expect_mapping(_require(data.get("generation"), f"{field_name}.generation"), f"{field_name}.generation"), f"{field_name}.generation"),
            acceleration=AccelerationConfig.from_dict(
                _expect_mapping(_require(data.get("acceleration"), f"{field_name}.acceleration"), f"{field_name}.acceleration"),
                f"{field_name}.acceleration",
            ),
            extension=ExtensionConfig.from_dict(_expect_mapping(_require(data.get("extension"), f"{field_name}.extension"), f"{field_name}.extension"), f"{field_name}.extension"),
        )


@dataclass(slots=True)
class AceTextEncoders:
    """Describe the two text encoders used by Ace Step."""

    clip_file_1: str
    clip_file_2: str
    type: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "AceTextEncoders":
        clip_file_1 = _as_str(_require(data.get("clip_file_1"), f"{field_name}.clip_file_1"), f"{field_name}.clip_file_1")
        clip_file_2 = _as_str(_require(data.get("clip_file_2"), f"{field_name}.clip_file_2"), f"{field_name}.clip_file_2")
        _check_path(clip_file_1, f"{field_name}.clip_file_1", mode)
        _check_path(clip_file_2, f"{field_name}.clip_file_2", mode)
        return cls(
            clip_file_1=clip_file_1,
            clip_file_2=clip_file_2,
            type=_as_str(_require(data.get("type"), f"{field_name}.type"), f"{field_name}.type"),
        )


@dataclass(slots=True)
class AceBundle:
    """Group the model files needed to run Ace Step."""

    diffusion_model: FileRef
    text_encoders: AceTextEncoders
    vae: FileRef

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "AceBundle":
        return cls(
            diffusion_model=FileRef.from_dict(_expect_mapping(_require(data.get("diffusion_model"), f"{field_name}.diffusion_model"), f"{field_name}.diffusion_model"), f"{field_name}.diffusion_model", mode),
            text_encoders=AceTextEncoders.from_dict(_expect_mapping(_require(data.get("text_encoders"), f"{field_name}.text_encoders"), f"{field_name}.text_encoders"), f"{field_name}.text_encoders", mode),
            vae=FileRef.from_dict(_expect_mapping(_require(data.get("vae"), f"{field_name}.vae"), f"{field_name}.vae"), f"{field_name}.vae", mode),
        )


@dataclass(slots=True)
class AudioToggle:
    """Represent a simple enabled-only audio section."""

    enabled: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "AudioToggle":
        return cls(enabled=_as_bool(_require(data.get("enabled"), f"{field_name}.enabled"), f"{field_name}.enabled"))


@dataclass(slots=True)
class VocalConfig:
    """Describe how vocal generation should be configured."""

    enabled: bool
    lyrics_mode: str
    lyrics_path: str
    style_prompt: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "VocalConfig":
        lyrics_path = _as_str(_require(data.get("lyrics_path"), f"{field_name}.lyrics_path"), f"{field_name}.lyrics_path")
        _check_path(lyrics_path, f"{field_name}.lyrics_path", mode)
        return cls(
            enabled=_as_bool(_require(data.get("enabled"), f"{field_name}.enabled"), f"{field_name}.enabled"),
            lyrics_mode=_as_str(_require(data.get("lyrics_mode"), f"{field_name}.lyrics_mode"), f"{field_name}.lyrics_mode"),
            lyrics_path=lyrics_path,
            style_prompt=_as_str(_require(data.get("style_prompt"), f"{field_name}.style_prompt"), f"{field_name}.style_prompt"),
        )


@dataclass(slots=True)
class VoiceCloneConfig:
    """Describe how a voice clone reference should be resolved."""

    enabled: bool
    clone_id: str
    reference_audio_dir: str
    mix_mode: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "VoiceCloneConfig":
        reference_audio_dir = _as_str(_require(data.get("reference_audio_dir"), f"{field_name}.reference_audio_dir"), f"{field_name}.reference_audio_dir")
        _check_path(reference_audio_dir, f"{field_name}.reference_audio_dir", mode)
        return cls(
            enabled=_as_bool(_require(data.get("enabled"), f"{field_name}.enabled"), f"{field_name}.enabled"),
            clone_id=_as_str(_require(data.get("clone_id"), f"{field_name}.clone_id"), f"{field_name}.clone_id"),
            reference_audio_dir=reference_audio_dir,
            mix_mode=_as_str(_require(data.get("mix_mode"), f"{field_name}.mix_mode"), f"{field_name}.mix_mode"),
        )


@dataclass(slots=True)
class AudioStructureItem:
    """Represent a labeled time section in the generated song structure."""

    label: str
    start: float
    end: float

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "AudioStructureItem":
        return cls(
            label=_as_str(_require(data.get("label"), f"{field_name}.label"), f"{field_name}.label"),
            start=_as_float(_require(data.get("start"), f"{field_name}.start"), f"{field_name}.start"),
            end=_as_float(_require(data.get("end"), f"{field_name}.end"), f"{field_name}.end"),
        )


@dataclass(slots=True)
class AudioConfig:
    """Group all audio generation settings for the pipeline."""

    engine: str
    bundle: AceBundle
    generation_mode: str
    output_mode: str
    prompt: str
    instrumental: AudioToggle
    vocal: VocalConfig
    voice_clone: VoiceCloneConfig
    bpm_target: int | None = None
    structure: list[AudioStructureItem] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "AudioConfig":
        structure_data = data.get("structure") or []
        if not isinstance(structure_data, list):
            raise ConfigError(f"`{field_name}.structure` must be a list when provided")
        bpm_target = data.get("bpm_target")
        if bpm_target is not None:
            bpm_target = _as_int(bpm_target, f"{field_name}.bpm_target")
        return cls(
            engine=_as_str(_require(data.get("engine"), f"{field_name}.engine"), f"{field_name}.engine"),
            bundle=AceBundle.from_dict(_expect_mapping(_require(data.get("bundle"), f"{field_name}.bundle"), f"{field_name}.bundle"), f"{field_name}.bundle", mode),
            generation_mode=_as_str(_require(data.get("generation_mode"), f"{field_name}.generation_mode"), f"{field_name}.generation_mode"),
            output_mode=_as_str(_require(data.get("output_mode"), f"{field_name}.output_mode"), f"{field_name}.output_mode"),
            prompt=_as_str(_require(data.get("prompt"), f"{field_name}.prompt"), f"{field_name}.prompt"),
            instrumental=AudioToggle.from_dict(_expect_mapping(_require(data.get("instrumental"), f"{field_name}.instrumental"), f"{field_name}.instrumental"), f"{field_name}.instrumental"),
            vocal=VocalConfig.from_dict(_expect_mapping(_require(data.get("vocal"), f"{field_name}.vocal"), f"{field_name}.vocal"), f"{field_name}.vocal", mode),
            voice_clone=VoiceCloneConfig.from_dict(_expect_mapping(_require(data.get("voice_clone"), f"{field_name}.voice_clone"), f"{field_name}.voice_clone"), f"{field_name}.voice_clone", mode),
            bpm_target=bpm_target,
            structure=[AudioStructureItem.from_dict(_expect_mapping(item, f"{field_name}.structure[]"), f"{field_name}.structure[]") for item in structure_data],
        )


@dataclass(slots=True)
class TitleConfig:
    """Describe title overlay text and timing."""

    text: str
    overlay_enabled: bool
    timing_seconds: float

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "TitleConfig":
        return cls(
            text=_as_str(_require(data.get("text"), f"{field_name}.text"), f"{field_name}.text"),
            overlay_enabled=_as_bool(_require(data.get("overlay_enabled"), f"{field_name}.overlay_enabled"), f"{field_name}.overlay_enabled"),
            timing_seconds=_as_float(_require(data.get("timing_seconds"), f"{field_name}.timing_seconds"), f"{field_name}.timing_seconds"),
        )


@dataclass(slots=True)
class InputsConfig:
    """Describe the input images and prompt text for a project."""

    source_images: list[str]
    reference_images: list[str]
    text_prompt: str
    title: TitleConfig

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "InputsConfig":
        source_images = [_as_str(item, f"{field_name}.source_images[]") for item in _expect_list(_require(data.get("source_images"), f"{field_name}.source_images"), f"{field_name}.source_images")]
        reference_images = [_as_str(item, f"{field_name}.reference_images[]") for item in _expect_list(data.get("reference_images") or [], f"{field_name}.reference_images")]
        if mode == ValidationMode.RUNTIME:
            for idx, path in enumerate(source_images):
                _check_path(path, f"{field_name}.source_images[{idx}]", mode)
            for idx, path in enumerate(reference_images):
                _check_path(path, f"{field_name}.reference_images[{idx}]", mode)
        return cls(
            source_images=source_images,
            reference_images=reference_images,
            text_prompt=_as_str(_require(data.get("text_prompt"), f"{field_name}.text_prompt"), f"{field_name}.text_prompt"),
            title=TitleConfig.from_dict(_expect_mapping(_require(data.get("title"), f"{field_name}.title"), f"{field_name}.title"), f"{field_name}.title"),
        )


@dataclass(slots=True)
class ShotDurationRange:
    """Store the allowed shot duration range used by planning."""

    min: float
    max: float

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "ShotDurationRange":
        min_value = _as_float(_require(data.get("min"), f"{field_name}.min"), f"{field_name}.min")
        max_value = _as_float(_require(data.get("max"), f"{field_name}.max"), f"{field_name}.max")
        if min_value > max_value:
            raise ConfigError(f"`{field_name}.min` must be <= `{field_name}.max`")
        return cls(min=min_value, max=max_value)


@dataclass(slots=True)
class BeatSyncConfig:
    """Describe how strongly music-first planning should align with beats."""

    enabled: bool
    align_cut_points_to_beats: bool
    prefer_section_boundaries: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "BeatSyncConfig":
        return cls(
            enabled=_as_bool(_require(data.get("enabled"), f"{field_name}.enabled"), f"{field_name}.enabled"),
            align_cut_points_to_beats=_as_bool(
                _require(data.get("align_cut_points_to_beats"), f"{field_name}.align_cut_points_to_beats"),
                f"{field_name}.align_cut_points_to_beats",
            ),
            prefer_section_boundaries=_as_bool(
                _require(data.get("prefer_section_boundaries"), f"{field_name}.prefer_section_boundaries"),
                f"{field_name}.prefer_section_boundaries",
            ),
        )


@dataclass(slots=True)
class PlanningConfig:
    """Store the planning rules that shape shot layout."""

    shot_template: str
    target_shot_count: int
    shot_duration_range: ShotDurationRange
    allow_s2v_extension: bool
    quality_profile: str | None = None
    energy_curve: list[str] = field(default_factory=list)
    energy_curve_source: str | None = None
    beat_sync: BeatSyncConfig | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "PlanningConfig":
        energy_curve = data.get("energy_curve") or []
        if not isinstance(energy_curve, list):
            raise ConfigError(f"`{field_name}.energy_curve` must be a list when provided")
        beat_sync_data = data.get("beat_sync")
        quality_profile = data.get("quality_profile")
        energy_curve_source = data.get("energy_curve_source")
        return cls(
            shot_template=_as_str(_require(data.get("shot_template"), f"{field_name}.shot_template"), f"{field_name}.shot_template"),
            target_shot_count=_as_int(_require(data.get("target_shot_count"), f"{field_name}.target_shot_count"), f"{field_name}.target_shot_count"),
            shot_duration_range=ShotDurationRange.from_dict(
                _expect_mapping(_require(data.get("shot_duration_range"), f"{field_name}.shot_duration_range"), f"{field_name}.shot_duration_range"),
                f"{field_name}.shot_duration_range",
            ),
            allow_s2v_extension=_as_bool(_require(data.get("allow_s2v_extension"), f"{field_name}.allow_s2v_extension"), f"{field_name}.allow_s2v_extension"),
            quality_profile=_as_str(quality_profile, f"{field_name}.quality_profile") if quality_profile is not None else None,
            energy_curve=[_as_str(item, f"{field_name}.energy_curve[]") for item in energy_curve],
            energy_curve_source=_as_str(energy_curve_source, f"{field_name}.energy_curve_source") if energy_curve_source is not None else None,
            beat_sync=BeatSyncConfig.from_dict(_expect_mapping(beat_sync_data, f"{field_name}.beat_sync"), f"{field_name}.beat_sync") if beat_sync_data is not None else None,
        )


@dataclass(slots=True)
class UpscaleConfig:
    """Describe the image upscaler used during post-processing."""

    enabled: bool
    model_path: str
    model_format: str
    scale: int
    apply_to: str
    fallback_method: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "UpscaleConfig":
        model_path = _as_str(_require(data.get("model_path"), f"{field_name}.model_path"), f"{field_name}.model_path")
        _check_path(model_path, f"{field_name}.model_path", mode)
        fallback_method = data.get("fallback_method")
        return cls(
            enabled=_as_bool(_require(data.get("enabled"), f"{field_name}.enabled"), f"{field_name}.enabled"),
            model_path=model_path,
            model_format=_as_str(_require(data.get("model_format"), f"{field_name}.model_format"), f"{field_name}.model_format"),
            scale=_as_int(_require(data.get("scale"), f"{field_name}.scale"), f"{field_name}.scale"),
            apply_to=_as_str(_require(data.get("apply_to"), f"{field_name}.apply_to"), f"{field_name}.apply_to"),
            fallback_method=_as_str(fallback_method, f"{field_name}.fallback_method") if fallback_method is not None else None,
        )


@dataclass(slots=True)
class FrameInterpolationConfig:
    """Describe the frame interpolation backend used after rendering."""

    enabled: bool
    engine: str
    model_path: str
    target_fps: int
    apply_after_upscale: bool
    multiplier: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "FrameInterpolationConfig":
        model_path = _as_str(_require(data.get("model_path"), f"{field_name}.model_path"), f"{field_name}.model_path")
        _check_path(model_path, f"{field_name}.model_path", mode)
        multiplier = data.get("multiplier")
        if multiplier is not None:
            multiplier = _as_int(multiplier, f"{field_name}.multiplier")
        return cls(
            enabled=_as_bool(_require(data.get("enabled"), f"{field_name}.enabled"), f"{field_name}.enabled"),
            engine=_as_str(_require(data.get("engine"), f"{field_name}.engine"), f"{field_name}.engine"),
            model_path=model_path,
            target_fps=_as_int(_require(data.get("target_fps"), f"{field_name}.target_fps"), f"{field_name}.target_fps"),
            apply_after_upscale=_as_bool(_require(data.get("apply_after_upscale"), f"{field_name}.apply_after_upscale"), f"{field_name}.apply_after_upscale"),
            multiplier=multiplier,
        )


@dataclass(slots=True)
class PostprocessConfig:
    """Group all post-processing steps for the final output."""

    upscale: UpscaleConfig
    frame_interpolation: FrameInterpolationConfig

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str, mode: ValidationMode) -> "PostprocessConfig":
        return cls(
            upscale=UpscaleConfig.from_dict(_expect_mapping(_require(data.get("upscale"), f"{field_name}.upscale"), f"{field_name}.upscale"), f"{field_name}.upscale", mode),
            frame_interpolation=FrameInterpolationConfig.from_dict(
                _expect_mapping(_require(data.get("frame_interpolation"), f"{field_name}.frame_interpolation"), f"{field_name}.frame_interpolation"),
                f"{field_name}.frame_interpolation",
                mode,
            ),
        )


@dataclass(slots=True)
class ExportConfig:
    """Store the codec choices used for the final file export."""

    video_codec: str
    audio_codec: str
    pixel_format: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "ExportConfig":
        return cls(
            video_codec=_as_str(_require(data.get("video_codec"), f"{field_name}.video_codec"), f"{field_name}.video_codec"),
            audio_codec=_as_str(_require(data.get("audio_codec"), f"{field_name}.audio_codec"), f"{field_name}.audio_codec"),
            pixel_format=_as_str(_require(data.get("pixel_format"), f"{field_name}.pixel_format"), f"{field_name}.pixel_format"),
        )


@dataclass(slots=True)
class OutputConfig:
    """Describe where outputs should be written and which manifests to keep."""

    dir: str
    save_intermediate_shots: bool
    save_last_frames: bool
    save_music_plan: bool
    save_stems: bool
    export: ExportConfig

    @classmethod
    def from_dict(cls, data: dict[str, Any], field_name: str) -> "OutputConfig":
        return cls(
            dir=_as_str(_require(data.get("dir"), f"{field_name}.dir"), f"{field_name}.dir"),
            save_intermediate_shots=_as_bool(_require(data.get("save_intermediate_shots"), f"{field_name}.save_intermediate_shots"), f"{field_name}.save_intermediate_shots"),
            save_last_frames=_as_bool(_require(data.get("save_last_frames"), f"{field_name}.save_last_frames"), f"{field_name}.save_last_frames"),
            save_music_plan=_as_bool(_require(data.get("save_music_plan"), f"{field_name}.save_music_plan"), f"{field_name}.save_music_plan"),
            save_stems=_as_bool(_require(data.get("save_stems"), f"{field_name}.save_stems"), f"{field_name}.save_stems"),
            export=ExportConfig.from_dict(_expect_mapping(_require(data.get("export"), f"{field_name}.export"), f"{field_name}.export"), f"{field_name}.export"),
        )


@dataclass(slots=True)
class AOGProjectConfig:
    """Top-level typed representation of an AOG project config."""

    project_name: str
    mode: str
    duration: float
    aspect_ratio: str
    output_format: str
    video: VideoConfig
    audio: AudioConfig
    inputs: InputsConfig
    planning: PlanningConfig
    postprocess: PostprocessConfig
    output: OutputConfig

    @classmethod
    def from_dict(cls, data: dict[str, Any], mode: ValidationMode = ValidationMode.EXAMPLE) -> "AOGProjectConfig":
        return cls(
            project_name=_as_str(_require(data.get("project_name"), "project_name"), "project_name"),
            mode=_as_str(_require(data.get("mode"), "mode"), "mode"),
            duration=_as_float(_require(data.get("duration"), "duration"), "duration"),
            aspect_ratio=_as_str(_require(data.get("aspect_ratio"), "aspect_ratio"), "aspect_ratio"),
            output_format=_as_str(_require(data.get("output_format"), "output_format"), "output_format"),
            video=VideoConfig.from_dict(_expect_mapping(_require(data.get("video"), "video"), "video"), "video", mode),
            audio=AudioConfig.from_dict(_expect_mapping(_require(data.get("audio"), "audio"), "audio"), "audio", mode),
            inputs=InputsConfig.from_dict(_expect_mapping(_require(data.get("inputs"), "inputs"), "inputs"), "inputs", mode),
            planning=PlanningConfig.from_dict(_expect_mapping(_require(data.get("planning"), "planning"), "planning"), "planning"),
            postprocess=PostprocessConfig.from_dict(_expect_mapping(_require(data.get("postprocess"), "postprocess"), "postprocess"), "postprocess", mode),
            output=OutputConfig.from_dict(_expect_mapping(_require(data.get("output"), "output"), "output"), "output"),
        )


def parse_project_config(data: dict[str, Any], mode: ValidationMode = ValidationMode.EXAMPLE) -> AOGProjectConfig:
    """
    Parse raw project config data and apply cross-field validation rules.

    Args:
        data: YAML에서 읽은 최상위 프로젝트 설정 매핑이다.
        mode: 예제 검증인지 런타임 검증인지 나타낸다.

    Returns:
        파싱과 검증을 마친 프로젝트 설정 객체다.
    """
    config = AOGProjectConfig.from_dict(data, mode=mode)
    _validate_runtime_extension_assets(config, mode)
    return config
