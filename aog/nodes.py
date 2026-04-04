"""AOG의 ComfyUI 노드 정의와 파이프라인 조립 로직."""

import json
import subprocess
from pathlib import Path

import av
import numpy as np
import torch

import comfy.model_management
import comfy.samplers
import folder_paths
import node_helpers
import nodes
from comfy_extras import nodes_audio

from .helpers import CUSTOM_NODES_DIR, audio_duration_sec, build_feature_prompt, build_llm_context, build_sfx_prompt, build_timeline, derive_semantic_cues, ensure_audio_dict, infer_song_sections, load_module_from_path, make_silent_audio, mix_audio_dicts, normalize_audio_duration, summarize_conditioning_payload, summarize_video_frames, to_pretty_json
from .llm import generate_lyrics, generate_music_plan, generate_prompt, generate_sfx_prompt

LANGUAGE_LABELS = {
    "ja": "Japanese",
    "ko": "Korean",
    "en": "English",
    "zh": "Chinese",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
    "pt": "Portuguese",
    "ru": "Russian",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "cs": "Czech",
    "fa": "Persian",
    "id": "Indonesian",
    "uk": "Ukrainian",
    "hu": "Hungarian",
    "ar": "Arabic",
    "sv": "Swedish",
    "ro": "Romanian",
    "el": "Greek",
}

VHS_FORMAT_ALIASES = {
    "video/mp4": "video/h264-mp4",
    "video/webm": "video/webm",
    "image/gif": "image/gif",
    "image/webp": "image/webp",
}

QUALITY_PRESET_CHOICES = ["fast", "balanced", "high"]
QUALITY_PRESETS = {
    "fast": {
        "ace_steps": 6,
        "ace_cfg": 1.0,
        "text_cfg_scale": 4.5,
        "sfx_steps": 6,
        "sfx_cfg": 3.0,
        "qwenvl_frame_count": 6,
        "qwenvl_max_tokens": 384,
        "qwenvl_temperature": 0.35,
    },
    "balanced": {
        "ace_steps": 8,
        "ace_cfg": 1.0,
        "text_cfg_scale": 5.0,
        "sfx_steps": 8,
        "sfx_cfg": 3.5,
        "qwenvl_frame_count": 8,
        "qwenvl_max_tokens": 512,
        "qwenvl_temperature": 0.4,
    },
    "high": {
        "ace_steps": 12,
        "ace_cfg": 1.2,
        "text_cfg_scale": 5.5,
        "sfx_steps": 12,
        "sfx_cfg": 4.0,
        "qwenvl_frame_count": 12,
        "qwenvl_max_tokens": 768,
        "qwenvl_temperature": 0.45,
    },
}


def _normalize_timesignature(value):
    """박자 표기를 ACE-Step 허용값으로 정규화한다."""
    text = str(value).strip()
    if text in {"2", "3", "4", "6"}:
        return text
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits in {"2", "3", "4", "6"}:
        return digits
    return text


def _normalize_language_choice(value):
    """언어 코드를 소문자 기준 canonical 값으로 정규화한다."""
    text = str(value).strip().lower()
    if text in LANGUAGE_CHOICES:
        return text
    return text


def _normalize_keyscale_choice(value):
    """조성 표기를 ACE-Step 허용 형식으로 정규화한다."""
    text = " ".join(str(value).strip().split())
    if not text:
        return text
    lowered = text.lower()
    alias_map = {
        "c major": "C major",
        "c# major": "C# major",
        "db major": "Db major",
        "d major": "D major",
        "d# major": "D# major",
        "eb major": "Eb major",
        "e major": "E major",
        "f major": "F major",
        "f# major": "F# major",
        "gb major": "Gb major",
        "g major": "G major",
        "g# major": "G# major",
        "ab major": "Ab major",
        "a major": "A major",
        "a# major": "A# major",
        "bb major": "Bb major",
        "b major": "B major",
        "c minor": "C minor",
        "c# minor": "C# minor",
        "db minor": "Db minor",
        "d minor": "D minor",
        "d# minor": "D# minor",
        "eb minor": "Eb minor",
        "e minor": "E minor",
        "f minor": "F minor",
        "f# minor": "F# minor",
        "gb minor": "Gb minor",
        "g minor": "G minor",
        "g# minor": "G# minor",
        "ab minor": "Ab minor",
        "a minor": "A minor",
        "a# minor": "A# minor",
        "bb minor": "Bb minor",
        "b minor": "B minor",
    }
    return alias_map.get(lowered, text)


def _resolve_quality_settings(quality_profile, apply_quality_profile, steps, cfg, text_cfg_scale, sfx_steps, sfx_cfg, qwenvl_bundle):
    """품질 프리셋 적용 여부에 따라 실제 샘플링 설정을 계산한다."""
    if not apply_quality_profile:
        return {
            "steps": int(steps),
            "cfg": float(cfg),
            "text_cfg_scale": float(text_cfg_scale),
            "sfx_steps": int(sfx_steps),
            "sfx_cfg": float(sfx_cfg),
            "qwenvl_bundle": dict(qwenvl_bundle) if qwenvl_bundle is not None else None,
            "quality_profile": quality_profile,
            "apply_quality_profile": False,
        }
    preset = QUALITY_PRESETS[quality_profile]
    resolved_bundle = dict(qwenvl_bundle) if qwenvl_bundle is not None else None
    if resolved_bundle is not None:
        resolved_bundle["frame_count"] = int(preset["qwenvl_frame_count"])
        resolved_bundle["max_tokens"] = int(preset["qwenvl_max_tokens"])
        resolved_bundle["temperature"] = float(preset["qwenvl_temperature"])
    return {
        "steps": int(preset["ace_steps"]),
        "cfg": float(preset["ace_cfg"]),
        "text_cfg_scale": float(preset["text_cfg_scale"]),
        "sfx_steps": int(preset["sfx_steps"]),
        "sfx_cfg": float(preset["sfx_cfg"]),
        "qwenvl_bundle": resolved_bundle,
        "quality_profile": quality_profile,
        "apply_quality_profile": True,
    }



def _build_video_features_without_mmaudio(video_batch):
    """MMAudio를 끈 경우에도 authoring에 필요한 기본 영상 특징을 생성한다."""
    images = video_batch["images"]
    source_duration = float(video_batch.get("source_duration_sec", video_batch.get("duration_sec", 0.0)))
    fps = float(video_batch.get("fps", 0.0))
    if source_duration <= 0:
        source_duration = int(video_batch.get("frame_count", images.shape[0])) / fps if fps > 0 else 0.0
    summary = summarize_video_frames(images, source_duration)
    timeline = build_timeline(images, source_duration, segment_count=8)
    semantic_cues = derive_semantic_cues(summary, timeline)
    conditioning_summary = {
        "mmaudio_enabled": False,
        "requested_duration_sec": float(source_duration),
        "mmaudio_condition_duration_sec": 0.0,
        "source_duration_sec": float(source_duration),
        "loaded_duration_sec": float(video_batch.get("loaded_duration_sec", source_duration)),
        "duration_preserved": True,
    }
    latent_structure_cues = [
        "mmaudio feature extraction disabled",
        f"song sections: {', '.join(infer_song_sections(summary['duration_sec']))}",
    ]
    if timeline:
        peak_segment = max(timeline, key=lambda item: item["motion_mean"])
        latent_structure_cues.append(f"highest kinetic emphasis near {peak_segment['start_sec']:.2f}-{peak_segment['end_sec']:.2f}s")
    return {
        "summary": summary,
        "timeline": timeline,
        "semantic_cues": semantic_cues,
        "conditioning_summary": conditioning_summary,
        "latent_structure_cues": latent_structure_cues,
        "duration_sec": float(source_duration),
        "source_duration_sec": float(source_duration),
        "loaded_duration_sec": float(video_batch.get("loaded_duration_sec", source_duration)),
        "mmaudio_condition_duration_sec": 0.0,
        "frame_count": int(video_batch.get("frame_count", images.shape[0])),
        "fps": float(video_batch.get("fps", 0.0)),
        "source_fps": float(video_batch.get("source_fps", video_batch.get("fps", 0.0))),
        "loaded_fps": float(video_batch.get("loaded_fps", video_batch.get("fps", 0.0))),
        "source_path": str(video_batch.get("source_path", "")),
        "feature_contract": "summary + timeline + semantic cues without mmaudio conditioning payload",
        "analysis_only": True,
    }


def _generate_qwenvl_authoring_text(video_batch, video_features, qwenvl_bundle, authoring_language, custom_prompt):
    """QwenVL을 호출해 프롬프트/가사/메타 계획용 텍스트를 생성한다."""
    qwen_module = load_module_from_path("aog_ext_qwenvl_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-QwenVL" / "AILab_QwenVL.py"))
    response = qwen_module.AILab_QwenVL_Advanced().process(
        model_name=qwenvl_bundle["model_name"],
        quantization=qwenvl_bundle["quantization"],
        attention_mode=qwenvl_bundle["attention_mode"],
        use_torch_compile=False,
        device="auto",
        preset_prompt="Describe this image in detail.",
        custom_prompt=custom_prompt,
        max_tokens=qwenvl_bundle["max_tokens"],
        temperature=qwenvl_bundle["temperature"],
        top_p=qwenvl_bundle["top_p"],
        num_beams=qwenvl_bundle["num_beams"],
        repetition_penalty=qwenvl_bundle["repetition_penalty"],
        frame_count=qwenvl_bundle["frame_count"],
        keep_model_loaded=qwenvl_bundle["keep_model_loaded"],
        seed=qwenvl_bundle["seed"],
        image=None,
        video=video_batch["images"],
    )[0].strip()
    return response, {
        "provider": "qwenvl",
        "mode": "llm",
        "model": qwenvl_bundle["model_name"],
        "request": {
            "authoring_language": authoring_language,
            "custom_prompt": custom_prompt,
            "frame_count": int(qwenvl_bundle["frame_count"]),
            "max_tokens": int(qwenvl_bundle["max_tokens"]),
            "temperature": float(qwenvl_bundle["temperature"]),
            "top_p": float(qwenvl_bundle["top_p"]),
            "num_beams": int(qwenvl_bundle["num_beams"]),
            "repetition_penalty": float(qwenvl_bundle["repetition_penalty"]),
        },
        "response": response,
        "context": build_llm_context(video_features),
    }


