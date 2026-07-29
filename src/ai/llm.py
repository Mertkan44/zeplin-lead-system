from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from src.config import env, groq_client, required_env


@dataclass(frozen=True)
class LLMResult:
    content: str
    provider: str
    model: str
    usage: dict[str, Any] | None = None


def active_provider() -> str:
    return (env("AI_PROVIDER", "groq") or "groq").strip().lower()


def complete_chat(
    system: str,
    prompt: str,
    *,
    max_tokens: int = 700,
    temperature: float = 0.35,
    json_output: bool = False,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> LLMResult:
    provider = active_provider()
    if provider == "deepseek":
        return _deepseek_chat(
            system,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            json_output=json_output,
            model=model,
            reasoning_effort=reasoning_effort,
        )
    if provider == "groq":
        return _groq_chat(
            system,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            json_output=json_output,
            model=model,
        )
    raise RuntimeError(f"Unsupported AI_PROVIDER: {provider}")


def _deepseek_chat(
    system: str,
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
    json_output: bool,
    model: str | None,
    reasoning_effort: str | None,
) -> LLMResult:
    api_key = required_env("DEEPSEEK_API_KEY")
    base_url = (env("DEEPSEEK_BASE_URL", "https://api.deepseek.com") or "").rstrip("/")
    model = model or env("DEEPSEEK_MODEL", "deepseek-v4-pro") or "deepseek-v4-pro"
    reasoning_effort = reasoning_effort or env("DEEPSEEK_REASONING_EFFORT", "high") or "high"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_output:
        payload["response_format"] = {"type": "json_object"}
    if model.startswith("deepseek-v4"):
        payload["reasoning_effort"] = "high"
        payload["thinking"] = {"type": "enabled"}
    else:
        payload["temperature"] = temperature

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    def _call(request_payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=90) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=request_payload,
            )
            if response.status_code == 402:
                raise RuntimeError("DeepSeek account has no available balance or billing is not enabled.")
            response.raise_for_status()
            return response.json()

    data = None
    try:
        data = _call(payload)
    except RuntimeError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError):
        data = None
    if data:
        choice = data["choices"][0]
        content = (choice.get("message") or {}).get("content") or ""
        if content.strip():
            return LLMResult(content=content.strip(), provider="deepseek", model=model, usage=data.get("usage"))

    fallback_model = env("DEEPSEEK_FLASH_MODEL", "deepseek-v4-flash") or "deepseek-v4-flash"
    fallback_payload: dict[str, Any] = {
        "model": fallback_model,
        "messages": payload["messages"],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if json_output:
        fallback_payload["response_format"] = {"type": "json_object"}
    fallback_data = _call(fallback_payload)
    fallback_choice = fallback_data["choices"][0]
    fallback_content = (fallback_choice.get("message") or {}).get("content") or ""
    if not fallback_content.strip():
        raise RuntimeError(
            "AI provider returned an empty response even after flash fallback."
        )
    return LLMResult(
        content=fallback_content.strip(),
        provider="deepseek",
        model=fallback_model,
        usage=fallback_data.get("usage"),
    )


def _groq_chat(
    system: str,
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
    json_output: bool,
    model: str | None,
) -> LLMResult:
    model = model or env("GROQ_MODEL", "llama-3.3-70b-versatile") or "llama-3.3-70b-versatile"
    kwargs: dict[str, Any] = {}
    if json_output:
        kwargs["response_format"] = {"type": "json_object"}
    response = groq_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        **kwargs,
    )
    content = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    return LLMResult(
        content=content.strip(),
        provider="groq",
        model=model,
        usage=usage.model_dump() if hasattr(usage, "model_dump") else None,
    )
