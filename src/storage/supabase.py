from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from src.config import env


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    key: str


def supabase_config() -> SupabaseConfig | None:
    url = (env("SUPABASE_URL") or "").rstrip("/")
    key = env("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_SECRET_KEY") or ""
    if not url or not key:
        return None
    return SupabaseConfig(url=url, key=key)


def is_enabled() -> bool:
    return supabase_config() is not None


def _headers(config: SupabaseConfig, *, prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": config.key,
        "Authorization": f"Bearer {config.key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _postgrest_url(config: SupabaseConfig, table: str, query: str = "") -> str:
    suffix = f"?{query}" if query else ""
    return f"{config.url}/rest/v1/{table}{suffix}"


def _lead_row(lead: dict[str, Any]) -> dict[str, Any]:
    scoring = lead.get("scoring") or {}
    package = lead.get("recommended_package") or {}
    data_quality = lead.get("data_quality") or {}
    now = datetime.now(timezone.utc).isoformat()
    return {
        "name": lead.get("name"),
        "sector": lead.get("sector"),
        "city": lead.get("city"),
        "category": lead.get("category"),
        "phone": lead.get("phone"),
        "address": lead.get("address"),
        "rating": lead.get("rating"),
        "review_count": lead.get("review_count"),
        "maps_url": lead.get("maps_url"),
        "website_url": (lead.get("website") or {}).get("website_url"),
        "instagram_url": (lead.get("social") or {}).get("instagram_url"),
        "score": scoring.get("score"),
        "grade": scoring.get("grade"),
        "estimated_value_tl": lead.get("estimated_value_tl"),
        "sales_priority_score": lead.get("sales_priority_score"),
        "next_action": lead.get("next_action"),
        "priority_reason": lead.get("priority_reason"),
        "recommended_package": package,
        "matched_services": lead.get("matched_services") or [],
        "data_quality": data_quality,
        "research_brief": lead.get("research_brief"),
        "ai_report": lead.get("ai_report"),
        "ai_email": lead.get("ai_email"),
        "status": lead.get("status") or "yeni",
        "last_analyzed": lead.get("last_analyzed"),
        "raw": lead,
        "updated_at": now,
    }


def upsert_leads(leads: list[dict[str, Any]], *, chunk_size: int = 100) -> int:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")

    total = 0
    rows = [_lead_row(lead) for lead in leads]
    with httpx.Client(timeout=60) as client:
        for index in range(0, len(rows), chunk_size):
            chunk = rows[index : index + chunk_size]
            response = client.post(
                _postgrest_url(config, "leads", "on_conflict=name"),
                headers=_headers(config, prefer="resolution=merge-duplicates"),
                content=json.dumps(chunk, ensure_ascii=False),
            )
            response.raise_for_status()
            total += len(chunk)
    return total


def set_lead_status(name: str, status: str) -> None:
    if status not in {"yeni", "contacted", "converted"}:
        raise ValueError("status must be yeni, contacted, or converted")
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    with httpx.Client(timeout=20) as client:
        response = client.patch(
            _postgrest_url(config, "leads", f"name=eq.{name}"),
            headers=_headers(config, prefer="return=minimal"),
            json={"status": status, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
        response.raise_for_status()


def insert_outreach_event(
    *,
    lead_name: str,
    action: str,
    note: str | None = None,
    happened_at: str | None = None,
) -> None:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    row = {
        "lead_name": lead_name,
        "action": action,
        "note": note,
        "happened_at": happened_at or datetime.now(timezone.utc).isoformat(),
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            _postgrest_url(config, "outreach_events"),
            headers=_headers(config, prefer="return=minimal"),
            json=row,
        )
        response.raise_for_status()


def list_leads(limit: int = 20) -> list[dict[str, Any]]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    query = f"select=name,score,grade,status,sales_priority_score,estimated_value_tl&order=sales_priority_score.desc&limit={limit}"
    with httpx.Client(timeout=20) as client:
        response = client.get(_postgrest_url(config, "leads", query), headers=_headers(config))
        if response.status_code == 400 and "leads.status" in response.text:
            fallback = f"select=name,score,grade,sales_priority_score,estimated_value_tl&order=sales_priority_score.desc&limit={limit}"
            response = client.get(_postgrest_url(config, "leads", fallback), headers=_headers(config))
        response.raise_for_status()
        return response.json()


def fetch_leads_full(limit: int = 500) -> list[dict[str, Any]]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    query = f"select=raw,status,updated_at&order=sales_priority_score.desc.nullslast&limit={limit}"
    with httpx.Client(timeout=30) as client:
        response = client.get(_postgrest_url(config, "leads", query), headers=_headers(config))
        response.raise_for_status()
        rows = response.json()
    leads: list[dict[str, Any]] = []
    for row in rows:
        raw = row.get("raw") or {}
        if isinstance(raw, dict):
            raw["status"] = row.get("status") or raw.get("status") or "yeni"
            raw["supabase_updated_at"] = row.get("updated_at")
            leads.append(raw)
    return leads


def fetch_outreach_events(limit: int = 500) -> list[dict[str, Any]]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    query = (
        "select=id,lead_name,action,note,happened_at,created_at"
        f"&order=happened_at.desc&limit={limit}"
    )
    with httpx.Client(timeout=30) as client:
        response = client.get(_postgrest_url(config, "outreach_events", query), headers=_headers(config))
        response.raise_for_status()
        return response.json()


def insert_run_log(
    *,
    kind: str,
    status: str,
    message: str,
    meta: dict[str, Any] | None = None,
) -> None:
    config = supabase_config()
    if not config:
        return
    row = {
        "kind": kind,
        "status": status,
        "message": message,
        "meta": meta or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            _postgrest_url(config, "pipeline_runs"),
            headers=_headers(config, prefer="return=minimal"),
            json=row,
        )
        response.raise_for_status()
