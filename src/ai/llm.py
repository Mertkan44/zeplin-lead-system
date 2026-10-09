from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import httpx

from src.config import env, groq_client, required_env


@dataclass(frozen=True)
class LLMResult:
    content: str
    provider: str
    model: str
    usage: dict[str, Any] | None = None


# Called once per provider request: on_attempt(provider=, model=, outcome=, usage=, error=)
# with outcome success | empty | error. A fallback is a second attempt.
AttemptHook = Callable[..., None]


def _report(hook: AttemptHook | None, **attempt: Any) -> None:
    if hook:
        hook(**attempt)


def active_provider() -> str:
    configured = (env("AI_PROVIDER") or "").strip().lower()
    if configured:
        return configured
    if env("DEEPSEEK_API_KEY"):
        return "deepseek"
    if env("GROQ_API_KEY"):
        return "groq"
    return "deepseek"


def complete_chat(
    system: str,
    prompt: str,
    *,
    max_tokens: int = 700,
    temperature: float = 0.35,
    json_output: bool = False,
    model: str | None = None,
    reasoning_effort: str | None = None,
    on_attempt: AttemptHook | None = None,
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
            on_attempt=on_attempt,
        )
    if provider == "groq":
        return _groq_chat(
            system,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            json_output=json_output,
            model=model,
            on_attempt=on_attempt,
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
    on_attempt: AttemptHook | None = None,
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
        thinking_mode = (env("DEEPSEEK_THINKING_MODE", "disabled") or "disabled").lower()
        thinking_enabled = thinking_mode == "enabled" or reasoning_effort == "max"
        payload["thinking"] = {"type": "enabled" if thinking_enabled else "disabled"}
        if thinking_enabled:
            payload["reasoning_effort"] = reasoning_effort or "high"
        else:
            payload["temperature"] = temperature
    else:
        payload["temperature"] = temperature

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    def _call(request_payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        """One request, reported to on_attempt whatever happens."""
        attempt_model = request_payload["model"]
        try:
            with httpx.Client(timeout=90) as client:
                response = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=request_payload,
                )
                if response.status_code == 402:
                    raise RuntimeError("DeepSeek account has no available balance or billing is not enabled.")
                response.raise_for_status()
                data = response.json()
            content = ((data["choices"][0].get("message") or {}).get("content") or "").strip()
        except Exception as exc:
            _report(on_attempt, provider="deepseek", model=attempt_model, outcome="error", usage=None,
                    error=f"{type(exc).__name__}: {exc}"[:300])
            raise
        _report(on_attempt, provider="deepseek", model=attempt_model,
                outcome="success" if content else "empty", usage=data.get("usage"), error=None)
        return content, data.get("usage")

    try:
        content, usage = _call(payload)
    except RuntimeError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError):
        content, usage = "", None
    if content:
        return LLMResult(content=content, provider="deepseek", model=model, usage=usage)

    fallback_model = env("DEEPSEEK_FLASH_MODEL", "deepseek-v4-flash") or "deepseek-v4-flash"
    fallback_payload: dict[str, Any] = {
        "model": fallback_model,
        "messages": payload["messages"],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if fallback_model.startswith("deepseek-v4"):
        fallback_payload["thinking"] = {"type": "disabled"}
    if json_output:
        fallback_payload["response_format"] = {"type": "json_object"}
    fallback_content, fallback_usage = _call(fallback_payload)
    if not fallback_content:
        raise RuntimeError(
            "AI provider returned an empty response even after flash fallback."
        )
    return LLMResult(
        content=fallback_content,
        provider="deepseek",
        model=fallback_model,
        usage=fallback_usage,
    )


def _groq_chat(
    system: str,
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
    json_output: bool,
    model: str | None,
    on_attempt: AttemptHook | None = None,
) -> LLMResult:
    model = model or env("GROQ_MODEL", "llama-3.3-70b-versatile") or "llama-3.3-70b-versatile"
    kwargs: dict[str, Any] = {}
    if json_output:
        kwargs["response_format"] = {"type": "json_object"}
    try:
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
    except Exception as exc:
        _report(on_attempt, provider="groq", model=model, outcome="error", usage=None,
                error=f"{type(exc).__name__}: {exc}"[:300])
        raise
    content = (response.choices[0].message.content or "").strip()
    usage = getattr(response, "usage", None)
    usage = usage.model_dump() if hasattr(usage, "model_dump") else None
    _report(on_attempt, provider="groq", model=model, outcome="success" if content else "empty", usage=usage, error=None)
    return LLMResult(content=content, provider="groq", model=model, usage=usage)
