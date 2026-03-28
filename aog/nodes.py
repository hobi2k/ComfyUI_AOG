import json
import subprocess
from pathlib import Path

import av
import numpy as np
import torch

import comfy.model_management
import comfy.samplers
import node_helpers
import nodes
from comfy_extras import nodes_audio

from .helpers import CUSTOM_NODES_DIR, audio_duration_sec, build_feature_prompt, build_llm_context, build_sfx_prompt, build_timeline, derive_semantic_cues, ensure_audio_dict, infer_song_sections, load_module_from_path, make_silent_audio, mix_audio_dicts, normalize_audio_duration, summarize_conditioning_payload, summarize_video_frames, to_pretty_json
from .llm import generate_lyrics, generate_prompt

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


def _generate_qwenvl_authoring_text(video_batch, video_features, qwenvl_bundle, authoring_language, custom_prompt):
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


def _draft_prompt_with_qwenvl(video_batch, video_features, qwenvl_bundle, title, theme, authoring_language):
    context = build_llm_context(video_features)
    custom_prompt = (
        f"You are writing an ACE-Step music prompt for an anime opening. Respond only in {authoring_language}. "
        "Return plain text only, with no markdown, no bullet list, and no explanation. "
        "Use the video itself plus the structured context below. Write a concise, vivid music-generation prompt describing instrumentation, pacing, rises, drops, emotional arc, transitions, and hook moments that fit this opening exactly.\n\n"
        f"Title: {title}\n"
        f"Theme: {theme}\n"
        f"Structured context: {json.dumps(context, ensure_ascii=False)}"
    )
    return _generate_qwenvl_authoring_text(video_batch, video_features, qwenvl_bundle, authoring_language, custom_prompt)


def _draft_lyrics_with_qwenvl(video_batch, video_features, qwenvl_bundle, title, theme, authoring_language, lyrics_language):
    context = build_llm_context(video_features)
    custom_prompt = (
        f"You are writing singable ACE-Step lyrics for an anime opening. Respond only in {lyrics_language}. "
        "Return plain text only. Use section labels like [Verse], [Pre-Chorus], [Chorus]. "
        "Match the video's pacing, turning points, climactic rise, and visible motifs. "
        "Do not explain your reasoning. Every lyric line must be written in the requested lyrics language. "
        "Do not switch languages. Do not translate the title unless needed inside a lyric line.\n\n"
        f"Authoring language: {authoring_language}\n"
        f"Lyrics language: {lyrics_language}\n"
        f"Title: {title}\n"
        f"Theme: {theme}\n"
        f"Structured context: {json.dumps(context, ensure_ascii=False)}"
    )
    return _generate_qwenvl_authoring_text(video_batch, video_features, qwenvl_bundle, lyrics_language, custom_prompt)

LANGUAGE_CHOICES = ["en", "ja", "zh", "es", "de", "fr", "pt", "ru", "it", "nl", "pl", "tr", "vi", "cs", "fa", "id", "ko", "uk", "hu", "ar", "sv", "ro", "el"]
KEYSCALE_CHOICES = [f"{root} {quality}" for quality in ["major", "minor"] for root in ["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"]]


def _save_audio_to_wav(audio, output_path):
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
    @classmethod
    def INPUT_TYPES(cls):
        mmaudio_nodes = load_module_from_path("aog_ext_mmaudio_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-MMAudio" / "nodes.py"))
        return mmaudio_nodes.MMAudioFeatureUtilsLoader.INPUT_TYPES()

    RETURN_TYPES = ("MMAUDIO_FEATUREUTILS",)
    RETURN_NAMES = ("mmaudio_featureutils",)
    FUNCTION = "load_bundle"
    CATEGORY = "AOG/Audio"

    def load_bundle(self, vae_model, synchformer_model, clip_model, precision="fp16", mode="44k", bigvgan_vocoder_model=None):
        mmaudio_nodes = load_module_from_path("aog_ext_mmaudio_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-MMAudio" / "nodes.py"))
        return mmaudio_nodes.MMAudioFeatureUtilsLoader().loadmodel(vae_model=vae_model, precision=precision, synchformer_model=synchformer_model, clip_model=clip_model, mode=mode, bigvgan_vocoder_model=bigvgan_vocoder_model)