def _draft_prompt_with_qwenvl(video_batch, video_features, qwenvl_bundle, authoring_language):
    """QwenVL로 영상 분석 기반 ACE-Step 프롬프트를 작성한다."""
    context = build_llm_context(video_features)
    custom_prompt = (
        f"You are writing an ACE-Step music prompt for an anime opening. Respond only in {authoring_language}. "
        "Return plain text only, with no markdown, no bullet list, and no explanation. "
        "Use the video itself plus the structured context below. Write a concise, vivid music-generation prompt describing instrumentation, pacing, rises, drops, emotional arc, transitions, and hook moments that fit this opening exactly.\n\n"
        f"Structured context: {json.dumps(context, ensure_ascii=False)}"
    )
    return _generate_qwenvl_authoring_text(video_batch, video_features, qwenvl_bundle, authoring_language, custom_prompt)


def _draft_lyrics_with_qwenvl(video_batch, video_features, qwenvl_bundle, authoring_language, lyrics_language):
    """QwenVL로 영상 분석 기반 ACE-Step 가사를 작성한다."""
    context = build_llm_context(video_features)
    custom_prompt = (
        f"You are writing singable ACE-Step lyrics for an anime opening. Respond only in {lyrics_language}. "
        "Return plain text only. Use section labels like [Verse], [Pre-Chorus], [Chorus]. "
        "Match the video's pacing, turning points, climactic rise, and visible motifs. "
        "Do not explain your reasoning. Every lyric line must be written in the requested lyrics language. "
        "Do not switch languages. Do not translate the title unless needed inside a lyric line.\n\n"
        f"Authoring language: {authoring_language}\n"
        f"Lyrics language: {lyrics_language}\n"
        f"Structured context: {json.dumps(context, ensure_ascii=False)}"
    )
    return _generate_qwenvl_authoring_text(video_batch, video_features, qwenvl_bundle, lyrics_language, custom_prompt)


def _draft_music_plan_with_qwenvl(video_batch, video_features, qwenvl_bundle, authoring_language, lyrics_language):
    """QwenVL로 BPM, 박자, 조성, 가창 언어를 JSON 형태로 계획한다."""
    context = build_llm_context(video_features)
    custom_prompt = (
        "You are planning ACE-Step music metadata for an anime opening. "
        "Return JSON only with keys: bpm, timesignature, keyscale, ace_language, rationale. "
        "bpm must be an integer from 60 to 210. "
        "timesignature must be one of 2, 3, 4, 6 as a string. "
        "keyscale must be a common major/minor key such as A minor or C major. "
        "ace_language must be the singing language and should normally match the requested lyrics language.\n\n"
        f"Authoring language: {authoring_language}\n"
        f"Requested lyrics language: {lyrics_language}\n"
        f"Structured context: {json.dumps(context, ensure_ascii=False)}"
    )
    text, info = _generate_qwenvl_authoring_text(video_batch, video_features, qwenvl_bundle, authoring_language, custom_prompt)
    decoder = json.JSONDecoder()
    start = text.find("{")
    if start < 0:
        raise ValueError("QwenVL music plan did not return a JSON object.")
    try:
        payload, _ = decoder.raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse QwenVL music plan JSON: {exc}") from exc
    plan = {
        "bpm": int(payload["bpm"]),
        "timesignature": str(payload["timesignature"]),
        "keyscale": str(payload["keyscale"]),
        "ace_language": str(payload.get("ace_language") or lyrics_language),
        "rationale": str(payload.get("rationale", "")).strip(),
    }
    info.update({"response_json": payload})
    return plan, info


def _inject_scene_analysis(video_features, scene_analysis):
    if not scene_analysis:
        return video_features
    enriched = dict(video_features)
    enriched["qwenvl_scene_analysis"] = str(scene_analysis).strip()
    return enriched


def _draft_sfx_prompt_with_qwenvl(video_batch, video_features, qwenvl_bundle, authoring_language):
    """QwenVL로 영상에 맞는 MMAudio SFX 프롬프트를 작성한다.

    Args:
        video_batch: AOG 비디오 배치.
        video_features: AOG 비디오 특징 계약.
        qwenvl_bundle: 로드된 QwenVL 설정 번들.
        authoring_language: 분석 및 작성 언어.

    Returns:
        `(sfx_prompt, info)` 튜플.
    """
    context = build_llm_context(video_features)
    custom_prompt = (
        f"You are writing an MMAudio SFX prompt for an anime opening. Respond only in {authoring_language}. "
        "Return plain text only, with no markdown, no bullet list, and no explanation. "
        "Describe motion-synced whooshes, risers, impacts, swells, transition hits, accent cues, and scene-change effects. "
        "Do not ask for a full music bed. Do not include vocals or dialogue.\n\n"
        f"Structured context: {json.dumps(context, ensure_ascii=False)}"
    )
    return _generate_qwenvl_authoring_text(video_batch, video_features, qwenvl_bundle, authoring_language, custom_prompt)


def _draft_sfx_prompt_with_qwenvl(video_batch, video_features, qwenvl_bundle, authoring_language):
    """QwenVL로 영상 기반 MMAudio SFX 프롬프트를 생성한다."""
    context = build_llm_context(video_features)
    custom_prompt = (
        f"You are writing an MMAudio SFX prompt for an anime opening. Respond only in {authoring_language}. "
        "Return plain text only, with no markdown and no explanation. "
        "Describe only cinematic sound-design layers such as whooshes, risers, impacts, transition swells, motion accents, "
        "camera-move sweeps, and visual hit punctuations. Do not describe vocals, dialogue, or the main background music.\n\n"
        f"Structured context: {json.dumps(context, ensure_ascii=False)}"
    )
    return _generate_qwenvl_authoring_text(video_batch, video_features, qwenvl_bundle, authoring_language, custom_prompt)

LANGUAGE_CHOICES = ["en", "ja", "zh", "es", "de", "fr", "pt", "ru", "it", "nl", "pl", "tr", "vi", "cs", "fa", "id", "ko", "uk", "hu", "ar", "sv", "ro", "el"]
KEYSCALE_CHOICES = [f"{root} {quality}" for quality in ["major", "minor"] for root in ["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"]]


def _save_audio_to_wav(audio, output_path):
    """AUDIO payload를 임시 WAV 파일로 저장한다."""
    import wave
    waveform = audio["waveform"][0].detach().cpu().numpy()
    if waveform.ndim == 1:
        waveform = waveform[np.newaxis, :]
    pcm16 = (np.clip(waveform, -1.0, 1.0).T * 32767.0).astype(np.int16, copy=False)
    channels = int(pcm16.shape[1]) if pcm16.ndim == 2 else 1
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(audio["sample_rate"]))
        wav_file.writeframes(pcm16.tobytes())


class AOGMMAudioFeatureBundle:
    """MMAudio 특징 추출기에 필요한 VAE/Sync/CLIP 묶음을 로드한다."""
    @classmethod
    def INPUT_TYPES(cls):
        choices = folder_paths.get_filename_list("mmaudio")
        return {
            "required": {
                "vae_model": (choices, {"default": "mmaudio_vae_44k_fp16.safetensors"}),
                "synchformer_model": (choices, {"default": "mmaudio_synchformer_fp16.safetensors"}),
                "clip_model": (choices, {"default": "apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors"}),
                "mode": (["16k", "44k"], {"default": "44k"}),
                "precision": (["fp16", "fp32", "bf16"], {"default": "fp16"}),
            }
        }

    RETURN_TYPES = ("MMAUDIO_FEATUREUTILS",)
    RETURN_NAMES = ("mmaudio_featureutils",)
    FUNCTION = "load_bundle"
    CATEGORY = "AOG/Audio"

    def load_bundle(self, vae_model, synchformer_model, clip_model, mode="44k", precision="fp16"):

        """MMAudio ?? ??? ?? ??? ????.

        

                Args:

                    vae_model: MMAudio VAE ????? ???.

                    synchformer_model: SyncFormer ????? ???.

                    clip_model: CLIP ?? ????? ???.

                    mode: ????? ??.

                    precision: ?? ???.

        

                Returns:

                    MMAudio ?? ??? ??? `MMAUDIO_FEATUREUTILS` ?? ??."""
        mmaudio_nodes = load_module_from_path("aog_ext_mmaudio_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-MMAudio" / "nodes.py"))
        return mmaudio_nodes.MMAudioFeatureUtilsLoader().loadmodel(vae_model=vae_model, precision=precision, synchformer_model=synchformer_model, clip_model=clip_model, mode=mode)


