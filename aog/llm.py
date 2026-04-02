"""AOG의 프롬프트, 가사, 음악 메타데이터 생성을 담당하는 LLM 유틸리티."""

import json
import re
import types
from functools import lru_cache
from pathlib import Path
from typing import Any

from .helpers import build_llm_context


class LLMGenerationError(RuntimeError):
    """LLM 호출과 응답 파싱 과정에서 발생하는 예외."""
    pass


ROOT_DIR = Path(__file__).resolve().parents[1]
COMFY_DIR = ROOT_DIR.parent.parent
DEFAULT_QWEN_MODEL_PATH = COMFY_DIR / "models" / "text_encoders" / "qwen_4b_ace15.safetensors"
DEFAULT_QWEN_TOKENIZER_PATH = COMFY_DIR / "comfy" / "text_encoders" / "qwen25_tokenizer"


@lru_cache(maxsize=1)
def _load_local_qwen_runtime(model_path: str) -> tuple[Any, Any, str]:
    """로컬 Qwen 체크포인트와 토크나이저를 로드해 재사용한다.

    Args:
        model_path: 로드할 safetensors 체크포인트 경로.

    Returns:
        `(model, tokenizer, resolved_model_path)` 튜플.
    """
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
    """로컬 Qwen을 호출해 단일 텍스트 응답과 디버그 정보를 반환한다.

    Args:
        system_prompt: 시스템 프롬프트.
        user_prompt: 사용자 프롬프트.
        model_path: 사용할 로컬 Qwen 모델 경로.
        max_new_tokens: 최대 생성 토큰 수.
        seed: 생성 시드.
        temperature: 샘플링 temperature.
        top_p: nucleus sampling 비율.

    Returns:
        `(text, info)` 튜플. `text`는 생성 결과, `info`는 요청/응답 메타데이터.
    """
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


def _extract_json_object(text: str) -> dict[str, Any]:
    """LLM 응답 본문에서 첫 번째 JSON 객체를 찾아 파싱한다.

    Args:
        text: LLM이 반환한 원문.

    Returns:
        파싱된 JSON 객체 딕셔너리.
    """
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise LLMGenerationError("LLM response did not contain a JSON object.")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMGenerationError(f"Failed to parse LLM JSON response: {exc}") from exc
    if not isinstance(payload, dict):
        raise LLMGenerationError("Parsed LLM response was not a JSON object.")
    return payload


def generate_prompt(
    video_features: dict[str, Any],
    user_prompt: str,
    provider: str,
    model: str = "",
    language: str = "",
) -> tuple[str, dict[str, Any]]:
    """영상 컨텍스트를 바탕으로 ACE-Step용 프롬프트를 생성한다.

    Args:
        video_features: AOG video feature contract 딕셔너리.
        user_prompt: 사람이 직접 작성한 프롬프트.
        provider: `human` 또는 `local_qwen`.
        model: 로컬 Qwen 모델 경로.
        language: 작성 언어.

    Returns:
        `(prompt_text, info)` 튜플.
    """
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
    authoring_language: str = "",
) -> tuple[str, dict[str, Any]]:
    """영상 컨텍스트를 바탕으로 ACE-Step용 가사를 생성한다.

    Args:
        video_features: AOG video feature contract 딕셔너리.
        user_lyrics: 사람이 직접 작성한 가사.
        language: 최종 가사 언어.
        provider: `human` 또는 `local_qwen`.
        model: 로컬 Qwen 모델 경로.
        authoring_language: LLM이 분석/작성에 사용할 언어.

    Returns:
        `(lyrics_text, info)` 튜플.
    """
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