class AOGMMAudioSFXBundle:
    @classmethod
    def INPUT_TYPES(cls):
        mmaudio_nodes = load_module_from_path("aog_ext_mmaudio_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-MMAudio" / "nodes.py"))
        return mmaudio_nodes.MMAudioModelLoader.INPUT_TYPES()

    RETURN_TYPES = ("MMAUDIO_MODEL",)
    RETURN_NAMES = ("mmaudio_model",)
    FUNCTION = "load_bundle"
    CATEGORY = "AOG/Audio"

    def load_bundle(self, mmaudio_model, base_precision="fp16"):
        mmaudio_nodes = load_module_from_path("aog_ext_mmaudio_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-MMAudio" / "nodes.py"))
        return mmaudio_nodes.MMAudioModelLoader().loadmodel(mmaudio_model=mmaudio_model, base_precision=base_precision)


class AOGQwenVLBundle:
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
                "keep_model_loaded": ("BOOLEAN", {"default": False}),
                "seed": ("INT", {"default": 1, "min": 1, "max": 2**32 - 1}),
            }
        }

    RETURN_TYPES = ("AOG_QWENVL_BUNDLE",)
    RETURN_NAMES = ("qwenvl_bundle",)
    FUNCTION = "load_bundle"
    CATEGORY = "AOG/Authoring"

    def load_bundle(self, model_name, quantization, attention_mode, frame_count, max_tokens, temperature, top_p, num_beams, repetition_penalty, keep_model_loaded, seed):
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


class AOGLoadVideoFrames:
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
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",), "fps": ("FLOAT", {"default": 8.0, "min": 0.1, "step": 0.1}), "source_path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = ("AOG_VIDEO_BATCH", "STRING")
    RETURN_NAMES = ("video_batch", "summary_json")
    FUNCTION = "adapt"
    CATEGORY = "AOG/Video"

    def adapt(self, images, fps, source_path):
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