class AOGMMAudioSFXBundle:
    """MMAudio SFX 생성 모델 묶음을 로드한다."""
    @classmethod
    def INPUT_TYPES(cls):
        mmaudio_nodes = load_module_from_path("aog_ext_mmaudio_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-MMAudio" / "nodes.py"))
        return mmaudio_nodes.MMAudioModelLoader.INPUT_TYPES()

    RETURN_TYPES = ("MMAUDIO_MODEL",)
    RETURN_NAMES = ("mmaudio_model",)
    FUNCTION = "load_bundle"
    CATEGORY = "AOG/Audio"

    def load_bundle(self, mmaudio_model, base_precision="fp16"):

        """MMAudio SFX ??? ??? ????.

        

                Args:

                    mmaudio_model: SFX ??? MMAudio ????? ???.

                    base_precision: ?? ???.

        

                Returns:

                    SFX ??? ??? `MMAUDIO_MODEL` ?? ??."""
        mmaudio_nodes = load_module_from_path("aog_ext_mmaudio_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-MMAudio" / "nodes.py"))
        return mmaudio_nodes.MMAudioModelLoader().loadmodel(mmaudio_model=mmaudio_model, base_precision=base_precision)


class AOGQwenVLBundle:
    """QwenVL 분석에 필요한 모델 설정 묶음을 만든다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_name": ("STRING", {"default": "Qwen3-VL-4B-Instruct", "multiline": False}),
                "quantization": (["None (FP16)", "8-bit (Balanced)", "4-bit (VRAM-friendly)"], {"default": "None (FP16)"}),
                "attention_mode": (["auto", "sage", "flash_attention_2", "sdpa"], {"default": "auto"}),
                "frame_count": ("INT", {"default": 16, "min": 1, "max": 64}),
                "max_tokens": ("INT", {"default": 512, "min": 64, "max": 4096}),
                "temperature": ("FLOAT", {"default": 0.4, "min": 0.0, "max": 1.0, "step": 0.05}),
                "top_p": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.05}),
                "num_beams": ("INT", {"default": 1, "min": 1, "max": 8}),
                "repetition_penalty": ("FLOAT", {"default": 1.1, "min": 0.5, "max": 2.0, "step": 0.05}),
                "keep_model_loaded": ("BOOLEAN", {"default": True}),
                "seed": ("INT", {"default": 1, "min": 1, "max": 2**32 - 1}),
            }
        }

    RETURN_TYPES = ("AOG_QWENVL_BUNDLE",)
    RETURN_NAMES = ("qwenvl_bundle",)
    FUNCTION = "load_bundle"
    CATEGORY = "AOG/Authoring"

    def load_bundle(self, model_name, quantization, attention_mode, frame_count, max_tokens, temperature, top_p, num_beams, repetition_penalty, keep_model_loaded, seed):

        """QwenVL ?? ??? ??? ??? ???.

        

                Args:

                    model_name: ??? QwenVL ?? ??.

                    quantization: ??? ??.

                    attention_mode: ??? ?? ??.

                    frame_count: ??? ??? ??? ?.

                    max_tokens: ?? ?? ?? ?.

                    temperature: ??? ??.

                    top_p: nucleus sampling ??.

                    num_beams: beam search ??.

                    repetition_penalty: ?? ?? ??.

                    keep_model_loaded: ?? ? ?? ?? ??.

                    seed: ?? ??.

        

                Returns:

                    QwenVL ?? ???? ??."""
        return ({
            "model_name": model_name,
            "quantization": quantization,
            "attention_mode": attention_mode,
            "frame_count": int(frame_count),
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
            "top_p": float(top_p),
            "num_beams": int(num_beams),
            "repetition_penalty": float(repetition_penalty),
            "keep_model_loaded": bool(keep_model_loaded),
            "seed": int(seed),
        },)


class AOGQualityPreset:
    """빠름/균형/고품질 프리셋을 실제 샘플링 파라미터로 변환한다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "quality_profile": (QUALITY_PRESET_CHOICES, {"default": "balanced"}),
                "apply_quality_profile": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("AOG_QUALITY_SETTINGS", "INT", "FLOAT", "FLOAT", "INT", "FLOAT", "STRING")
    RETURN_NAMES = ("quality_settings", "ace_steps", "ace_cfg", "text_cfg_scale", "sfx_steps", "sfx_cfg", "summary_json")
    FUNCTION = "build"
    CATEGORY = "AOG/Config"

    def build(self, quality_profile, apply_quality_profile):

        """?? ??? ??? payload? ???.

        

                Args:

                    quality_profile: fast, balanced, high ? ??.

                    apply_quality_profile: ??? ?? ?? ??.

        

                Returns:

                    ?? payload? ?? ???, ?? JSON."""
        payload = {
            "quality_profile": quality_profile,
            "apply_quality_profile": bool(apply_quality_profile),
            "preset_values": dict(QUALITY_PRESETS[quality_profile]),
        }
        return (
            payload,
            int(payload["preset_values"]["ace_steps"]),
            float(payload["preset_values"]["ace_cfg"]),
            float(payload["preset_values"]["text_cfg_scale"]),
            int(payload["preset_values"]["sfx_steps"]),
            float(payload["preset_values"]["sfx_cfg"]),
            to_pretty_json(payload),
        )


class AOGLoadVideoFrames:
    """파일 경로 기반으로 비디오 프레임과 메타데이터를 읽어온다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {"default": "", "multiline": False}),
                "max_frames": ("INT", {"default": 0, "min": 0, "max": 100000}),
                "force_rate": ("FLOAT", {"default": 25.0, "min": 0.0, "step": 1.0}),
                "analysis_width": ("INT", {"default": 640, "min": 0, "max": 4096, "step": 8}),
            }
        }

    RETURN_TYPES = ("AOG_VIDEO_BATCH", "IMAGE", "STRING")
    RETURN_NAMES = ("video_batch", "images", "summary_json")
    FUNCTION = "load_video"
    CATEGORY = "AOG/Video"

    def load_video(self, video_path, max_frames, force_rate, analysis_width):

        """??? ??? ?? AOG ??? ??? ????.

        

                Args:

                    video_path: ?? ??? ??.

                    max_frames: ?? ??? ?. 0?? ?? ??.

                    force_rate: ?? FPS. 0?? ?? FPS ??.

                    analysis_width: ??? ???? ??.

        

                Returns:

                    `(video_batch, images, summary_json)` ??."""
        if not video_path.strip():
            raise ValueError("video_path is required.")
        frames = []
        source_fps = 0.0
        source_duration_sec = 0.0
        with av.open(video_path) as container:
            stream = container.streams.video[0]
            if stream.average_rate is not None:
                source_fps = float(stream.average_rate)
            if stream.duration is not None and stream.time_base is not None:
                source_duration_sec = float(stream.duration * stream.time_base)
            for frame in container.decode(stream):
                frames.append(torch.from_numpy(frame.to_ndarray(format="rgb24").astype(np.float32) / 255.0))
        if not frames:
            raise ValueError(f"No frames decoded from {video_path}")
        if source_fps <= 0:
            source_fps = 25.0
        if source_duration_sec <= 0:
            source_duration_sec = float(len(frames) / source_fps)
        source_frame_count = len(frames)
        target_fps = float(force_rate) if force_rate > 0 else source_fps
        if target_fps <= 0:
            target_fps = source_fps
        target_frame_count = max(1, int(round(source_duration_sec * target_fps)))
        if max_frames > 0:
            target_frame_count = min(target_frame_count, int(max_frames))
        if target_frame_count == source_frame_count:
            images = torch.stack(frames, dim=0)
        else:
            frame_positions = np.linspace(0, source_frame_count - 1, num=target_frame_count)
            sampled = [frames[min(source_frame_count - 1, int(round(position)))] for position in frame_positions]
            images = torch.stack(sampled, dim=0)
        if analysis_width > 0 and images.shape[2] > analysis_width:
            scale = float(analysis_width / images.shape[2])
            analysis_height = max(8, int(round(images.shape[1] * scale / 8.0) * 8))
            images_nchw = images.permute(0, 3, 1, 2)
            images_nchw = torch.nn.functional.interpolate(images_nchw, size=(analysis_height, int(analysis_width)), mode="bilinear", align_corners=False)
            images = images_nchw.permute(0, 2, 3, 1).contiguous()
        frame_count = int(images.shape[0])
        loaded_duration_sec = float(frame_count / target_fps) if target_fps > 0 else source_duration_sec
        video_batch = {
            "images": images,
            "frame_count": int(frame_count),
            "fps": float(target_fps),
            "duration_sec": float(loaded_duration_sec),
            "source_fps": float(source_fps),
            "source_duration_sec": float(source_duration_sec),
            "loaded_fps": float(target_fps),
            "loaded_duration_sec": float(loaded_duration_sec),
            "source_path": video_path,
            "video_info": {
                "source_fps": float(source_fps),
                "source_frame_count": int(source_frame_count),
                "source_duration": float(source_duration_sec),
                "source_width": int(images.shape[2]),
                "source_height": int(images.shape[1]),
                "loaded_fps": float(target_fps),
                "loaded_frame_count": int(frame_count),
                "loaded_duration": float(loaded_duration_sec),
                "loaded_width": int(images.shape[2]),
                "loaded_height": int(images.shape[1]),
            },
        }
        return (
            video_batch,
            images,
            to_pretty_json(
                {
                    "source_path": video_path,
                    "frame_count": int(frame_count),
                    "source_fps": float(source_fps),
                    "source_duration_sec": float(source_duration_sec),
                    "loaded_fps": float(target_fps),
                    "loaded_duration_sec": float(loaded_duration_sec),
                    "height": int(images.shape[1]),
                    "width": int(images.shape[2]),
                }
            ),
        )


class AOGWorkflowVideoBatchAdapter:
    """워크플로우 내 raw 출력들을 AOG_VIDEO_BATCH 계약으로 묶는다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",), "fps": ("FLOAT", {"default": 8.0, "min": 0.1, "step": 0.1}), "source_path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = ("AOG_VIDEO_BATCH", "STRING")
    RETURN_NAMES = ("video_batch", "summary_json")
    FUNCTION = "adapt"
    CATEGORY = "AOG/Video"

    def adapt(self, images, fps, source_path):

        """?? ?????? ??? ??? AOG ??? ??? ???.

        

                Args:

                    images: ??? ??? ??.

                    fps: ??? ???.

                    source_path: ?? ??? ?? ?? ???.

        

                Returns:

                    `(video_batch, summary_json)` ??."""
        frame_count = int(images.shape[0])
        duration_sec = float(frame_count / fps) if fps > 0 else 0.0
        batch = {
            "images": images,
            "frame_count": frame_count,
            "fps": float(fps),
            "duration_sec": duration_sec,
            "source_fps": float(fps),
            "source_duration_sec": duration_sec,
            "loaded_fps": float(fps),
            "loaded_duration_sec": duration_sec,
            "source_path": source_path.strip(),
        }
        return (
            batch,
            to_pretty_json(
                {
                    "source_path": source_path.strip(),
                    "frame_count": frame_count,
                    "fps": float(fps),
                    "duration_sec": duration_sec,
                    "contract": "external SVI workflow output adapted for AOG music generation",
                }
            ),
        )


