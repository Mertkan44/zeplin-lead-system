"""AI generation cache: one paid call per (task, model, input).

The key covers the task, provider, requested model, a hash of the exact
system + user prompt, the prompt version and the service-catalog version, so
any change to the data the model sees produces a new generation and an
unchanged input never pays twice.

With Supabase configured, `ai_generations` is the cache and the lock
(`claim_ai_generation`): a second request for a key that is being generated
waits for the first one's text instead of calling the provider again. A local
JSON file (`.cache/ai_generations.json`, or AI_CACHE_PATH) is an optional
extra copy for the worker and CLI; it is off on Vercel or with
AI_LOCAL_CACHE=0, and a failure to write it never blocks the remote record.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.config import env

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = ROOT / ".cache" / "ai_generations.json"
CACHE_SCHEMA_VERSION = 3
LEASE_SECONDS = 180
BUSY_WAIT_SECONDS = 25
BUSY_POLL_SECONDS = 2


class GenerationBusy(RuntimeError):
    """Another request is generating this text right now."""


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def generation_key(
    *,
    task: str,
    provider: str,
    requested_model: str,
    input_hash: str,
    prompt_version: str,
    catalog_version: str,
) -> str:
    return fingerprint(
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "task": task,
            "provider": provider,
            "model": requested_model,
            "input_hash": input_hash,
            "prompt_version": prompt_version,
            "catalog_version": catalog_version,
        }
    )


# ── Local file (optional) ────────────────────────────────────────────────────

def local_cache_path() -> Path | None:
    if env("VERCEL") or (env("AI_LOCAL_CACHE") or "1") == "0":
        return None
    configured = env("AI_CACHE_PATH")
    return Path(configured) if configured else DEFAULT_CACHE


def load_cache(path: Path | None = None) -> dict[str, Any]:
    path = path or local_cache_path()
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("local AI cache unreadable (%s): %s", path, exc)
        return {}


def _save_local(key: str, entry: dict[str, Any]) -> None:
    path = local_cache_path()
    if not path:
        return
    try:
        cache = load_cache(path)
        cache[key] = entry
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)  # atomic: readers never see half a file
    except OSError as exc:
        logger.warning("local AI cache not written (%s): %s", path, exc)


def _local_content(key: str) -> str | None:
    item = load_cache().get(key)
    content = item.get("content") if isinstance(item, dict) else None
    return content if isinstance(content, str) and content.strip() else None


# ── Get or generate ─────────────────────────────────────────────────────────

def get_or_generate(
    *,
    key: str,
    task: str,
    provider: str,
    requested_model: str,
    meta: dict[str, Any],
    generate: Callable[[], Any],
    on_hit: Callable[[str | None], None] | None = None,
    force: bool = False,
) -> str:
    """Cached text for `key`, or the result of `generate()` (an LLMResult),
    stored. `meta` carries lead_id, input_hash, prompt_version, catalog_version.
    `force` regenerates and replaces a finished text.
    Raises GenerationBusy if another request holds the key past the wait."""
    from src.storage import supabase

    def entry(content: str, result_provider: str, model: str | None, usage: Any) -> dict[str, Any]:
        return {
            "task": task, "provider": result_provider, "model": model, "content": content,
            "usage": usage or {}, "created_at": datetime.now(timezone.utc).isoformat(), **meta,
        }

    if not supabase.is_enabled():
        cached = None if force else _local_content(key)
        if cached:
            if on_hit:
                on_hit(None)
            return cached
        result = generate()
        _save_local(key, entry(result.content, result.provider, result.model, result.usage))
        return result.content

    owner = f"{os.getpid()}:{uuid.uuid4()}"
    claim_args = dict(
        cache_key=key, task=task, owner=owner, lease_seconds=LEASE_SECONDS, provider=provider,
        requested_model=requested_model, **meta,
    )
    state = supabase.claim_ai_generation(**claim_args)
    deadline = time.monotonic() + BUSY_WAIT_SECONDS
    while state.get("status") == "busy" and time.monotonic() < deadline:
        time.sleep(BUSY_POLL_SECONDS)
        state = supabase.claim_ai_generation(**claim_args)
    if state.get("status") == "ready" and force:
        result = generate()
        supabase.replace_ai_generation(
            cache_key=key, content=result.content, provider=result.provider, model=result.model, usage=result.usage or {},
        )
        _save_local(key, entry(result.content, result.provider, result.model, result.usage))
        return result.content
    if state.get("status") == "ready":
        content = state["content"]
        if on_hit:
            on_hit(state.get("model"))
        _save_local(key, entry(content, state.get("provider") or provider, state.get("model"), None))
        return content
    if state.get("status") == "busy":
        raise GenerationBusy(f"{task} is being generated by another request")

    try:
        result = generate()
    except Exception as exc:
        try:
            supabase.fail_ai_generation(cache_key=key, owner=owner, error=f"{type(exc).__name__}: {exc}")
        except Exception as release_exc:
            logger.warning("could not release AI generation lease %s: %s", key[:12], release_exc)
        raise
    supabase.complete_ai_generation(
        cache_key=key, content=result.content, provider=result.provider, model=result.model, usage=result.usage or {},
    )
    _save_local(key, entry(result.content, result.provider, result.model, result.usage))
    return result.content


def stats(path: Path | None = None) -> dict[str, Any]:
    path = path or local_cache_path()
    cache = load_cache(path) if path else {}
    by_task: dict[str, int] = {}
    by_model: dict[str, int] = {}
    total_tokens = 0
    for item in cache.values():
        if not isinstance(item, dict):
            continue
        by_task[item.get("task", "unknown")] = by_task.get(item.get("task", "unknown"), 0) + 1
        by_model[item.get("model", "unknown")] = by_model.get(item.get("model", "unknown"), 0) + 1
        usage = item.get("usage") or {}
        if isinstance(usage, dict):
            total_tokens += int(usage.get("total_tokens") or 0)
    return {
        "entries": len(cache),
        "by_task": by_task,
        "by_model": by_model,
        "total_tokens_recorded": total_tokens,
        "path": str(path) if path else None,
    }
