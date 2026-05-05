from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = ROOT / ".cache" / "ai_generations.json"


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def load_cache(path: Path = DEFAULT_CACHE) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cache(cache: dict[str, Any], path: Path = DEFAULT_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cache_key(*, task: str, provider: str, model: str, payload: Any) -> str:
    return fingerprint({"task": task, "provider": provider, "model": model, "payload": payload})


def get(key: str, path: Path = DEFAULT_CACHE) -> str | None:
    item = load_cache(path).get(key)
    if not isinstance(item, dict):
        return None
    content = item.get("content")
    return content if isinstance(content, str) and content.strip() else None


def put(
    key: str,
    *,
    task: str,
    provider: str,
    model: str,
    content: str,
    usage: dict[str, Any] | None = None,
    path: Path = DEFAULT_CACHE,
) -> None:
    cache = load_cache(path)
    cache[key] = {
        "task": task,
        "provider": provider,
        "model": model,
        "content": content,
        "usage": usage or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_cache(cache, path)


def stats(path: Path = DEFAULT_CACHE) -> dict[str, Any]:
    cache = load_cache(path)
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
        "path": str(path),
    }