class AOGVHSVideoBatchAdapter:
    """VHS_LoadVideo 출력을 AOG_VIDEO_BATCH 계약으로 변환한다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "frame_count": ("INT", {"default": 1, "min": 1}),
                "video_info": ("VHS_VIDEOINFO",),
            },
        }

    RETURN_TYPES = ("AOG_VIDEO_BATCH", "STRING")
    RETURN_NAMES = ("video_batch", "summary_json")
    FUNCTION = "adapt"
    CATEGORY = "AOG/Video"

    def adapt(self, images, frame_count, video_info):

        """VHS ??? ??? AOG ??? ??? ????.

        

                Args:

                    images: VHS? ??? ??? ??.

                    frame_count: ??? ?.

                    video_info: VHS ????? ????.

        

                Returns:

                    `(video_batch, summary_json)` ??."""
        resolved_source_path = str(video_info.get("source_path", "")).strip() or "[uploaded via VHS_LoadVideo]"
        source_fps = float(video_info.get("source_fps", 0.0))
        source_duration = float(video_info.get("source_duration", 0.0))
        loaded_fps = float(video_info.get("loaded_fps", source_fps if source_fps > 0 else 0.0))
        loaded_duration = float(video_info.get("loaded_duration", 0.0))
        if loaded_fps <= 0:
            loaded_fps = float(frame_count / loaded_duration) if loaded_duration > 0 else 8.0
        if loaded_duration <= 0:
            loaded_duration = float(frame_count / loaded_fps) if loaded_fps > 0 else 0.0
        if source_fps <= 0:
            source_fps = loaded_fps
        if source_duration <= 0:
            source_duration = loaded_duration
        batch = {
            "images": images,
            "frame_count": int(frame_count),
            "fps": loaded_fps,
            "duration_sec": loaded_duration,
            "source_fps": source_fps,
            "source_duration_sec": source_duration,
            "loaded_fps": loaded_fps,
            "loaded_duration_sec": loaded_duration,
            "source_path": resolved_source_path,
            "video_info": dict(video_info),
        }
        summary = {
            "source_path": resolved_source_path,
            "frame_count": int(frame_count),
            "source_fps": source_fps,
            "source_duration_sec": source_duration,
            "loaded_fps": loaded_fps,
            "loaded_duration_sec": loaded_duration,
            "contract": "VHS upload/path video adapted for AOG full-duration music generation",
        }
        return (batch, to_pretty_json(summary))


class AOGVideoFeatureExtract:
    """영상에서 MMAudio 특징과 요약/타임라인/구조 cue를 추출한다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_batch": ("AOG_VIDEO_BATCH",),
                "mmaudio_featureutils": ("MMAUDIO_FEATUREUTILS",),
                "mask_away_clip": ("BOOLEAN", {"default": False}),
            },
                    }

    RETURN_TYPES = ("AOG_VIDEO_FEATURES", "STRING")
    RETURN_NAMES = ("video_features", "summary_json")
    FUNCTION = "extract_features"
    CATEGORY = "AOG/Audio"

    def extract_features(self, video_batch, mmaudio_featureutils, mask_away_clip):

        """???? authoring? SFX? ??? ??? ??? ????.

        

                Args:

                    video_batch: ?? ??? ??.

                    mmaudio_featureutils: MMAudio ?? ?? ????.

                    mask_away_clip: CLIP branch ?? ?? ??.


        

                Returns:

                    `(video_features, summary_json)` ??."""
        images = video_batch["images"]
        mmaudio_nodes = load_module_from_path("aog_ext_mmaudio_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-MMAudio" / "nodes.py"))
        source_duration = float(video_batch.get("source_duration_sec", video_batch.get("duration_sec", 0.0)))
        loaded_duration = float(video_batch.get("loaded_duration_sec", video_batch.get("duration_sec", 0.0)))
        requested_duration = loaded_duration
        if requested_duration <= 0:
            fps = float(video_batch.get("fps", 0.0))
            requested_duration = int(video_batch.get("frame_count", images.shape[0])) / fps if fps > 0 else 0.0
        if requested_duration <= 0:
            raise ValueError("Video duration could not be resolved.")
        clip_frames, sync_frames, adjusted_duration = mmaudio_nodes.process_video_tensor(images, requested_duration)
        device = comfy.model_management.get_torch_device()
        feature_dtype = getattr(mmaudio_featureutils, "dtype", torch.float32)
        clip_batch = None if mask_away_clip else clip_frames.unsqueeze(0).to(device=device, dtype=feature_dtype)
        sync_batch = sync_frames.unsqueeze(0).to(device=device, dtype=feature_dtype)
        clip_features = None
        sync_features = None
        try:
            mmaudio_featureutils.to(device)
            with torch.no_grad():
                if clip_batch is not None:
                    clip_features = mmaudio_featureutils.encode_video_with_clip(clip_batch).detach().cpu()
                sync_features = mmaudio_featureutils.encode_video_with_sync(sync_batch).detach().cpu()
        finally:
            del clip_batch, sync_batch
            # 특징 추출이 끝난 뒤에는 바로 오프로딩해서 VRAM 점유를 줄인다.
            mmaudio_featureutils.to(comfy.model_management.unet_offload_device())
            comfy.model_management.soft_empty_cache()
        summary = summarize_video_frames(images, source_duration if source_duration > 0 else requested_duration)
        timeline = build_timeline(images, source_duration if source_duration > 0 else requested_duration, segment_count=8)
        semantic_cues = derive_semantic_cues(summary, timeline)
        conditioning_summary = summarize_conditioning_payload(clip_features, sync_features)
        conditioning_summary["mmaudio_enabled"] = True
        conditioning_summary["requested_duration_sec"] = float(requested_duration)
        conditioning_summary["mmaudio_condition_duration_sec"] = float(adjusted_duration)
        conditioning_summary["source_duration_sec"] = float(source_duration)
        conditioning_summary["loaded_duration_sec"] = float(loaded_duration)
        conditioning_summary["duration_preserved"] = bool(abs((source_duration or requested_duration) - adjusted_duration) < 0.05)
        latent_structure_cues = [
            "conditioning payload reserved for future direct music-model integration",
            f"song sections: {', '.join(infer_song_sections(summary['duration_sec']))}",
            f"loaded video duration {loaded_duration:.2f}s",
            f"mmaudio conditioning span {adjusted_duration:.2f}s",
        ]
        if timeline:
            peak_segment = max(timeline, key=lambda item: item["motion_mean"])
            latent_structure_cues.append(f"highest kinetic emphasis near {peak_segment['start_sec']:.2f}-{peak_segment['end_sec']:.2f}s")
        export_payload = {
            "summary": summary,
            "timeline": timeline,
            "semantic_cues": semantic_cues,
            "conditioning_summary": conditioning_summary,
            "latent_structure_cues": latent_structure_cues,
            "duration_sec": float(source_duration if source_duration > 0 else adjusted_duration),
            "source_duration_sec": float(source_duration if source_duration > 0 else adjusted_duration),
            "loaded_duration_sec": float(loaded_duration),
            "mmaudio_condition_duration_sec": float(adjusted_duration),
            "frame_count": int(video_batch.get("frame_count", images.shape[0])),
            "fps": float(video_batch.get("fps", 0.0)),
            "source_fps": float(video_batch.get("source_fps", video_batch.get("fps", 0.0))),
            "loaded_fps": float(video_batch.get("loaded_fps", video_batch.get("fps", 0.0))),
            "source_path": str(video_batch.get("source_path", "")),
            "feature_contract": "rich summary + timeline + semantic cues + conditioning payload summary only",
            "analysis_only": True,
        }
        return (export_payload, to_pretty_json(export_payload))


