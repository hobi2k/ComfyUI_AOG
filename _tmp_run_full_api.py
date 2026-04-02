import json
import time
import urllib.error
import urllib.request
from pathlib import Path


SERVER = "http://127.0.0.1:8188"
INPUT_VIDEO = r"D:\Stable Diffusion\StabilityMatrix-win-x64\Data\Packages\ComfyUI\input\120752-01_00001.webm"


def post_json(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{SERVER}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {path}: {body}") from exc


def get_json(path):
    with urllib.request.urlopen(f"{SERVER}{path}", timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_for_prompt(prompt_id, timeout_sec=3600):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            history = get_json(f"/history/{prompt_id}")
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2)
            continue
        if prompt_id in history:
            return history[prompt_id]
        time.sleep(2)
    raise TimeoutError(f"prompt {prompt_id} did not finish in time")


def build_prompt():
    return {
        "1": {
            "class_type": "AOG Load Video Frames",
            "inputs": {
                "video_path": INPUT_VIDEO,
                "max_frames": 0,
                "force_rate": 8.0,
                "analysis_width": 640,
            },
        },
        "2": {
            "class_type": "AOG MMAudio Feature Bundle",
            "inputs": {
                "vae_model": "mmaudio_vae_44k_fp16.safetensors",
                "synchformer_model": "mmaudio_synchformer_fp16.safetensors",
                "clip_model": "apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors",
                "mode": "44k",
                "precision": "fp16",
            },
        },
        "3": {
            "class_type": "AOG QwenVL Bundle",
            "inputs": {
                "model_name": "Qwen3-VL-4B-Instruct",
                "quantization": "None (FP16)",
                "attention_mode": "auto",
                "frame_count": 8,
                "max_tokens": 512,
                "temperature": 0.4,
                "top_p": 0.9,
                "num_beams": 1,
                "repetition_penalty": 1.1,
                "keep_model_loaded": True,
                "seed": 1,
            },
        },
        "4": {
            "class_type": "AOG Video Feature Extract",
            "inputs": {
                "enabled": True,
                "video_batch": ["1", 0],
                "mmaudio_featureutils": ["2", 0],
                "mask_away_clip": False,
            },
        },
        "5": {
            "class_type": "AOG QwenVL Semantic Extract",
            "inputs": {
                "enabled": True,
                "video_batch": ["1", 0],
                "qwenvl_bundle": ["3", 0],
                "authoring_language": "en",
                "analysis_prompt": "",
            },
        },
        "6": {
            "class_type": "AOG Prompt Draft",
            "inputs": {
                "enabled": True,
                "video_batch": ["1", 0],
                "video_features": ["4", 0],
                "prompt_mode": "llm",
                "user_prompt": "",
                "llm_provider": "qwenvl",
                "authoring_language": "en",
                "qwenvl_bundle": ["3", 0],
            },
        },
        "7": {
            "class_type": "AOG Lyrics Draft",
            "inputs": {
                "enabled": True,
                "video_batch": ["1", 0],
                "video_features": ["4", 0],
                "lyrics_mode": "llm",
                "user_lyrics": "",
                "lyrics_language": "ja",
                "llm_provider": "qwenvl",
                "authoring_language": "en",
                "qwenvl_bundle": ["3", 0],
            },
        },
        "8": {
            "class_type": "AOG Music Plan",
            "inputs": {
                "enabled": True,
                "video_batch": ["1", 0],
                "video_features": ["4", 0],
                "plan_mode": "llm",
                "llm_provider": "qwenvl",
                "authoring_language": "en",
                "lyrics_language": "ja",
                "manual_bpm": 120,
                "manual_timesignature": "4",
                "manual_keyscale": "A minor",
                "manual_ace_language": "ja",
                "qwenvl_bundle": ["3", 0],
            },
        },
        "9": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "acestep_v1.5_turbo.safetensors",
                "weight_dtype": "default",
            },
        },
        "10": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": "qwen_0.6b_ace15.safetensors",
                "clip_name2": "qwen_4b_ace15.safetensors",
                "type": "ace",
                "device": "default",
            },
        },
        "11": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": "ace_1.5_vae.safetensors",
            },
        },
        "12": {
            "class_type": "AOG ACE-Step Compose",
            "inputs": {
                "enabled": True,
                "model": ["9", 0],
                "clip": ["10", 0],
                "vae": ["11", 0],
                "video_features": ["4", 0],
                "prompt_text": ["6", 0],
                "lyrics_text": ["7", 0],
                "negative_tags": "silence, clipping, distortion, noise",
                "seed": 0,
                "bpm": ["8", 0],
                "duration": ["8", 1],
                "timesignature": ["8", 2],
                "ace_language": ["8", 3],
                "keyscale": ["8", 4],
                "steps": 8,
                "cfg": 1.0,
                "text_cfg_scale": 5.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "13": {
            "class_type": "AOG MMAudio SFX Bundle",
            "inputs": {
                "mmaudio_model": "mmaudio_large_44k_v2_fp16.safetensors",
                "base_precision": "fp16",
            },
        },
        "14": {
            "class_type": "AOG SFX Compose",
            "inputs": {
                "enabled": True,
                "video_batch": ["1", 0],
                "video_features": ["4", 0],
                "mmaudio_featureutils": ["2", 0],
                "sfx_mode": "auto",
                "seed": 1,
                "sfx_prompt": "anime opening impact swells, whooshes, risers, accent hits",
                "negative_prompt": "spoken dialogue, vocals, muddy bass, clipping",
                "steps": 8,
                "cfg": 3.5,
                "gain": 0.25,
                "mask_away_clip": True,
                "mmaudio_model": ["13", 0],
            },
        },
        "15": {
            "class_type": "AOG Final Audio Mix",
            "inputs": {
                "ace_audio": ["12", 0],
                "sfx_audio": ["14", 0],
                "enable_sfx": True,
                "sfx_mode": "auto",
                "sfx_gain": 0.25,
            },
        },
        "16": {
            "class_type": "AOG Save Summary JSON",
            "inputs": {
                "enabled": True,
                "summary_json": ["15", 1],
                "filename_prefix": "AOG/full_music_sfx_summary_api",
            },
        },
        "17": {
            "class_type": "AOG Preview Video Combine",
            "inputs": {
                "enabled": True,
                "video_batch": ["1", 0],
                "audio": ["15", 0],
                "filename_prefix": "AOG/full_music_sfx_preview_api",
                "format": "video/mp4",
                "save_output": True,
                "pingpong": False,
                "loop_count": 0,
            },
        },
    }


def main():
    payload = {
        "prompt": build_prompt(),
        "client_id": "aog-direct-api",
    }
    response = post_json("/prompt", payload)
    prompt_id = response["prompt_id"]
    print(f"queued: {prompt_id}")
    history = wait_for_prompt(prompt_id)
    print(json.dumps(history, ensure_ascii=False, indent=2)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