class AOGVideoFeatureExtract:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video_batch": ("AOG_VIDEO_BATCH",), "mmaudio_featureutils": ("MMAUDIO_FEATUREUTILS",), "mask_away_clip": ("BOOLEAN", {"default": False})}}

    RETURN_TYPES = ("AOG_VIDEO_FEATURES", "STRING")
    RETURN_NAMES = ("video_features", "summary_json")
    FUNCTION = "extract_features"
    CATEGORY = "AOG/Audio"

    def extract_features(self, video_batch, mmaudio_featureutils, mask_away_clip):
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
            mmaudio_featureutils.to(comfy.model_management.unet_offload_device())
            comfy.model_management.soft_empty_cache()
        summary = summarize_video_frames(images, source_duration if source_duration > 0 else requested_duration)
        timeline = build_timeline(images, source_duration if source_duration > 0 else requested_duration, segment_count=8)
        semantic_cues = derive_semantic_cues(summary, timeline)
        conditioning_summary = summarize_conditioning_payload(clip_features, sync_features)
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
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_batch": ("AOG_VIDEO_BATCH",),
                "qwenvl_bundle": ("AOG_QWENVL_BUNDLE",),
                "authoring_language": (LANGUAGE_CHOICES, {"default": "ja"}),
                "analysis_prompt": ("STRING", {"multiline": True, "default": ""}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("scene_analysis", "summary_json")
    FUNCTION = "extract"
    CATEGORY = "AOG/Authoring"

    def extract(self, video_batch, qwenvl_bundle, authoring_language, analysis_prompt):
        qwen_module = load_module_from_path("aog_ext_qwenvl_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-QwenVL" / "AILab_QwenVL.py"))
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
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_batch": ("AOG_VIDEO_BATCH",),
                "video_features": ("AOG_VIDEO_FEATURES",),
                "prompt_mode": (["human", "llm"], {"default": "human"}),
                "user_prompt": ("STRING", {"multiline": True, "default": ""}),
                "llm_provider": (["qwenvl", "local_qwen"], {"default": "qwenvl"}),
                "llm_model": ("STRING", {"default": "models/text_encoders/qwen_4b_ace15.safetensors", "multiline": False}),
                "title": ("STRING", {"default": "", "multiline": False}),
                "theme": ("STRING", {"default": "", "multiline": False}),
                "authoring_language": (LANGUAGE_CHOICES, {"default": "ja"}),
            },
            "optional": {
                "qwenvl_bundle": ("AOG_QWENVL_BUNDLE",),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt_text", "summary_json")
    FUNCTION = "draft"
    CATEGORY = "AOG/Audio"

    def draft(self, video_batch, video_features, prompt_mode, user_prompt, llm_provider, llm_model, title, theme, authoring_language, qwenvl_bundle=None):
        if prompt_mode == "human":
            prompt_text, info = generate_prompt(video_features=video_features, user_prompt=user_prompt, provider="human", model=llm_model, title=title, theme=theme, language=authoring_language)
        elif llm_provider == "qwenvl":
            if qwenvl_bundle is None:
                raise ValueError("prompt_mode=llm with llm_provider=qwenvl requires qwenvl_bundle.")
            prompt_text, info = _draft_prompt_with_qwenvl(video_batch, video_features, qwenvl_bundle, title, theme, authoring_language)
        else:
            prompt_text, info = generate_prompt(video_features=video_features, user_prompt=user_prompt, provider=llm_provider, model=llm_model, title=title, theme=theme, language=authoring_language)
        return (prompt_text, to_pretty_json({"prompt_mode": prompt_mode, "resolved_prompt": prompt_text, "llm_info": info}))


class AOGLyricsDraft:
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
                "llm_model": ("STRING", {"default": "models/text_encoders/qwen_4b_ace15.safetensors", "multiline": False}),
                "title": ("STRING", {"default": "", "multiline": False}),
                "theme": ("STRING", {"default": "", "multiline": False}),
                "authoring_language": (LANGUAGE_CHOICES, {"default": "ja"}),
            },
            "optional": {
                "qwenvl_bundle": ("AOG_QWENVL_BUNDLE",),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("lyrics_text", "summary_json")
    FUNCTION = "draft"
    CATEGORY = "AOG/Audio"

    def draft(self, video_batch, video_features, lyrics_mode, user_lyrics, lyrics_language, llm_provider, llm_model, title, theme, authoring_language, qwenvl_bundle=None):
        if lyrics_mode == "human":
            lyrics_text, info = generate_lyrics(video_features=video_features, user_lyrics=user_lyrics, language=lyrics_language, provider="human", model=llm_model, title=title, theme=theme, authoring_language=authoring_language)
        elif llm_provider == "qwenvl":
            if qwenvl_bundle is None:
                raise ValueError("lyrics_mode=llm with llm_provider=qwenvl requires qwenvl_bundle.")
            lyrics_text, info = _draft_lyrics_with_qwenvl(video_batch, video_features, qwenvl_bundle, title, theme, authoring_language, lyrics_language)
        else:
            lyrics_text, info = generate_lyrics(video_features=video_features, user_lyrics=user_lyrics, language=lyrics_language, provider=llm_provider, model=llm_model, title=title, theme=theme, authoring_language=authoring_language)
        return (lyrics_text, to_pretty_json({"lyrics_mode": lyrics_mode, "lyrics_language": lyrics_language, "resolved_lyrics": lyrics_text, "llm_info": info}))


class AOGAceStepCompose:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("MODEL",), "clip": ("CLIP",), "vae": ("VAE",), "video_features": ("AOG_VIDEO_FEATURES",), "prompt_text": ("STRING", {"multiline": True, "default": ""}), "lyrics_text": ("STRING", {"multiline": True, "default": ""}), "negative_tags": ("STRING", {"multiline": True, "default": "silence, clipping, distortion, noise"}), "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}), "bpm": ("INT", {"default": 120, "min": 10, "max": 300}), "duration": ("FLOAT", {"default": 8.0, "min": 0.1, "step": 0.1}), "timesignature": (["2", "3", "4", "6"], {"default": "4"}), "ace_language": (LANGUAGE_CHOICES, {"default": "ja"}), "keyscale": (KEYSCALE_CHOICES, {"default": "A minor"}), "steps": ("INT", {"default": 8, "min": 1, "max": 200}), "cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "step": 0.1}), "text_cfg_scale": ("FLOAT", {"default": 5.0, "min": 0.0, "step": 0.1}), "sampler_name": (comfy.samplers.KSampler.SAMPLERS, {"default": "euler"}), "scheduler": (comfy.samplers.KSampler.SCHEDULERS, {"default": "simple"}), "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01})}, "optional": {"reference_audio": ("AUDIO",)}}

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "summary_json")
    FUNCTION = "compose"
    CATEGORY = "AOG/Audio"

    def compose(self, model, clip, vae, video_features, prompt_text, lyrics_text, negative_tags, seed, bpm, duration, timesignature, ace_language, keyscale, steps, cfg, text_cfg_scale, sampler_name, scheduler, denoise, reference_audio=None):
        actual_duration = float(video_features.get("source_duration_sec", video_features.get("duration_sec", duration)))
        conditioning_summary = video_features.get("conditioning_summary", {})
        latent_cues = video_features.get("latent_structure_cues", [])
        augmented_tags = "\n".join(filter(None, [prompt_text.strip(), build_feature_prompt(video_features), "conditioning summary: " + ", ".join(f"{key}={value}" for key, value in conditioning_summary.items()) if conditioning_summary else "", "latent structure cues: " + ", ".join(latent_cues[:4]) if latent_cues else ""]))
        use_audio_codes = reference_audio is None
        positive_tokens = clip.tokenize(augmented_tags, lyrics=lyrics_text, bpm=bpm, duration=actual_duration, timesignature=int(timesignature), language=ace_language, keyscale=keyscale, seed=seed, generate_audio_codes=use_audio_codes, cfg_scale=text_cfg_scale, temperature=0.85, top_p=0.9, top_k=0, min_p=0.0)
        positive = clip.encode_from_tokens_scheduled(positive_tokens)
        negative_tokens = clip.tokenize(negative_tags, lyrics="", bpm=bpm, duration=actual_duration, timesignature=int(timesignature), language=ace_language, keyscale=keyscale, seed=seed, generate_audio_codes=use_audio_codes, cfg_scale=text_cfg_scale, temperature=0.85, top_p=0.9, top_k=0, min_p=0.0)
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
        return (audio, to_pretty_json({"prompt_text": prompt_text, "augmented_tags": augmented_tags, "duration_sec": actual_duration, "ace_language": ace_language, "bpm": bpm, "text_cfg_scale": text_cfg_scale, "conditioning_contract": "text-conditioned ACE-Step with preserved video conditioning summary for future direct integration", "has_reference_audio": reference_audio is not None, "waveform_shape": list(audio["waveform"].shape), "sample_rate": audio["sample_rate"]}))