class AOGQwenVLSemanticExtract:
    """QwenVL로 장면 설명, 카메라, 분위기 같은 의미 분석을 수행한다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_batch": ("AOG_VIDEO_BATCH",),
                "qwenvl_bundle": ("AOG_QWENVL_BUNDLE",),
                "authoring_language": (LANGUAGE_CHOICES, {"default": "en"}),
                "analysis_prompt": ("STRING", {"multiline": True, "default": ""}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("scene_analysis", "summary_json")
    FUNCTION = "extract"
    CATEGORY = "AOG/Authoring"

    def extract(self, video_batch, qwenvl_bundle, authoring_language, analysis_prompt):

        """QwenVL? ?? ?? ??? ????.

        

                Args:

                    video_batch: ?? ??? ??.

                    qwenvl_bundle: QwenVL ?? ??.

                    authoring_language: ?? ?? ??.

                    analysis_prompt: ??? ?? ?? ????.

        

                Returns:

                    `(scene_analysis, summary_json)` ??."""
        qwen_module = load_module_from_path("aog_ext_qwenvl_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-QwenVL" / "AILab_QwenVL.py"))
        # QwenVL은 비디오 프레임 시퀀스를 직접 받아 장면 의미를 분석한다.
        video = video_batch["images"]
        prompt = analysis_prompt.strip() or (
            f"Analyze this opening video and respond only in {authoring_language}. "
            "Describe the visible actions, camera motion, pacing changes, scene transitions, emotional arc, repeating motifs, and moments that should influence song structure, lyrics, and opening music prompt writing. "
            "Be concrete and concise. Do not use any other language."
        )
        response = qwen_module.AILab_QwenVL_Advanced().process(
            model_name=qwenvl_bundle["model_name"],
            quantization=qwenvl_bundle["quantization"],
            attention_mode=qwenvl_bundle["attention_mode"],
            use_torch_compile=False,
            device="auto",
            preset_prompt="Describe this image in detail.",
            custom_prompt=prompt,
            max_tokens=qwenvl_bundle["max_tokens"],
            temperature=qwenvl_bundle["temperature"],
            top_p=qwenvl_bundle["top_p"],
            num_beams=qwenvl_bundle["num_beams"],
            repetition_penalty=qwenvl_bundle["repetition_penalty"],
            frame_count=qwenvl_bundle["frame_count"],
            keep_model_loaded=qwenvl_bundle["keep_model_loaded"],
            seed=qwenvl_bundle["seed"],
            video=video,
        )[0]
        return (
            response,
            to_pretty_json(
                {
                    "authoring_language": authoring_language,
                    "scene_analysis": response,
                    "model_name": qwenvl_bundle["model_name"],
                    "frame_count": qwenvl_bundle["frame_count"],
                }
            ),
        )


class AOGPromptDraft:
    """사람 입력 또는 LLM으로 ACE-Step용 프롬프트를 만든다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_batch": ("AOG_VIDEO_BATCH",),
                "video_features": ("AOG_VIDEO_FEATURES",),
                "prompt_mode": (["human", "llm"], {"default": "human"}),
                "user_prompt": ("STRING", {"multiline": True, "default": ""}),
                "llm_provider": (["qwenvl", "local_qwen"], {"default": "qwenvl"}),
                "authoring_language": (LANGUAGE_CHOICES, {"default": "en"}),
            },
            "optional": {
                "qwenvl_bundle": ("AOG_QWENVL_BUNDLE",),
                "scene_analysis": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt_text", "summary_json")
    FUNCTION = "draft"
    CATEGORY = "AOG/Audio"

    def draft(self, video_batch, video_features, prompt_mode, user_prompt, llm_provider, authoring_language, qwenvl_bundle=None, scene_analysis=""):

        """ACE-Step? ?? ????? ????.

        

                Args:

                    video_batch: ?? ??? ??.

                    video_features: ?? ?? payload.

                    prompt_mode: human ?? llm.

                    user_prompt: ?? ????.

                    llm_provider: qwenvl ?? local_qwen.

                    authoring_language: ?? ??.

                    qwenvl_bundle: ??? QwenVL ?? ??.

        

                Returns:

                    `(prompt_text, summary_json)` ??."""
        enriched_features = _inject_scene_analysis(video_features, scene_analysis)
        if prompt_mode == "human":
            prompt_text, info = generate_prompt(video_features=enriched_features, user_prompt=user_prompt, provider="human", language=authoring_language)
        elif llm_provider == "qwenvl" and str(scene_analysis).strip():
            prompt_text, info = generate_prompt(video_features=enriched_features, user_prompt=user_prompt, provider="local_qwen", language=authoring_language)
            info["video_analysis_provider"] = "qwenvl"
            info["drafting_provider"] = "local_qwen"
        elif llm_provider == "qwenvl":
            if qwenvl_bundle is None:
                raise ValueError("prompt_mode=llm with llm_provider=qwenvl requires qwenvl_bundle.")
            prompt_text, info = _draft_prompt_with_qwenvl(video_batch, enriched_features, qwenvl_bundle, authoring_language)
        else:
            prompt_text, info = generate_prompt(video_features=enriched_features, user_prompt=user_prompt, provider=llm_provider, language=authoring_language)
        summary_json = to_pretty_json({"prompt_mode": prompt_mode, "resolved_prompt": prompt_text, "llm_info": info})
        return {
            "ui": {
                "text": [prompt_text],
                "aog_prompt": [prompt_text],
            },
            "result": (prompt_text, summary_json),
        }


class AOGLyricsDraft:
    """사람 입력 또는 LLM으로 ACE-Step용 가사를 만든다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_batch": ("AOG_VIDEO_BATCH",),
                "video_features": ("AOG_VIDEO_FEATURES",),
                "lyrics_mode": (["human", "llm"], {"default": "human"}),
                "user_lyrics": ("STRING", {"multiline": True, "default": ""}),
                "lyrics_language": (LANGUAGE_CHOICES, {"default": "ja"}),
                "llm_provider": (["qwenvl", "local_qwen"], {"default": "qwenvl"}),
                "authoring_language": (LANGUAGE_CHOICES, {"default": "en"}),
            },
            "optional": {
                "qwenvl_bundle": ("AOG_QWENVL_BUNDLE",),
                "scene_analysis": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("lyrics_text", "summary_json")
    FUNCTION = "draft"
    CATEGORY = "AOG/Audio"

    def draft(self, video_batch, video_features, lyrics_mode, user_lyrics, lyrics_language, llm_provider, authoring_language, qwenvl_bundle=None, scene_analysis=""):

        """ACE-Step? ??? ????.

        

                Args:

                    video_batch: ?? ??? ??.

                    video_features: ?? ?? payload.

                    lyrics_mode: human ?? llm.

                    user_lyrics: ?? ??.

                    lyrics_language: ?? ?? ??.

                    llm_provider: qwenvl ?? local_qwen.

                    authoring_language: ??/?? ?? ??.

                    qwenvl_bundle: ??? QwenVL ?? ??.

        

                Returns:

                    `(lyrics_text, summary_json)` ??."""
        enriched_features = _inject_scene_analysis(video_features, scene_analysis)
        if lyrics_mode == "human":
            lyrics_text, info = generate_lyrics(video_features=enriched_features, user_lyrics=user_lyrics, language=lyrics_language, provider="human", authoring_language=authoring_language)
        elif llm_provider == "qwenvl" and str(scene_analysis).strip():
            lyrics_text, info = generate_lyrics(video_features=enriched_features, user_lyrics=user_lyrics, language=lyrics_language, provider="local_qwen", authoring_language=authoring_language)
            info["video_analysis_provider"] = "qwenvl"
            info["drafting_provider"] = "local_qwen"
        elif llm_provider == "qwenvl":
            if qwenvl_bundle is None:
                raise ValueError("lyrics_mode=llm with llm_provider=qwenvl requires qwenvl_bundle.")
            lyrics_text, info = _draft_lyrics_with_qwenvl(video_batch, enriched_features, qwenvl_bundle, authoring_language, lyrics_language)
        else:
            lyrics_text, info = generate_lyrics(video_features=enriched_features, user_lyrics=user_lyrics, language=lyrics_language, provider=llm_provider, authoring_language=authoring_language)
        summary_json = to_pretty_json({"lyrics_mode": lyrics_mode, "lyrics_language": lyrics_language, "resolved_lyrics": lyrics_text, "llm_info": info})
        return {
            "ui": {
                "text": [lyrics_text],
                "aog_lyrics": [lyrics_text],
            },
            "result": (lyrics_text, summary_json),
        }


class AOGMusicPlan:
    """영상 기반으로 BPM, 박자, 조성, 가창 언어를 자동 계획한다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_batch": ("AOG_VIDEO_BATCH",),
                "video_features": ("AOG_VIDEO_FEATURES",),
                "plan_mode": (["human", "llm"], {"default": "llm"}),
                "llm_provider": (["qwenvl", "local_qwen"], {"default": "qwenvl"}),
                "authoring_language": (LANGUAGE_CHOICES, {"default": "en"}),
                "lyrics_language": (LANGUAGE_CHOICES, {"default": "ja"}),
                "manual_bpm": ("INT", {"default": 120, "min": 10, "max": 300}),
                "manual_timesignature": (["2", "3", "4", "6"], {"default": "4"}),
                "manual_keyscale": (KEYSCALE_CHOICES, {"default": "A minor"}),
                "manual_ace_language": (LANGUAGE_CHOICES, {"default": "ja"}),
            },
            "optional": {
                "qwenvl_bundle": ("AOG_QWENVL_BUNDLE",),
                "scene_analysis": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("INT", "FLOAT", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("bpm", "duration", "timesignature", "ace_language", "keyscale", "summary_json")
    FUNCTION = "plan"
    CATEGORY = "AOG/Audio"

    def plan(self, video_batch, video_features, plan_mode, llm_provider, authoring_language, lyrics_language, manual_bpm, manual_timesignature, manual_keyscale, manual_ace_language, qwenvl_bundle=None, scene_analysis=""):

        """?? ?? ?? ?? ?? ????.

        

                Args:

                    video_batch: ?? ??? ??.

                    video_features: ?? ?? payload.

                    plan_mode: human ?? llm.

                    llm_provider: qwenvl ?? local_qwen.

                    authoring_language: ?? ?? ??.

                    lyrics_language: ?? ??.

                    manual_bpm: ?? BPM.

                    manual_timesignature: ?? ??.

                    manual_keyscale: ?? ??.

                    manual_ace_language: ?? ACE ??.

                    qwenvl_bundle: ??? QwenVL ?? ??.

        

                Returns:

                    `(bpm, duration, timesignature, ace_language, keyscale, summary_json)` ??."""
        enriched_features = _inject_scene_analysis(video_features, scene_analysis)
        duration = float(enriched_features.get("source_duration_sec", enriched_features.get("duration_sec", video_batch.get("loaded_duration_sec", 0.0))))
        if duration <= 0:
            fps = float(video_batch.get("loaded_fps", video_batch.get("fps", 0.0)))
            frame_count = int(video_batch.get("frame_count", 0))
            duration = frame_count / fps if fps > 0 and frame_count > 0 else 8.0
        if plan_mode == "human":
            # 수동 모드에서는 사람이 지정한 음악 계획 값을 그대로 사용한다.
            bpm = int(manual_bpm)
            timesignature = str(manual_timesignature)
            ace_language = str(manual_ace_language)
            keyscale = str(manual_keyscale)
            info = {"provider": "human", "mode": "human"}
        elif llm_provider == "qwenvl" and str(scene_analysis).strip():
            plan, info = generate_music_plan(
                enriched_features,
                provider="local_qwen",
                authoring_language=authoring_language,
                lyrics_language=lyrics_language,
            )
            info["video_analysis_provider"] = "qwenvl"
            info["drafting_provider"] = "local_qwen"
            bpm = int(plan["bpm"])
            timesignature = _normalize_timesignature(plan["timesignature"])
            ace_language = _normalize_language_choice(plan["ace_language"])
            keyscale = _normalize_keyscale_choice(plan["keyscale"])
        elif llm_provider == "qwenvl":
            if qwenvl_bundle is None:
                raise ValueError("plan_mode=llm with llm_provider=qwenvl requires qwenvl_bundle.")
            plan, info = _draft_music_plan_with_qwenvl(video_batch, enriched_features, qwenvl_bundle, authoring_language, lyrics_language)
            bpm = int(plan["bpm"])
            timesignature = _normalize_timesignature(plan["timesignature"])
            ace_language = _normalize_language_choice(plan["ace_language"])
            keyscale = _normalize_keyscale_choice(plan["keyscale"])
        else:
            plan, info = generate_music_plan(
                enriched_features,
                provider="local_qwen",
                authoring_language=authoring_language,
                lyrics_language=lyrics_language,
            )
            bpm = int(plan["bpm"])
            timesignature = _normalize_timesignature(plan["timesignature"])
            ace_language = _normalize_language_choice(plan["ace_language"])
            keyscale = _normalize_keyscale_choice(plan["keyscale"])
        summary = {
            "plan_mode": plan_mode,
            "llm_provider": llm_provider if plan_mode == "llm" else "human",
            "duration_sec": float(duration),
            "bpm": int(bpm),
            "timesignature": timesignature,
            "ace_language": ace_language,
            "keyscale": keyscale,
            "llm_info": info,
        }
        return (int(bpm), float(duration), timesignature, ace_language, keyscale, to_pretty_json(summary))


class AOGAceStepCompose:
    """ACE-Step을 호출해 최종 음악 오디오를 생성한다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "video_features": ("AOG_VIDEO_FEATURES",),
                "prompt_text": ("STRING", {"multiline": True, "default": ""}),
                "lyrics_text": ("STRING", {"multiline": True, "default": ""}),
                "negative_tags": ("STRING", {"multiline": True, "default": "silence, clipping, distortion, noise"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "bpm": ("INT", {"default": 120, "min": 10, "max": 300}),
                "duration": ("FLOAT", {"default": 8.0, "min": 0.1, "step": 0.1}),
                "timesignature": ("STRING", {"default": "4", "multiline": False}),
                "ace_language": ("STRING", {"default": "ja", "multiline": False}),
                "keyscale": ("STRING", {"default": "A minor", "multiline": False}),
                "generate_audio_codes": ("BOOLEAN", {"default": True}),
                "text_cfg_scale": ("FLOAT", {"default": 5.0, "min": 0.0, "step": 0.1}),
                "temperature": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.01}),
                "top_k": ("INT", {"default": 0, "min": 0, "max": 1000}),
                "min_p": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "steps": ("INT", {"default": 8, "min": 1, "max": 200}),
                "cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "step": 0.1}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS, {"default": "euler"}),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS, {"default": "simple"}),
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": {"reference_audio": ("AUDIO",)},
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "summary_json")
    FUNCTION = "compose"
    CATEGORY = "AOG/Audio"

    def compose(
        self,
        model,
        clip,
        vae,
        video_features,
        prompt_text,
        lyrics_text,
        negative_tags,
        seed,
        bpm,
        duration,
        timesignature,
        ace_language,
        keyscale,
        generate_audio_codes,
        text_cfg_scale,
        temperature,
        top_p,
        top_k,
        min_p,
        steps,
        cfg,
        sampler_name,
        scheduler,
        denoise,
        reference_audio=None,
    ):

        """ACE-Step?? ??? ????.

        

                Args:

                    model: ACE-Step ??.

                    clip: ACE-Step ??? ???.

                    vae: ACE-Step ??? VAE.

                    video_features: ?? ?? payload.

                    prompt_text: ?? ????.

                    lyrics_text: ?? ??.

                    negative_tags: ?? ??.

                    seed: ?? ??.

                    bpm: ??? BPM.

                    duration: ?? ??.

                    timesignature: ??? ??.

                    ace_language: ACE-Step ?? ??.

                    keyscale: ??? ??.

                    generate_audio_codes: LM 오디오 코드 생성 사용 여부.

                    text_cfg_scale: 텍스트 인코더 CFG 스케일.

                    temperature: 텍스트 인코더 temperature.

                    top_p: 텍스트 인코더 top-p.

                    top_k: 텍스트 인코더 top-k.

                    min_p: 텍스트 인코더 min-p.

                    steps: 샘플링 단계 수.

                    cfg: 샘플러 CFG.

                    sampler_name: ??? ??.

                    scheduler: ???? ??.

                    denoise: denoise ?.

                    reference_audio: ??? ?? ???.

        

                Returns:

                    `(audio, summary_json)` ??."""
        # 계획 노드에서 문자열로 전달된 값을 여기서 다시 검증해
        # 잘못된 워크플로우 연결을 명확한 에러로 드러낸다.
        actual_duration = float(video_features.get("source_duration_sec", video_features.get("duration_sec", duration)))
        timesignature = _normalize_timesignature(timesignature)
        ace_language = _normalize_language_choice(ace_language)
        keyscale = _normalize_keyscale_choice(keyscale)
        if timesignature not in {"2", "3", "4", "6"}:
            raise ValueError(f"Invalid timesignature: {timesignature}")
        if ace_language not in LANGUAGE_CHOICES:
            raise ValueError(f"Invalid ace_language: {ace_language}")
        if keyscale not in KEYSCALE_CHOICES:
            raise ValueError(f"Invalid keyscale: {keyscale}")
        conditioning_summary = video_features.get("conditioning_summary", {})
        latent_cues = video_features.get("latent_structure_cues", [])
        augmented_tags = "\n".join(filter(None, [prompt_text.strip(), build_feature_prompt(video_features), "conditioning summary: " + ", ".join(f"{key}={value}" for key, value in conditioning_summary.items()) if conditioning_summary else "", "latent structure cues: " + ", ".join(latent_cues[:4]) if latent_cues else ""]))
        use_audio_codes = bool(generate_audio_codes) and reference_audio is None
        positive_tokens = clip.tokenize(augmented_tags, lyrics=lyrics_text, bpm=bpm, duration=actual_duration, timesignature=int(timesignature), language=ace_language, keyscale=keyscale, seed=seed, generate_audio_codes=use_audio_codes, cfg_scale=text_cfg_scale, temperature=temperature, top_p=top_p, top_k=top_k, min_p=min_p)
        positive = clip.encode_from_tokens_scheduled(positive_tokens)
        negative_tokens = clip.tokenize(negative_tags, lyrics="", bpm=bpm, duration=actual_duration, timesignature=int(timesignature), language=ace_language, keyscale=keyscale, seed=seed, generate_audio_codes=use_audio_codes, cfg_scale=text_cfg_scale, temperature=temperature, top_p=top_p, top_k=top_k, min_p=min_p)
        negative = clip.encode_from_tokens_scheduled(negative_tokens)
        latent_length = round((actual_duration * 48000 / 1920))
        latent = {"samples": torch.zeros([1, 64, latent_length], device=comfy.model_management.intermediate_device()), "type": "audio"}
        if reference_audio is not None:
            ref_audio = ensure_audio_dict(reference_audio)
            ref_waveform = ref_audio["waveform"]
            if ref_waveform.ndim == 2:
                ref_waveform = ref_waveform.unsqueeze(0)
            ref_latent = nodes_audio.VAEEncodeAudio.execute(vae, {"waveform": ref_waveform, "sample_rate": ref_audio["sample_rate"]}).result[0]
            positive = node_helpers.conditioning_set_values(positive, {"reference_audio_timbre_latents": [ref_latent["samples"]]}, append=True)
        latent_result = nodes.KSampler().sample(model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent, denoise)[0]
        del positive_tokens, negative_tokens, positive, negative, latent
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache(True)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        audio = nodes_audio.vae_decode_audio(vae, latent_result)
        audio = normalize_audio_duration(audio, actual_duration)
        return (
            audio,
            to_pretty_json(
                {
                    "prompt_text": prompt_text,
                    "lyrics_text": lyrics_text,
                    "augmented_tags": augmented_tags,
                    "duration_sec": actual_duration,
                    "ace_language": ace_language,
                    "bpm": bpm,
                    "timesignature": timesignature,
                    "keyscale": keyscale,
                    "generate_audio_codes": use_audio_codes,
                    "text_cfg_scale": text_cfg_scale,
                    "temperature": temperature,
                    "top_p": top_p,
                    "top_k": top_k,
                    "min_p": min_p,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": sampler_name,
                    "scheduler": scheduler,
                    "denoise": denoise,
                    "conditioning_contract": "text-conditioned ACE-Step with preserved video conditioning summary for future direct integration",
                    "has_reference_audio": reference_audio is not None,
                    "waveform_shape": list(audio["waveform"].shape),
                    "sample_rate": audio["sample_rate"],
                }
            ),
        )


class AOGSFXCompose:
    """MMAudio를 이용해 영상 맞춤 효과음 레이어를 생성한다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_batch": ("AOG_VIDEO_BATCH",),
                "video_features": ("AOG_VIDEO_FEATURES",),
                "mmaudio_featureutils": ("MMAUDIO_FEATUREUTILS",),
                "sfx_mode": (["off", "auto"], {"default": "off"}),
                "sfx_prompt_mode": (["human", "llm"], {"default": "llm"}),
                "llm_provider": (["qwenvl", "local_qwen"], {"default": "qwenvl"}),
                "authoring_language": (LANGUAGE_CHOICES, {"default": "en"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "sfx_prompt": ("STRING", {"multiline": True, "default": "anime opening impact swells, whooshes, risers, accent hits"}),
                "negative_prompt": ("STRING", {"multiline": True, "default": "spoken dialogue, vocals, muddy bass, clipping"}),
                "steps": ("INT", {"default": 100, "min": 1, "max": 200}),
                "cfg": ("FLOAT", {"default": 5.0, "min": 0.0, "step": 0.1}),
                "gain": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_away_clip": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "mmaudio_model": ("MMAUDIO_MODEL",),
                "qwenvl_bundle": ("AOG_QWENVL_BUNDLE",),
                "scene_analysis": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "summary_json")
    FUNCTION = "compose"
    CATEGORY = "AOG/Audio"

    def compose(
        self,
        video_batch,
        video_features,
        mmaudio_featureutils,
        sfx_mode,
        sfx_prompt_mode,
        llm_provider,
        authoring_language,
        seed,
        sfx_prompt,
        negative_prompt,
        steps,
        cfg,
        gain,
        mask_away_clip,
        mmaudio_model=None,
        qwenvl_bundle=None,
        scene_analysis="",
    ):
        """MMAudio로 영상 대응 효과음 레이어를 생성한다.

        Args:
            video_batch: AOG 표준 영상 배치.
            video_features: 영상 특징 payload.
            mmaudio_featureutils: MMAudio feature utils 객체.
            sfx_mode: `off` 또는 `auto`.
            sfx_prompt_mode: `human` 또는 `llm`.
            llm_provider: `qwenvl` 또는 `local_qwen`.
            authoring_language: SFX 프롬프트 작성 언어.
            seed: 샘플링 시드.
            sfx_prompt: 사람이 직접 쓰는 SFX 프롬프트 또는 LLM용 기본 힌트.
            negative_prompt: 네거티브 프롬프트.
            steps: 샘플링 스텝 수.
            cfg: 샘플링 CFG.
            gain: 믹싱 참고 gain.
            mask_away_clip: CLIP branch 마스킹 여부.
            mmaudio_model: 선택적 MMAudio SFX 모델.
            qwenvl_bundle: QwenVL 분석 번들.

        Returns:
            `(audio, summary_json)` 튜플.
        """
        duration = float(video_features.get("source_duration_sec", video_batch.get("source_duration_sec", video_batch.get("duration_sec", 0.0))))
        if sfx_mode == "off" or mmaudio_model is None:
            audio = make_silent_audio(duration)
            return (
                audio,
                to_pretty_json(
                    {
                        "sfx_mode": sfx_mode,
                        "sfx_prompt_mode": sfx_prompt_mode,
                        "generated": False,
                        "duration_sec": duration,
                    }
                ),
            )
        mmaudio_nodes = load_module_from_path("aog_ext_mmaudio_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-MMAudio" / "nodes.py"))
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache(True)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        llm_info = {"provider": "none", "mode": sfx_prompt_mode}
        default_sfx_prompt = "anime opening impact swells, whooshes, risers, accent hits"
        resolved_sfx_prompt = sfx_prompt.strip() or default_sfx_prompt
        enriched_features = _inject_scene_analysis(video_features, scene_analysis)
        if sfx_prompt_mode == "llm":
            if llm_provider == "qwenvl":
                if str(scene_analysis).strip():
                    resolved_sfx_prompt, llm_info = generate_sfx_prompt(
                        enriched_features,
                        sfx_prompt,
                        provider="local_qwen",
                        authoring_language=authoring_language,
                    )
                    llm_info["video_analysis_provider"] = "qwenvl"
                    llm_info["drafting_provider"] = "local_qwen"
                elif qwenvl_bundle is None:
                    llm_info = {
                        "provider": "qwenvl",
                        "mode": "degraded",
                        "warning": "qwenvl_bundle missing; used manual/default sfx prompt instead of LLM-authored SFX prompt.",
                    }
                else:
                    resolved_sfx_prompt, llm_info = _draft_sfx_prompt_with_qwenvl(
                        video_batch,
                        enriched_features,
                        qwenvl_bundle,
                        authoring_language,
                    )
            else:
                resolved_sfx_prompt, llm_info = generate_sfx_prompt(
                    enriched_features,
                    sfx_prompt,
                    provider="local_qwen",
                    authoring_language=authoring_language,
                )
        elif not sfx_prompt.strip():
            llm_info = {
                "provider": "human",
                "mode": "degraded",
                "warning": "empty sfx_prompt; used default SFX prompt.",
            }
        prompt = build_sfx_prompt(enriched_features, resolved_sfx_prompt)
        audio = mmaudio_nodes.MMAudioSampler().sample(mmaudio_model=mmaudio_model, seed=seed, feature_utils=mmaudio_featureutils, duration=duration, steps=steps, cfg=cfg, prompt=prompt, negative_prompt=negative_prompt, mask_away_clip=mask_away_clip, force_offload=True, images=video_batch["images"])[0]
        audio = normalize_audio_duration(audio, duration)
        return (
            audio,
            to_pretty_json(
                {
                    "sfx_mode": sfx_mode,
                    "sfx_prompt_mode": sfx_prompt_mode,
                    "generated": True,
                    "duration_sec": duration,
                    "resolved_sfx_prompt": resolved_sfx_prompt,
                    "mmaudio_prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "gain_hint": gain,
                    "mask_away_clip": mask_away_clip,
                    "llm_info": llm_info,
                }
            ),
        )


class AOGFinalAudioMix:
    """ACE-Step 음악과 SFX 레이어를 최종 오디오로 합친다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ace_audio": ("AUDIO",),
                "sfx_audio": ("AUDIO",),
                "sfx_mode": (["off", "auto"], {"default": "off"}),
                "sfx_gain": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
                    }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("final_audio", "summary_json")
    FUNCTION = "mix"
    CATEGORY = "AOG/Audio"

    def mix(self, ace_audio, sfx_audio, sfx_mode, sfx_gain):

        """ACE-Step ???? SFX ???? ???.

        

                Args:

                    ace_audio: ACE-Step ???.

                    sfx_audio: SFX ???.

                    sfx_mode: off ?? auto.

                    sfx_gain: SFX gain ?.

        

                Returns:

                    `(final_audio, summary_json)` ??."""
        if sfx_mode == "auto":
            # 음악 stem을 기준으로 SFX stem을 합성해 최종 오디오를 만든다.
            mixed = mix_audio_dicts(ace_audio, sfx_audio, gain_b=sfx_gain)
            return (mixed, to_pretty_json({"sfx_applied": True, "sfx_mode": sfx_mode, "sfx_gain": sfx_gain}))
        return (ensure_audio_dict(ace_audio), to_pretty_json({"sfx_applied": False, "sfx_mode": sfx_mode, "sfx_gain": sfx_gain}))


class AOGMergeSummaryJSON:
    """여러 단계의 JSON/텍스트 메타데이터를 하나의 최종 summary_json으로 합친다.

    Returns:
        병합된 summary_json 문자열을 담은 튜플.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "video_summary": ("STRING", {"multiline": True, "default": ""}),
                "prompt_summary": ("STRING", {"multiline": True, "default": ""}),
                "lyrics_summary": ("STRING", {"multiline": True, "default": ""}),
                "music_plan_summary": ("STRING", {"multiline": True, "default": ""}),
                "ace_summary": ("STRING", {"multiline": True, "default": ""}),
                "sfx_summary": ("STRING", {"multiline": True, "default": ""}),
                "final_mix_summary": ("STRING", {"multiline": True, "default": ""}),
                "preview_summary": ("STRING", {"multiline": True, "default": ""}),
                "scene_analysis": ("STRING", {"multiline": True, "default": ""}),
                "prompt_text": ("STRING", {"multiline": True, "default": ""}),
                "lyrics_text": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("summary_json",)
    FUNCTION = "merge"
    CATEGORY = "AOG/Debug"

    @staticmethod
    def _load_summary_payload(summary_text):
        """비어 있지 않은 summary 문자열을 dict로 정규화한다.

        Args:
            summary_text: JSON 문자열 또는 일반 문자열.

        Returns:
            dict 또는 None.
        """
        raw = str(summary_text or "").strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw_text": raw}

    def merge(
        self,
        video_summary="",
        prompt_summary="",
        lyrics_summary="",
        music_plan_summary="",
        ace_summary="",
        sfx_summary="",
        final_mix_summary="",
        preview_summary="",
        scene_analysis="",
        prompt_text="",
        lyrics_text="",
    ):

        """여러 단계의 요약을 하나의 JSON으로 병합한다.

        Returns:
            `(summary_json,)` 튜플.
        """
        payload = {}
        summary_map = {
            "video_summary": video_summary,
            "prompt_summary": prompt_summary,
            "lyrics_summary": lyrics_summary,
            "music_plan_summary": music_plan_summary,
            "ace_summary": ace_summary,
            "sfx_summary": sfx_summary,
            "final_mix_summary": final_mix_summary,
            "preview_summary": preview_summary,
        }
        for key, value in summary_map.items():
            parsed = self._load_summary_payload(value)
            if parsed is not None:
                payload[key] = parsed
        if str(scene_analysis or "").strip():
            payload["scene_analysis"] = str(scene_analysis).strip()
        if str(prompt_text or "").strip():
            payload["prompt_text"] = str(prompt_text).strip()
        if str(lyrics_text or "").strip():
            payload["lyrics_text"] = str(lyrics_text).strip()
        return (to_pretty_json(payload),)


class AOGSaveSummaryJSON:
    """summary_json 문자열을 실제 JSON 파일로 저장한다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "summary_json": ("STRING", {"multiline": True, "default": "{}"}),
                "filename_prefix": ("STRING", {"default": "AOG/summary"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("saved_path", "summary_json")
    OUTPUT_NODE = True
    FUNCTION = "save"
    CATEGORY = "AOG/Debug"

    def save(self, summary_json, filename_prefix):

        """?? JSON? ?? ??? ????.

        

                Args:

                    summary_json: ??? JSON ???.

                    filename_prefix: ?? ?? prefix.

        

                Returns:

                    `(saved_path, summary_json)` ??."""
        safe_prefix = (filename_prefix or "AOG/summary").replace("\\", "/").strip("/")
        subdir = Path(folder_paths.get_output_directory()) / Path(safe_prefix).parent
        subdir.mkdir(parents=True, exist_ok=True)
        stem = Path(safe_prefix).name or "summary"
        counter = 1
        while True:
            candidate = subdir / f"{stem}_{counter:05d}.json"
            if not candidate.exists():
                break
            counter += 1
        try:
            payload = json.loads(summary_json)
            candidate.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except json.JSONDecodeError:
            candidate.write_text(summary_json, encoding="utf-8")
        return (str(candidate), summary_json)


class AOGMuxVideoAudio:
    """기존 비디오 파일에 생성한 오디오를 mux해 새 파일로 저장한다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"enabled": ("BOOLEAN", {"default": True}), "video_path": ("STRING", {"default": "", "multiline": False}), "audio": ("AUDIO",), "output_path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("output_path",)
    FUNCTION = "mux"
    CATEGORY = "AOG/Video"

    def mux(self, enabled, video_path, audio, output_path):

        """???? ???? ??? ??? mux??.

        

                Args:

                    enabled: mux ?? ??.

                    video_path: ?? ??? ??.

                    audio: ??? ??? payload.

                    output_path: ?? ?? ??.

        

                Returns:

                    `(output_path,)` ??."""
        if not enabled:
            return (video_path,)
        with av.open(video_path) as container:
            stream = container.streams.video[0]
            frame_count = int(stream.frames or 0)
            if stream.average_rate is not None and frame_count > 0:
                video_duration_sec = frame_count / float(stream.average_rate)
            elif stream.duration is not None and stream.time_base is not None:
                video_duration_sec = float(stream.duration * stream.time_base)
            else:
                video_duration_sec = audio_duration_sec(audio)
        audio = normalize_audio_duration(audio, video_duration_sec)
        temp_audio = Path(output_path).with_suffix(".aog_temp.wav")
        _save_audio_to_wav(audio, str(temp_audio))
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        # -shortest를 쓰지 않고 mux해서 영상이나 오디오가 의도치 않게 잘리지 않도록 한다.
        command = ["ffmpeg", "-y", "-i", video_path, "-i", str(temp_audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(output)]
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            if temp_audio.exists():
                temp_audio.unlink()
        return (str(output),)


class AOGPreviewVideoCombine:
    """ComfyUI 내부 미리보기를 위해 비디오와 오디오를 결합한다."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_batch": ("AOG_VIDEO_BATCH",),
                "audio": ("AUDIO",),
                "filename_prefix": ("STRING", {"default": "AOG/preview"}),
                "format": (["video/mp4", "video/webm", "image/gif", "image/webp"], {"default": "video/mp4"}),
                "save_output": ("BOOLEAN", {"default": True}),
                "pingpong": ("BOOLEAN", {"default": False}),
                "loop_count": ("INT", {"default": 0, "min": 0, "max": 100, "step": 1}),
            },
            "optional": {
                "meta_batch": ("VHS_BatchManager",),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("VHS_FILENAMES", "STRING")
    RETURN_NAMES = ("filenames", "summary_json")
    OUTPUT_NODE = True
    FUNCTION = "combine"
    CATEGORY = "AOG/Video"

    def combine(self, video_batch, audio, filename_prefix, format, save_output, pingpong, loop_count, meta_batch=None, prompt=None, extra_pnginfo=None, unique_id=None):

        """VHS VideoCombine? ?? ??? ???? ????.

        

                Args:

                    video_batch: ?? ??? ??.

                    audio: ??? ??? payload.

                    filename_prefix: ?? prefix.

                    format: ?? ??.

                    save_output: ?? ?? ??.

                    pingpong: pingpong ?? ??.

                    loop_count: ?? ??.

                    meta_batch: ??? VHS ?? ??.

                    prompt: ComfyUI hidden prompt.

                    extra_pnginfo: ComfyUI hidden png info.

                    unique_id: ComfyUI hidden unique id.

        

                Returns:

                    ComfyUI? ???? `ui/result` ????."""
        images = video_batch["images"]
        frame_rate = float(video_batch.get("loaded_fps", video_batch.get("fps", 8.0)))
        duration = float(video_batch.get("source_duration_sec", video_batch.get("duration_sec", audio_duration_sec(audio))))
        audio = normalize_audio_duration(audio, duration)
        summary_json = to_pretty_json({"frame_rate": frame_rate, "duration_sec": duration, "format": format, "save_output": bool(save_output), "source_path": str(video_batch.get("source_path", ""))})
        vhs_module = load_module_from_path("aog_ext_vhs_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-VideoHelperSuite" / "videohelpersuite" / "nodes.py"))
        resolved_format = VHS_FORMAT_ALIASES.get(format, format)
        # VHS의 ui payload를 그대로 전달해야 ComfyUI에서 저장 결과와 미리보기가 보인다.
        result = vhs_module.VideoCombine().combine_video(
            images=images,
            frame_rate=frame_rate,
            loop_count=loop_count,
            filename_prefix=filename_prefix,
            format=resolved_format,
            pingpong=pingpong,
            save_output=save_output,
            prompt=prompt,
            extra_pnginfo=extra_pnginfo,
            audio=audio,
            unique_id=unique_id,
            meta_batch=meta_batch,
        )
        if isinstance(result, dict):
            filenames = result["result"][0]
            ui_payload = result.get("ui")
            return {"ui": ui_payload, "result": (filenames, to_pretty_json({"frame_rate": frame_rate, "duration_sec": duration, "format": resolved_format, "save_output": save_output, "source_path": str(video_batch.get("source_path", ""))}))}
        filenames = result[0]
        return {"result": (filenames, to_pretty_json({"frame_rate": frame_rate, "duration_sec": duration, "format": resolved_format, "save_output": save_output, "source_path": str(video_batch.get("source_path", ""))}))}



NODE_CLASS_MAPPINGS = {
    "AOG MMAudio Feature Bundle": AOGMMAudioFeatureBundle,
    "AOG MMAudio SFX Bundle": AOGMMAudioSFXBundle,
    "AOG QwenVL Bundle": AOGQwenVLBundle,
    "AOG Quality Preset": AOGQualityPreset,
    "AOG Load Video Frames": AOGLoadVideoFrames,
    "AOG Workflow Video Batch Adapter": AOGWorkflowVideoBatchAdapter,
    "AOG VHS Video Batch Adapter": AOGVHSVideoBatchAdapter,
    "AOG Video Feature Extract": AOGVideoFeatureExtract,
    "AOG QwenVL Semantic Extract": AOGQwenVLSemanticExtract,
    "AOG Prompt Draft": AOGPromptDraft,
    "AOG Lyrics Draft": AOGLyricsDraft,
    "AOG Music Plan": AOGMusicPlan,
    "AOG ACE-Step Compose": AOGAceStepCompose,
    "AOG SFX Compose": AOGSFXCompose,
    "AOG Final Audio Mix": AOGFinalAudioMix,
    "AOG Merge Summary JSON": AOGMergeSummaryJSON,
    "AOG Save Summary JSON": AOGSaveSummaryJSON,
    "AOG Mux Video Audio": AOGMuxVideoAudio,
    "AOG Preview Video Combine": AOGPreviewVideoCombine,
}

NODE_DISPLAY_NAME_MAPPINGS = {name: name for name in NODE_CLASS_MAPPINGS}
