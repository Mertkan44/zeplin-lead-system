from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / ".cache" / "pipeline_state.json"


def _key(name: str, city: str = "", query: str = "") -> str:
    raw = "|".join([name.strip().lower(), city.strip().lower(), query.strip().lower()])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_state(path: Path = DEFAULT_STATE) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: dict[str, Any], path: Path = DEFAULT_STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_stage(name: str, stage: str, *, city: str = "", query: str = "", path: Path = DEFAULT_STATE):
    state = load_state(path)
    item = state.get(_key(name, city, query), {})
    return item.get(stage)


def put_stage(
    name: str,
    stage: str,
    value: Any,
    *,
    city: str = "",
    query: str = "",
    path: Path = DEFAULT_STATE,
) -> None:
    state = load_state(path)
    key = _key(name, city, query)
    item = state.setdefault(key, {"name": name, "city": city, "query": query, "stages": []})
    item[stage] = value
    stages = item.setdefault("stages", [])
    if stage not in stages:
        stages.append(stage)
    item["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state, path)