class AOGSFXCompose:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video_batch": ("AOG_VIDEO_BATCH",), "video_features": ("AOG_VIDEO_FEATURES",), "mmaudio_featureutils": ("MMAUDIO_FEATUREUTILS",), "sfx_mode": (["off", "auto"], {"default": "off"}), "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}), "sfx_prompt": ("STRING", {"multiline": True, "default": "anime opening impact swells, whooshes, risers, accent hits"}), "negative_prompt": ("STRING", {"multiline": True, "default": "spoken dialogue, vocals, muddy bass, clipping"}), "steps": ("INT", {"default": 8, "min": 1, "max": 200}), "cfg": ("FLOAT", {"default": 3.5, "min": 0.0, "step": 0.1}), "gain": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}), "mask_away_clip": ("BOOLEAN", {"default": True})}, "optional": {"mmaudio_model": ("MMAUDIO_MODEL",)}}

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "summary_json")
    FUNCTION = "compose"
    CATEGORY = "AOG/Audio"

    def compose(self, video_batch, video_features, mmaudio_featureutils, sfx_mode, seed, sfx_prompt, negative_prompt, steps, cfg, gain, mask_away_clip, mmaudio_model=None):
        duration = float(video_features.get("source_duration_sec", video_batch.get("source_duration_sec", video_batch.get("duration_sec", 0.0))))
        if sfx_mode == "off" or mmaudio_model is None:
            audio = make_silent_audio(duration)
            return (audio, to_pretty_json({"sfx_mode": sfx_mode, "generated": False, "duration_sec": duration}))
        mmaudio_nodes = load_module_from_path("aog_ext_mmaudio_nodes", str(CUSTOM_NODES_DIR / "ComfyUI-MMAudio" / "nodes.py"))
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache(True)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        prompt = build_sfx_prompt(video_features, sfx_prompt)
        audio = mmaudio_nodes.MMAudioSampler().sample(mmaudio_model=mmaudio_model, seed=seed, feature_utils=mmaudio_featureutils, duration=duration, steps=steps, cfg=cfg, prompt=prompt, negative_prompt=negative_prompt, mask_away_clip=mask_away_clip, force_offload=True, images=video_batch["images"])[0]
        audio = normalize_audio_duration(audio, duration)
        return (audio, to_pretty_json({"sfx_mode": sfx_mode, "generated": True, "duration_sec": duration, "sfx_prompt": prompt, "gain_hint": gain, "mask_away_clip": mask_away_clip}))


class AOGMuxVideoAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video_path": ("STRING", {"default": "", "multiline": False}), "audio": ("AUDIO",), "output_path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("output_path",)
    FUNCTION = "mux"
    CATEGORY = "AOG/Video"

    def mux(self, video_path, audio, output_path):
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
        command = ["ffmpeg", "-y", "-i", video_path, "-i", str(temp_audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(output)]
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            if temp_audio.exists():
                temp_audio.unlink()
        return (str(output),)


class AOGOpeningMusicPipeline:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video_batch": ("AOG_VIDEO_BATCH",), "mmaudio_featureutils": ("MMAUDIO_FEATUREUTILS",), "model": ("MODEL",), "clip": ("CLIP",), "vae": ("VAE",), "title": ("STRING", {"default": "", "multiline": False}), "theme": ("STRING", {"default": "", "multiline": False}), "prompt_mode": (["human", "llm"], {"default": "human"}), "prompt_text": ("STRING", {"multiline": True, "default": ""}), "lyrics_mode": (["human", "llm"], {"default": "human"}), "lyrics_text": ("STRING", {"multiline": True, "default": ""}), "negative_tags": ("STRING", {"multiline": True, "default": "silence, clipping, distortion, noise"}), "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}), "bpm": ("INT", {"default": 120, "min": 10, "max": 300}), "timesignature": (["2", "3", "4", "6"], {"default": "4"}), "authoring_language": (LANGUAGE_CHOICES, {"default": "ja"}), "lyrics_language": (LANGUAGE_CHOICES, {"default": "ja"}), "ace_language": (LANGUAGE_CHOICES, {"default": "ja"}), "keyscale": (KEYSCALE_CHOICES, {"default": "A minor"}), "steps": ("INT", {"default": 8, "min": 1, "max": 200}), "cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "step": 0.1}), "text_cfg_scale": ("FLOAT", {"default": 5.0, "min": 0.0, "step": 0.1}), "sampler_name": (comfy.samplers.KSampler.SAMPLERS, {"default": "euler"}), "scheduler": (comfy.samplers.KSampler.SCHEDULERS, {"default": "simple"}), "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}), "mask_away_clip": ("BOOLEAN", {"default": False}), "llm_provider": (["qwenvl", "local_qwen"], {"default": "qwenvl"}), "llm_model": ("STRING", {"default": "models/text_encoders/qwen_4b_ace15.safetensors", "multiline": False}), "sfx_mode": (["off", "auto"], {"default": "off"}), "sfx_prompt": ("STRING", {"multiline": True, "default": "anime opening impact swells, whooshes, risers, accent hits"}), "sfx_negative_prompt": ("STRING", {"multiline": True, "default": "spoken dialogue, vocals, muddy bass, clipping"}), "sfx_steps": ("INT", {"default": 8, "min": 1, "max": 200}), "sfx_cfg": ("FLOAT", {"default": 3.5, "min": 0.0, "step": 0.1}), "sfx_gain": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}), "sfx_mask_away_clip": ("BOOLEAN", {"default": True})}, "optional": {"reference_audio": ("AUDIO",), "mmaudio_model": ("MMAUDIO_MODEL",), "qwenvl_bundle": ("AOG_QWENVL_BUNDLE",), "qwenvl_analysis_prompt": ("STRING", {"multiline": True, "default": ""})}}

    RETURN_TYPES = ("AOG_VIDEO_FEATURES", "AUDIO", "AUDIO", "AUDIO", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video_features", "final_audio", "ace_audio", "sfx_audio", "resolved_prompt", "resolved_lyrics", "summary_json")
    FUNCTION = "run_pipeline"
    CATEGORY = "AOG/Audio"

    def run_pipeline(self, video_batch, mmaudio_featureutils, model, clip, vae, title, theme, prompt_mode, prompt_text, lyrics_mode, lyrics_text, negative_tags, seed, bpm, timesignature, authoring_language, lyrics_language, ace_language, keyscale, steps, cfg, text_cfg_scale, sampler_name, scheduler, denoise, mask_away_clip=False, llm_provider="qwenvl", llm_model="models/text_encoders/qwen_4b_ace15.safetensors", sfx_mode="off", sfx_prompt="", sfx_negative_prompt="", sfx_steps=8, sfx_cfg=3.5, sfx_gain=0.35, sfx_mask_away_clip=True, reference_audio=None, mmaudio_model=None, qwenvl_bundle=None, qwenvl_analysis_prompt=""):
        print("[AOG] pipeline: extracting MMAudio features...", flush=True)
        video_features, _ = AOGVideoFeatureExtract().extract_features(video_batch, mmaudio_featureutils, mask_away_clip)
        scene_analysis = ""
        if qwenvl_bundle is not None:
            print("[AOG] pipeline: extracting QwenVL scene analysis...", flush=True)
            scene_analysis, _ = AOGQwenVLSemanticExtract().extract(video_batch=video_batch, qwenvl_bundle=qwenvl_bundle, authoring_language=authoring_language, analysis_prompt=qwenvl_analysis_prompt)
            video_features["qwenvl_scene_analysis"] = scene_analysis
            video_features["qwenvl_analysis_language"] = authoring_language
        print("[AOG] pipeline: resolving prompt...", flush=True)
        resolved_prompt, prompt_json = AOGPromptDraft().draft(video_batch=video_batch, video_features=video_features, prompt_mode=prompt_mode, user_prompt=prompt_text, llm_provider=llm_provider, llm_model=llm_model, title=title, theme=theme, authoring_language=authoring_language, qwenvl_bundle=qwenvl_bundle)
        print("[AOG] pipeline: resolving lyrics...", flush=True)
        resolved_lyrics, lyrics_json = AOGLyricsDraft().draft(video_batch=video_batch, video_features=video_features, lyrics_mode=lyrics_mode, user_lyrics=lyrics_text, lyrics_language=lyrics_language, llm_provider=llm_provider, llm_model=llm_model, title=title, theme=theme, authoring_language=authoring_language, qwenvl_bundle=qwenvl_bundle)
        print("[AOG] pipeline: composing ACE-Step audio...", flush=True)
        ace_audio, ace_json = AOGAceStepCompose().compose(model=model, clip=clip, vae=vae, video_features=video_features, prompt_text=resolved_prompt, lyrics_text=resolved_lyrics, negative_tags=negative_tags, seed=seed, bpm=bpm, duration=video_features["duration_sec"], timesignature=timesignature, ace_language=ace_language, keyscale=keyscale, steps=steps, cfg=cfg, text_cfg_scale=text_cfg_scale, sampler_name=sampler_name, scheduler=scheduler, denoise=denoise, reference_audio=reference_audio)
        print("[AOG] pipeline: composing SFX layer...", flush=True)
        sfx_audio, sfx_json = AOGSFXCompose().compose(video_batch=video_batch, video_features=video_features, mmaudio_featureutils=mmaudio_featureutils, sfx_mode=sfx_mode, seed=seed + 1, sfx_prompt=sfx_prompt, negative_prompt=sfx_negative_prompt, steps=sfx_steps, cfg=sfx_cfg, gain=sfx_gain, mask_away_clip=sfx_mask_away_clip, mmaudio_model=mmaudio_model)
        final_audio = mix_audio_dicts(ace_audio, sfx_audio, gain_b=sfx_gain) if sfx_mode == "auto" else ace_audio
        summary_json = to_pretty_json({"video_summary": video_features["summary"], "timeline": video_features["timeline"], "semantic_cues": video_features["semantic_cues"], "qwenvl_scene_analysis": video_features.get("qwenvl_scene_analysis", ""), "qwenvl_analysis_language": video_features.get("qwenvl_analysis_language", ""), "conditioning_summary": video_features["conditioning_summary"], "latent_structure_cues": video_features["latent_structure_cues"], "prompt_mode": prompt_mode, "lyrics_mode": lyrics_mode, "authoring_language": authoring_language, "lyrics_language": lyrics_language, "ace_language": ace_language, "llm_provider": llm_provider if prompt_mode == "llm" or lyrics_mode == "llm" else "human", "sfx_mode": sfx_mode, "implementation_note": "ACE-Step currently receives text plus derived video cues; raw conditioning payload is preserved for future direct integration.", "prompt_summary": prompt_json, "lyrics_summary": lyrics_json, "ace_summary": ace_json, "sfx_summary": sfx_json})
        return (video_features, final_audio, ace_audio, sfx_audio, resolved_prompt, resolved_lyrics, summary_json)


NODE_CLASS_MAPPINGS = {
    "AOG MMAudio Feature Bundle": AOGMMAudioFeatureBundle,
    "AOG MMAudio SFX Bundle": AOGMMAudioSFXBundle,
    "AOG QwenVL Bundle": AOGQwenVLBundle,
    "AOG Load Video Frames": AOGLoadVideoFrames,
    "AOG Workflow Video Batch Adapter": AOGWorkflowVideoBatchAdapter,
    "AOG Video Feature Extract": AOGVideoFeatureExtract,
    "AOG QwenVL Semantic Extract": AOGQwenVLSemanticExtract,
    "AOG Prompt Draft": AOGPromptDraft,
    "AOG Lyrics Draft": AOGLyricsDraft,
    "AOG ACE-Step Compose": AOGAceStepCompose,
    "AOG SFX Compose": AOGSFXCompose,
    "AOG Mux Video Audio": AOGMuxVideoAudio,
    "AOG Opening Music Pipeline": AOGOpeningMusicPipeline,
}

NODE_DISPLAY_NAME_MAPPINGS = {name: name for name in NODE_CLASS_MAPPINGS}
