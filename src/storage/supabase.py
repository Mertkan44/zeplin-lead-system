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


def estimate_search_tokens(*, max_results: int, deep_research: bool = True, ai_mode: str = "smart") -> dict[str, Any]:
    per_lead = 9000 if deep_research else 5200
    model_mix = "flash+pro" if ai_mode == "smart" else ai_mode
    estimated_tokens = max(1, int(max_results)) * per_lead
    estimated_cost_usd = round(estimated_tokens / 1_000_000 * 0.9, 4)
    return {
        "estimated_tokens": estimated_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "model_mix": model_mix,
    }


def create_search_job(
    *,
    query: str,
    city: str,
    max_results: int,
    deep_research: bool,
    ai_mode: str,
    created_by: str,
) -> dict[str, Any]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    estimate = estimate_search_tokens(max_results=max_results, deep_research=deep_research, ai_mode=ai_mode)
    row = {
        "query": query,
        "city": city,
        "max_results": max_results,
        "deep_research": deep_research,
        "ai_mode": ai_mode,
        "status": "queued",
        "created_by": created_by,
        "estimated_tokens": estimate["estimated_tokens"],
        "estimated_cost_usd": estimate["estimated_cost_usd"],
        "meta": {"model_mix": estimate["model_mix"]},
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            _postgrest_url(config, "admin_search_jobs"),
            headers=_headers(config, prefer="return=representation"),
            json=row,
        )
        response.raise_for_status()
        jobs = response.json()
        job = jobs[0] if isinstance(jobs, list) and jobs else jobs
        ledger = {
            "job_id": job.get("id"),
            "kind": "reservation",
            "provider": "deepseek",
            "model": estimate["model_mix"],
            "estimated_tokens": estimate["estimated_tokens"],
            "actual_tokens": None,
            "estimated_cost_usd": estimate["estimated_cost_usd"],
            "actual_cost_usd": None,
            "meta": {"query": query, "city": city, "max_results": max_results},
        }
        ledger_response = client.post(
            _postgrest_url(config, "ai_token_ledger"),
            headers=_headers(config, prefer="return=minimal"),
            json=ledger,
        )
        ledger_response.raise_for_status()
        return job


def fetch_search_jobs(limit: int = 20, *, status: str | None = None) -> list[dict[str, Any]]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    query = (
        "select=id,query,city,max_results,deep_research,ai_mode,status,created_by,"
        "estimated_tokens,estimated_cost_usd,result,meta,created_at,updated_at"
        "&order=created_at.desc"
        f"&limit={min(limit, 100)}"
    )
    if status:
        query += f"&status=eq.{status}"
    with httpx.Client(timeout=20) as client:
        response = client.get(_postgrest_url(config, "admin_search_jobs", query), headers=_headers(config))
        response.raise_for_status()
        return response.json()


def update_search_job(job_id: int, *, status: str, result: dict[str, Any] | None = None) -> None:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    row: dict[str, Any] = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if result is not None:
        row["result"] = result
    with httpx.Client(timeout=20) as client:
        response = client.patch(
            _postgrest_url(config, "admin_search_jobs", f"id=eq.{job_id}"),
            headers=_headers(config, prefer="return=minimal"),
            json=row,
        )
        response.raise_for_status()


def fetch_token_summary() -> dict[str, Any]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    query = "select=estimated_tokens,actual_tokens,estimated_cost_usd,actual_cost_usd,kind,created_at&order=created_at.desc&limit=500"
    with httpx.Client(timeout=20) as client:
        response = client.get(_postgrest_url(config, "ai_token_ledger", query), headers=_headers(config))
        response.raise_for_status()
        rows = response.json()
    return {
        "estimated_tokens": sum(int(row.get("estimated_tokens") or 0) for row in rows),
        "actual_tokens": sum(int(row.get("actual_tokens") or 0) for row in rows),
        "estimated_cost_usd": round(sum(float(row.get("estimated_cost_usd") or 0) for row in rows), 4),
        "actual_cost_usd": round(sum(float(row.get("actual_cost_usd") or 0) for row in rows), 4),
        "entries": len(rows),
    }