def generate_music_plan(
    video_features: dict[str, Any],
    *,
    provider: str,
    model: str = "",
    authoring_language: str = "",
    lyrics_language: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """영상 컨텍스트를 바탕으로 BPM/박자/조성/가창 언어를 계획한다.

    Args:
        video_features: AOG video feature contract 딕셔너리.
        provider: 현재는 `local_qwen`만 지원한다.
        model: 로컬 Qwen 모델 경로.
        authoring_language: 분석/설명 언어.
        lyrics_language: 요청된 가사 언어.

    Returns:
        `(plan, info)` 튜플. `plan`에는 bpm, timesignature, keyscale, ace_language가 포함된다.
    """
    if provider != "local_qwen":
        raise LLMGenerationError(f"Unsupported llm provider: {provider}")

    context = build_llm_context(video_features)
    system_prompt = (
        "You are an anime opening music planner for ACE-Step. "
        "Given the video context, choose musically appropriate metadata for the song. "
        "Return JSON only with keys: bpm, timesignature, keyscale, ace_language, rationale. "
        "Rules: bpm must be an integer between 60 and 210. "
        "timesignature must be one of 2, 3, 4, 6 as a string. "
        "keyscale must be one of common major/minor musical keys such as A minor or C major. "
        "ace_language must be the singing language and should normally match the requested lyrics language."
    )
    user_prompt_text = (
        f"Authoring language: {authoring_language}\n"
        f"Requested lyrics language: {lyrics_language}\n"
        f"Video context: {json.dumps(context, ensure_ascii=False)}"
    )
    raw_text, info = _generate_local_text(
        system_prompt=system_prompt,
        user_prompt=user_prompt_text,
        model_path=model,
        max_new_tokens=120,
        seed=2,
        temperature=0.4,
        top_p=0.9,
    )
    payload = _extract_json_object(raw_text)
    try:
        plan = {
            "bpm": int(payload["bpm"]),
            "timesignature": str(payload["timesignature"]),
            "keyscale": str(payload["keyscale"]),
            "ace_language": str(payload.get("ace_language") or lyrics_language),
            "rationale": str(payload.get("rationale", "")).strip(),
        }
    except Exception as exc:
        raise LLMGenerationError(f"LLM music plan response missing required fields: {exc}") from exc
    info.update({"mode": "llm", "context": context, "response_json": payload})
    return plan, info


def generate_sfx_prompt(
    video_features: dict[str, Any],
    user_prompt: str,
    provider: str,
    model: str = "",
    authoring_language: str = "",
) -> tuple[str, dict[str, Any]]:
    """영상 특징을 바탕으로 MMAudio SFX 프롬프트를 생성한다.

    Args:
        video_features: AOG video feature contract 딕셔너리.
        user_prompt: 사람이 직접 작성한 SFX 프롬프트.
        provider: `human` 또는 `local_qwen`.
        model: 로컬 Qwen 모델 경로.
        authoring_language: 분석 및 작성에 사용할 언어.

    Returns:
        `(sfx_prompt, info)` 튜플.
    """
    if provider == "human":
        prompt = user_prompt.strip()
        if not prompt:
            raise LLMGenerationError("sfx_prompt_mode=human requires a non-empty SFX prompt.")
        return prompt, {"provider": "human", "mode": "human", "request": None, "response": prompt}

    if provider != "local_qwen":
        raise LLMGenerationError(f"Unsupported llm provider: {provider}")

    context = build_llm_context(video_features)
    system_prompt = (
        "You write concise MMAudio SFX prompts for anime openings. "
        "Focus on transition hits, whooshes, risers, impacts, swells, accent moments, and motion-synced effects. "
        "Do not describe a music bed. Do not request vocals or dialogue. "
        "Return plain text only in the requested language."
    )
    user_prompt_text = (
        f"Authoring language: {authoring_language}\n"
        f"Video context: {json.dumps(context, ensure_ascii=False)}"
    )
    text, info = _generate_local_text(
        system_prompt=system_prompt,
        user_prompt=user_prompt_text,
        model_path=model,
        max_new_tokens=96,
        seed=3,
        temperature=0.6,
        top_p=0.9,
    )
    info.update({"mode": "llm", "context": context})
    return text, info


def generate_sfx_prompt(
    video_features: dict[str, Any],
    user_prompt: str,
    *,
    provider: str,
    model: str = "",
    authoring_language: str = "",
) -> tuple[str, dict[str, Any]]:
    """영상 컨텍스트를 바탕으로 MMAudio용 SFX 프롬프트를 생성한다.

    Args:
        video_features: AOG video feature contract 딕셔너리.
        user_prompt: 사람이 직접 작성한 SFX 프롬프트.
        provider: `human` 또는 `local_qwen`.
        model: 로컬 Qwen 모델 경로.
        authoring_language: LLM이 분석/작성에 사용할 언어.

    Returns:
        `(sfx_prompt, info)` 튜플.
    """
    if provider == "human":
        prompt = user_prompt.strip()
        if not prompt:
            raise LLMGenerationError("sfx_prompt_mode=human requires a non-empty SFX prompt.")
        return prompt, {"provider": "human", "mode": "human", "request": None, "response": prompt}

    if provider != "local_qwen":
        raise LLMGenerationError(f"Unsupported llm provider: {provider}")

    context = build_llm_context(video_features)
    system_prompt = (
        "You write concise MMAudio SFX prompts for anime opening videos. "
        "Describe only non-musical cinematic sound design cues such as risers, whooshes, impacts, sweeps, hit accents, "
        "transition swells, glitch accents, and motion-synced texture layers. "
        "Do not mention vocals or dialogue. Return plain text only."
    )
    user_prompt_text = (
        f"Language: {authoring_language or 'en'}\n"
        f"Video context: {json.dumps(context, ensure_ascii=False)}"
    )
    text, info = _generate_local_text(
        system_prompt=system_prompt,
        user_prompt=user_prompt_text,
        model_path=model,
        max_new_tokens=96,
        seed=3,
        temperature=0.6,
        top_p=0.9,
    )
    info.update({"mode": "llm", "context": context})
    return text, info
