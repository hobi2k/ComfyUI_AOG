import json
import types
from functools import lru_cache
from pathlib import Path
from typing import Any

from .helpers import build_llm_context


class LLMGenerationError(RuntimeError):
    pass


ROOT_DIR = Path(__file__).resolve().parents[1]
COMFY_DIR = ROOT_DIR.parent.parent
DEFAULT_QWEN_MODEL_PATH = COMFY_DIR / "models" / "text_encoders" / "qwen_4b_ace15.safetensors"
DEFAULT_QWEN_TOKENIZER_PATH = COMFY_DIR / "comfy" / "text_encoders" / "qwen25_tokenizer"


@lru_cache(maxsize=1)
def _load_local_qwen_runtime(model_path: str) -> tuple[Any, Any, str]:
    import torch
    import comfy.model_management
    import comfy.ops
    import comfy.utils
    from comfy.text_encoders import llama
    from transformers import Qwen2Tokenizer

    resolved_model_path = Path(model_path or DEFAULT_QWEN_MODEL_PATH).resolve()
    if not resolved_model_path.exists():
        raise LLMGenerationError(f"Local Qwen model not found: {resolved_model_path}")

    tokenizer = Qwen2Tokenizer.from_pretrained(str(DEFAULT_QWEN_TOKENIZER_PATH))
    device = comfy.model_management.get_torch_device()
    dtype = torch.bfloat16 if comfy.model_management.should_use_bf16(device) else torch.float16
    model = llama.Qwen3_4B_ACE15_lm({}, dtype, device, comfy.ops.manual_cast)
    state_dict = comfy.utils.load_torch_file(str(resolved_model_path), safe_load=True)
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    if missing or unexpected:
        raise LLMGenerationError(
            f"Failed to load local Qwen weights cleanly. missing={len(missing)} unexpected={len(unexpected)}"
        )
    model.generate = types.MethodType(llama.BaseGenerate.generate, model)
    model.sample_token = types.MethodType(llama.BaseGenerate.sample_token, model)
    model.eval()
    return model, tokenizer, str(resolved_model_path)


def _generate_local_text(
    *,
    system_prompt: str,
    user_prompt: str,
    model_path: str,
    max_new_tokens: int,
    seed: int,
    temperature: float,
    top_p: float,
) -> tuple[str, dict[str, Any]]:
    import torch
    import comfy.model_management

    model, tokenizer, resolved_model_path = _load_local_qwen_runtime(model_path)
    device = comfy.model_management.get_torch_device()
    offload_device = comfy.model_management.unet_offload_device()
    model.to(device)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    if hasattr(tokenizer, "apply_chat_template"):
        prompt_text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    else:
        prompt_text = f"{system_prompt}\n\n{user_prompt}"
    token_ids = tokenizer.encode(prompt_text, add_special_tokens=False)
    if not token_ids:
        raise LLMGenerationError("Local Qwen request prompt encoded to zero tokens.")
    ids = torch.tensor(token_ids, device=device, dtype=torch.long).unsqueeze(0)
    with torch.no_grad():
        embeds = model.model.embed_tokens(ids)
        generated_ids = model.generate(
            embeds=embeds,
            do_sample=True,
            max_length=max_new_tokens,
            temperature=temperature,
            top_k=0,
            top_p=top_p,
            min_p=0.0,
            repetition_penalty=1.02,
            seed=seed,
        )
    text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
    model.to(offload_device)
    comfy.model_management.soft_empty_cache(True)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    if not text:
        raise LLMGenerationError("Local Qwen returned an empty response.")
    return text, {
        "provider": "local_qwen",
        "model": resolved_model_path,
        "request": {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "prompt_text": prompt_text,
            "max_new_tokens": max_new_tokens,
            "seed": seed,
            "temperature": temperature,
            "top_p": top_p,
        },
        "response": text,
    }


def generate_prompt(
    video_features: dict[str, Any],
    user_prompt: str,
    provider: str,
    model: str = "",
    title: str = "",
    theme: str = "",
    language: str = "",
) -> tuple[str, dict[str, Any]]:
    if provider == "human":
        prompt = user_prompt.strip()
        if not prompt:
            raise LLMGenerationError("prompt_mode=human requires a non-empty prompt.")
        return prompt, {"provider": "human", "mode": "human", "request": None, "response": prompt}

    if provider != "local_qwen":
        raise LLMGenerationError(f"Unsupported llm provider: {provider}")

    context = build_llm_context(video_features)
    system_prompt = (
        "You write concise, high-quality ACE-Step prompts for anime openings. "
        "Use the video context to describe instrumentation, pacing, rises, drops, emotional arc, and scene-driven musical shifts. "
        "Write in the requested language. Return plain text only."
    )
    user_prompt_text = (
        f"Language: {language}\n"
        f"Title: {title}\n"
        f"Theme: {theme}\n"
        f"Video context: {json.dumps(context, ensure_ascii=False)}"
    )
    text, info = _generate_local_text(
        system_prompt=system_prompt,
        user_prompt=user_prompt_text,
        model_path=model,
        max_new_tokens=96,
        seed=0,
        temperature=0.7,
        top_p=0.9,
    )
    info.update({"mode": "llm", "context": context})
    return text, info


def generate_lyrics(
    video_features: dict[str, Any],
    user_lyrics: str,
    language: str,
    provider: str,
    model: str = "",
    title: str = "",
    theme: str = "",
    authoring_language: str = "",
) -> tuple[str, dict[str, Any]]:
    if provider == "human":
        lyrics = user_lyrics.strip()
        if not lyrics:
            raise LLMGenerationError("lyrics_mode=human requires non-empty lyrics.")
        return lyrics, {"provider": "human", "mode": "human", "lyrics_language": language, "request": None, "response": lyrics}

    if provider != "local_qwen":
        raise LLMGenerationError(f"Unsupported llm provider: {provider}")

    context = build_llm_context(video_features)
    system_prompt = (
        "You write singable ACE-Step lyrics for anime openings. "
        "Use labeled sections like [Verse], [Pre-Chorus], [Chorus]. "
        "Respect the requested language and the video timing and emotional arc. "
        "Return plain text only."
    )
    user_prompt_text = (
        f"Language: {authoring_language or language}\n"
        f"Title: {title}\n"
        f"Theme: {theme}\n"
        f"Video context: {json.dumps(context, ensure_ascii=False)}"
    )
    text, info = _generate_local_text(
        system_prompt=system_prompt,
        user_prompt=user_prompt_text,
        model_path=model,
        max_new_tokens=220,
        seed=1,
        temperature=0.8,
        top_p=0.92,
    )
    info.update({"mode": "llm", "lyrics_language": language, "context": context})
    return text, info
