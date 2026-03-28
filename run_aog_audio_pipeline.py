import argparse
import json
import subprocess
import sys
from pathlib import Path

import av


ROOT_DIR = Path(__file__).resolve().parent
COMFY_DIR = ROOT_DIR.parent.parent


def _save_audio_file(audio, output_path):
    import numpy as np
    import wave
    output_path.parent.mkdir(parents=True, exist_ok=True)
    waveform = audio["waveform"][0].detach().cpu().numpy()
    if waveform.ndim == 1:
        waveform = waveform[np.newaxis, :]
    pcm16 = (np.clip(waveform, -1.0, 1.0).T * 32767.0).astype(np.int16, copy=False)
    channels = int(pcm16.shape[1]) if pcm16.ndim == 2 else 1
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(audio["sample_rate"]))
        wav_file.writeframes(pcm16.tobytes())
    return output_path


def _mux_video_with_audio(video_path, audio_path, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-i", video_path, "-i", str(audio_path), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(output_path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def _write_json(output_path, payload):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _persist_llm_artifacts(output_dir, prefix, info, text, extra_meta):
    if not info:
        return
    payload = {
        "trace_id": info.get("trace_id", ""),
        "provider": info.get("provider", ""),
        "model": info.get("model", ""),
        "mode": info.get("mode", ""),
        "context_sha256": info.get("context_sha256", ""),
        "authoring_context_sha256": info.get("authoring_context_sha256", ""),
        "authoring_context": info.get("authoring_context"),
        "request": info.get("request"),
        "response": info.get("response", text),
        "response_meta": info.get("response_meta", {}),
        "meta": extra_meta,
    }
    _write_json(output_dir / f"llm_{prefix}_request.json", {
        "trace_id": payload["trace_id"],
        "provider": payload["provider"],
        "model": payload["model"],
        "mode": payload["mode"],
        "context_sha256": payload["context_sha256"],
        "authoring_context_sha256": payload["authoring_context_sha256"],
        "authoring_context": payload["authoring_context"],
        "request": payload["request"],
        "meta": extra_meta,
    })
    _write_json(output_dir / f"llm_{prefix}_response.json", {
        "trace_id": payload["trace_id"],
        "provider": payload["provider"],
        "model": payload["model"],
        "mode": payload["mode"],
        "context_sha256": payload["context_sha256"],
        "authoring_context_sha256": payload["authoring_context_sha256"],
        "response": payload["response"],
        "response_meta": payload["response_meta"],
        "meta": extra_meta,
    })
    _write_json(output_dir / f"resolved_{prefix}.meta.json", payload)


def _parse_json_maybe(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _build_parser():
    parser = argparse.ArgumentParser(description="Run AOG music pipeline on top of an externally rendered SVI video.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--theme", default="")
    parser.add_argument("--tags", default="")
    parser.add_argument("--lyrics", default="")
    parser.add_argument("--lyrics-file", default="")
    parser.add_argument("--prompt-mode", default="human", choices=["human", "llm"])
    parser.add_argument("--lyrics-mode", default="human", choices=["human", "llm"])
    parser.add_argument("--authoring-language", default="")
    parser.add_argument("--lyrics-language", default="")
    parser.add_argument("--ace-language", default="ja")
    parser.add_argument("--llm-provider", default="qwenvl", choices=["qwenvl", "local_qwen"])
    parser.add_argument("--llm-model", default="models/text_encoders/qwen_4b_ace15.safetensors")
    parser.add_argument("--negative-tags", default="silence, clipping, distortion, noise")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--bpm", type=int, default=120)
    parser.add_argument("--timesignature", default="4", choices=["2", "3", "4", "6"])
    parser.add_argument("--keyscale", default="A minor")
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--cfg", type=float, default=1.0)
    parser.add_argument("--text-cfg-scale", type=float, default=5.0)
    parser.add_argument("--sampler-name", default="euler")
    parser.add_argument("--scheduler", default="simple")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--max-seconds", type=float, default=0.0)
    parser.add_argument("--video-force-rate", type=float, default=0.0)
    parser.add_argument("--analysis-width", type=int, default=640)
    parser.add_argument("--sfx-mode", default="off", choices=["off", "auto"])
    parser.add_argument("--sfx-prompt", default="anime opening impact swells, whooshes, risers, accent hits")
    parser.add_argument("--sfx-negative-prompt", default="spoken dialogue, vocals, muddy bass, clipping")
    parser.add_argument("--sfx-steps", type=int, default=8)
    parser.add_argument("--sfx-cfg", type=float, default=3.5)
    parser.add_argument("--sfx-gain", type=float, default=0.35)
    parser.add_argument("--sfx-mask-away-clip", action="store_true", default=True)
    parser.add_argument("--no-sfx-mask-away-clip", dest="sfx_mask_away_clip", action="store_false")
    parser.add_argument("--mmaudio-model", default="mmaudio_large_44k_v2_fp16.safetensors")
    parser.add_argument("--qwenvl-model", default="")
    parser.add_argument("--qwenvl-quantization", default="None (FP16)")
    parser.add_argument("--qwenvl-attention-mode", default="auto")
    parser.add_argument("--qwenvl-frame-count", type=int, default=16)
    parser.add_argument("--qwenvl-max-tokens", type=int, default=512)
    parser.add_argument("--qwenvl-temperature", type=float, default=0.4)
    parser.add_argument("--qwenvl-top-p", type=float, default=0.9)
    parser.add_argument("--qwenvl-num-beams", type=int, default=1)
    parser.add_argument("--qwenvl-repetition-penalty", type=float, default=1.1)
    parser.add_argument("--qwenvl-keep-model-loaded", action="store_true")
    parser.add_argument("--qwenvl-analysis-prompt", default="")
    parser.add_argument("--ace-model", default="acestep_v1.5_turbo.safetensors")
    parser.add_argument("--ace-clip-small", default="qwen_0.6b_ace15.safetensors")
    parser.add_argument("--ace-clip-large", default="qwen_4b_ace15.safetensors")
    parser.add_argument("--ace-vae", default="ace_1.5_vae.safetensors")
    parser.add_argument("--mmaudio-vae", default="mmaudio_vae_44k_fp16.safetensors")
    parser.add_argument("--mmaudio-synchformer", default="mmaudio_synchformer_fp16.safetensors")
    parser.add_argument("--mmaudio-clip", default="apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors")
    parser.add_argument("--mmaudio-precision", default="fp16", choices=["fp16", "fp32", "bf16"])
    parser.add_argument("--mmaudio-mode", default="44k", choices=["16k", "44k"])
    parser.add_argument("--ace-reference-audio", default="")
    return parser


def _resolve_max_frames(video_path, max_frames, max_seconds, force_rate):
    if max_frames > 0:
        return max_frames
    if max_seconds <= 0:
        return 0
    with av.open(video_path) as container:
        stream = container.streams.video[0]
        fps = float(force_rate) if force_rate > 0 else (float(stream.average_rate) if stream.average_rate is not None else 0.0)
    if fps <= 0:
        return 0
    return max(1, int(round(fps * max_seconds)))


def main():
    args = _build_parser().parse_args()
    authoring_language = args.authoring_language.strip() or args.ace_language
    lyrics_language = args.lyrics_language.strip() or authoring_language
    lyrics = Path(args.lyrics_file).read_text(encoding="utf-8") if args.lyrics_file.strip() else args.lyrics
    sys.path.insert(0, str(COMFY_DIR))
    print("[AOG] importing Comfy and AOG modules...", flush=True)
    import torch
    import comfy.model_management
    import nodes
    from custom_nodes.ComfyUI_AOG.aog import nodes as aog_nodes
    from custom_nodes.ComfyUI_AOG.aog.helpers import build_llm_context, ensure_audio_dict, normalize_audio_duration

    def _load_audio_file(audio_path):
        import numpy as np
        import soundfile as sf
        waveform, sample_rate = sf.read(audio_path, always_2d=True)
        return {"waveform": torch.from_numpy(np.asarray(waveform, dtype="float32").T).unsqueeze(0), "sample_rate": int(sample_rate)}

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_max_frames = _resolve_max_frames(args.video, args.max_frames, args.max_seconds, args.video_force_rate)
    print(f"[AOG] loading video frames: {args.video} (max_frames={resolved_max_frames or 'all'})", flush=True)
    video_batch, _, video_summary_json = aog_nodes.AOGLoadVideoFrames().load_video(args.video, resolved_max_frames, args.video_force_rate, args.analysis_width)
    print("[AOG] loading MMAudio feature bundle...", flush=True)
    mmaudio_featureutils = aog_nodes.AOGMMAudioFeatureBundle().load_bundle(vae_model=args.mmaudio_vae, synchformer_model=args.mmaudio_synchformer, clip_model=args.mmaudio_clip, precision=args.mmaudio_precision, mode=args.mmaudio_mode)[0]
    qwenvl_bundle = None
    if args.prompt_mode == "llm" or args.lyrics_mode == "llm":
        print("[AOG] preparing QwenVL semantic analysis bundle...", flush=True)
        qwenvl_bundle = aog_nodes.AOGQwenVLBundle().load_bundle(
            model_name=args.qwenvl_model or "Qwen3-VL-4B-Instruct",
            quantization=args.qwenvl_quantization,
            attention_mode=args.qwenvl_attention_mode,
            frame_count=args.qwenvl_frame_count,
            max_tokens=args.qwenvl_max_tokens,
            temperature=args.qwenvl_temperature,
            top_p=args.qwenvl_top_p,
            num_beams=args.qwenvl_num_beams,
            repetition_penalty=args.qwenvl_repetition_penalty,
            keep_model_loaded=args.qwenvl_keep_model_loaded,
            seed=max(1, args.seed + 7),
        )[0]
    ace_reference_audio = _load_audio_file(args.ace_reference_audio) if args.ace_reference_audio.strip() else None
    print("[AOG] extracting video features...", flush=True)
    video_features, _ = aog_nodes.AOGVideoFeatureExtract().extract_features(video_batch, mmaudio_featureutils, False)
    if qwenvl_bundle is not None:
        print("[AOG] generating QwenVL scene analysis...", flush=True)
        scene_analysis, _ = aog_nodes.AOGQwenVLSemanticExtract().extract(video_batch, qwenvl_bundle, authoring_language, args.qwenvl_analysis_prompt)
        video_features["qwenvl_scene_analysis"] = scene_analysis
        video_features["qwenvl_analysis_language"] = authoring_language
    print("[AOG] generating prompt...", flush=True)
    resolved_prompt, prompt_json = aog_nodes.AOGPromptDraft().draft(
        video_batch=video_batch,
        video_features=video_features,
        prompt_mode=args.prompt_mode,
        user_prompt=args.tags,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        title=args.title,
        theme=args.theme,
        authoring_language=authoring_language,
        qwenvl_bundle=qwenvl_bundle,
    )
    print("[AOG] generating lyrics...", flush=True)
    resolved_lyrics, lyrics_json = aog_nodes.AOGLyricsDraft().draft(
        video_batch=video_batch,
        video_features=video_features,
        lyrics_mode=args.lyrics_mode,
        user_lyrics=lyrics,
        lyrics_language=lyrics_language,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        title=args.title,
        theme=args.theme,
        authoring_language=authoring_language,
        qwenvl_bundle=qwenvl_bundle,
    )
    comfy.model_management.unload_all_models()
    comfy.model_management.soft_empty_cache(True)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("[AOG] loading ACE-Step UNet...", flush=True)
    ace_model = nodes.UNETLoader().load_unet(args.ace_model, "default")[0]
    print("[AOG] loading ACE-Step dual CLIP...", flush=True)
    ace_clip = nodes.DualCLIPLoader().load_clip(args.ace_clip_small, args.ace_clip_large, "ace", "default")[0]
    print("[AOG] loading ACE-Step VAE...", flush=True)
    ace_vae = nodes.VAELoader().load_vae(args.ace_vae)[0]
    print("[AOG] composing ACE-Step audio...", flush=True)
    ace_audio, ace_json = aog_nodes.AOGAceStepCompose().compose(
        model=ace_model,
        clip=ace_clip,
        vae=ace_vae,
        video_features=video_features,
        prompt_text=resolved_prompt,
        lyrics_text=resolved_lyrics,
        negative_tags=args.negative_tags,
        seed=args.seed,
        bpm=args.bpm,
        duration=video_features["duration_sec"],
        timesignature=args.timesignature,
        ace_language=args.ace_language,
        keyscale=args.keyscale,
        steps=args.steps,
        cfg=args.cfg,
        text_cfg_scale=args.text_cfg_scale,
        sampler_name=args.sampler_name,
        scheduler=args.scheduler,
        denoise=1.0,
        reference_audio=ensure_audio_dict(ace_reference_audio) if ace_reference_audio is not None else None,
    )
    mmaudio_model = None
    if args.sfx_mode == "auto":
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache(True)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("[AOG] loading MMAudio SFX model...", flush=True)
        mmaudio_model = aog_nodes.AOGMMAudioSFXBundle().load_bundle(mmaudio_model=args.mmaudio_model, base_precision=args.mmaudio_precision)[0]
    print("[AOG] composing SFX audio...", flush=True)
    sfx_audio, sfx_json = aog_nodes.AOGSFXCompose().compose(
        video_batch=video_batch,
        video_features=video_features,
        mmaudio_featureutils=mmaudio_featureutils,
        sfx_mode=args.sfx_mode,
        seed=args.seed + 1,
        sfx_prompt=args.sfx_prompt,
        negative_prompt=args.sfx_negative_prompt,
        steps=args.sfx_steps,
        cfg=args.sfx_cfg,
        gain=args.sfx_gain,
        mask_away_clip=args.sfx_mask_away_clip,
        mmaudio_model=mmaudio_model,
    )
    final_audio = aog_nodes.mix_audio_dicts(ace_audio, sfx_audio, gain_b=args.sfx_gain) if args.sfx_mode == "auto" else ace_audio
    summary_json = aog_nodes.to_pretty_json({
        "video_summary": video_features["summary"],
        "timeline": video_features["timeline"],
        "semantic_cues": video_features["semantic_cues"],
        "qwenvl_scene_analysis": video_features.get("qwenvl_scene_analysis", ""),
        "qwenvl_analysis_language": video_features.get("qwenvl_analysis_language", ""),
        "conditioning_summary": video_features["conditioning_summary"],
        "latent_structure_cues": video_features["latent_structure_cues"],
        "prompt_mode": args.prompt_mode,
        "lyrics_mode": args.lyrics_mode,
        "authoring_language": authoring_language,
        "lyrics_language": lyrics_language,
        "ace_language": args.ace_language,
        "llm_provider": args.llm_provider if args.prompt_mode == "llm" or args.lyrics_mode == "llm" else "human",
        "sfx_mode": args.sfx_mode,
        "prompt_summary": prompt_json,
        "lyrics_summary": lyrics_json,
        "ace_summary": ace_json,
        "sfx_summary": sfx_json,
    })
    print("[AOG] saving outputs...", flush=True)
    final_audio = normalize_audio_duration(final_audio, float(video_batch.get("source_duration_sec", video_batch.get("duration_sec", 0.0))))
    ace_audio_path = _save_audio_file(ace_audio, output_dir / "ace_audio.wav")
    sfx_audio_path = None
    if args.sfx_mode == "auto":
        sfx_audio_path = _save_audio_file(sfx_audio, output_dir / "sfx_audio.wav")
    final_audio_path = _save_audio_file(final_audio, output_dir / "final_mix.wav")
    print("[AOG] muxing final video...", flush=True)
    final_video_path = _mux_video_with_audio(args.video, final_audio_path, output_dir / "opening_final.mp4")
    (output_dir / "resolved_prompt.txt").write_text(resolved_prompt, encoding="utf-8-sig")
    (output_dir / "resolved_lyrics.txt").write_text(resolved_lyrics, encoding="utf-8-sig")
    (output_dir / "video_summary.json").write_text(video_summary_json, encoding="utf-8")
    export_features = {k: v for k, v in video_features.items() if k != "conditioning_payload"}
    _write_json(output_dir / "feature_summary.json", export_features)
    authoring_context = build_llm_context(video_features)
    _write_json(output_dir / "authoring_context.json", authoring_context)
    if video_features.get("qwenvl_scene_analysis", ""):
        _write_json(output_dir / "qwenvl_analysis.json", {
            "authoring_language": video_features.get("qwenvl_analysis_language", authoring_language),
            "scene_analysis": video_features.get("qwenvl_scene_analysis", ""),
        })
    summary_payload = json.loads(summary_json)
    prompt_summary = _parse_json_maybe(summary_payload.get("prompt_summary", {}))
    lyrics_summary = _parse_json_maybe(summary_payload.get("lyrics_summary", {}))
    ace_summary = _parse_json_maybe(summary_payload.get("ace_summary", {}))
    sfx_summary = _parse_json_maybe(summary_payload.get("sfx_summary", {}))
    summary_payload["prompt_summary"] = prompt_summary
    summary_payload["lyrics_summary"] = lyrics_summary
    summary_payload["ace_summary"] = ace_summary
    summary_payload["sfx_summary"] = sfx_summary
    prompt_llm_info = prompt_summary.get("llm_info") if isinstance(prompt_summary, dict) else None
    lyrics_llm_info = lyrics_summary.get("llm_info") if isinstance(lyrics_summary, dict) else None
    _persist_llm_artifacts(
        output_dir,
        "prompt",
        prompt_llm_info,
        resolved_prompt,
        {
            "title": args.title,
            "theme": args.theme,
            "source_video": args.video,
            "authoring_language": authoring_language,
            "lyrics_language": lyrics_language,
            "ace_language": args.ace_language,
        },
    )
    _persist_llm_artifacts(
        output_dir,
        "lyrics",
        lyrics_llm_info,
        resolved_lyrics,
        {
            "title": args.title,
            "theme": args.theme,
            "source_video": args.video,
            "authoring_language": authoring_language,
            "lyrics_language": lyrics_language,
            "ace_language": args.ace_language,
        },
    )
    summary_payload["authoring_artifacts"] = {
        "authoring_context_path": str(output_dir / "authoring_context.json"),
        "qwenvl_analysis_path": str(output_dir / "qwenvl_analysis.json") if video_features.get("qwenvl_scene_analysis", "") else "",
        "prompt_request_path": str(output_dir / "llm_prompt_request.json") if prompt_llm_info else "",
        "prompt_response_path": str(output_dir / "llm_prompt_response.json") if prompt_llm_info else "",
        "lyrics_request_path": str(output_dir / "llm_lyrics_request.json") if lyrics_llm_info else "",
        "lyrics_response_path": str(output_dir / "llm_lyrics_response.json") if lyrics_llm_info else "",
        "prompt_trace_id": prompt_llm_info.get("trace_id", "") if prompt_llm_info else "",
        "lyrics_trace_id": lyrics_llm_info.get("trace_id", "") if lyrics_llm_info else "",
        "context_sha256": authoring_context.get("context_sha256", ""),
    }
    _write_json(output_dir / "run_summary.json", summary_payload)
    print(json.dumps({"status": "ok", "video": args.video, "output_dir": str(output_dir), "ace_audio": str(ace_audio_path), "sfx_audio": str(sfx_audio_path) if sfx_audio_path else "", "final_audio": str(final_audio_path), "final_video": str(final_video_path), "prompt_mode": args.prompt_mode, "lyrics_mode": args.lyrics_mode, "sfx_mode": args.sfx_mode}, ensure_ascii=False, indent=2))
    torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
