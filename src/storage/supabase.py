from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

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


def _eq(value: str) -> str:
    return quote(str(value), safe="")


def _lead_row(lead: dict[str, Any]) -> dict[str, Any]:
    scoring = lead.get("scoring") or {}
    package = lead.get("recommended_package") or {}
    data_quality = lead.get("data_quality") or {}
    now = datetime.now(timezone.utc).isoformat()
    maps_url = str(lead.get("maps_url") or "").strip()
    identity = (
        f"{str(lead.get('name') or '').strip().casefold()}|"
        f"{str(lead.get('city') or '').strip().casefold()}"
    )
    return {
        "external_id": f"name-city:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}",
        "name": lead.get("name"),
        "sector": lead.get("sector"),
        "city": lead.get("city"),
        "category": lead.get("category"),
        "phone": lead.get("phone"),
        "address": lead.get("address"),
        "rating": lead.get("rating"),
        "review_count": lead.get("review_count"),
        "maps_url": maps_url or None,
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


LEAD_STATUSES = {"yeni", "ready", "missing_info", "contacted", "follow_up", "converted", "lost"}
_UNSET = object()


def set_lead_status(name: str, status: str) -> None:
    if status not in LEAD_STATUSES:
        raise ValueError("status is invalid")
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    with httpx.Client(timeout=20) as client:
        response = client.patch(
            _postgrest_url(config, "leads", f"name=eq.{_eq(name)}"),
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
    actor_email: str | None = None,
    source: str = "dashboard",
    idempotency_key: str | None = None,
) -> None:
    aliases = {
        "note": "note_added",
        "call_made": "call_completed",
        "email_sent": "email_sent",
        "meeting_scheduled": "follow_up_scheduled",
        "reply_received": "follow_up_scheduled",
        "draft_prepared": "email_drafted",
        "outreach_review_started": "email_drafted",
    }
    action = aliases.get(action, action)
    allowed_actions = {
        "data_enrichment_started",
        "note_added",
        "call_started",
        "call_completed",
        "contact_result_recorded",
        "draft_reviewed",
        "manual_verification_saved",
        "email_drafted",
        "email_sent",
        "follow_up_scheduled",
        "proposal_created",
        "proposal_sent",
        "deal_won",
        "deal_lost",
    }
    if action not in allowed_actions:
        raise ValueError("outreach action is invalid")
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    row = {
        "lead_name": lead_name,
        "action": action,
        "note": note,
        "happened_at": happened_at or datetime.now(timezone.utc).isoformat(),
        "actor_email": actor_email,
        "source": source,
        "idempotency_key": idempotency_key,
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            _postgrest_url(
                config,
                "outreach_events",
                "on_conflict=idempotency_key" if idempotency_key else "",
            ),
            headers=_headers(
                config,
                prefer="resolution=ignore-duplicates,return=minimal" if idempotency_key else "return=minimal",
            ),
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
        "select=id,lead_name,action,note,happened_at,created_at,actor_email,source,idempotency_key"
        f"&order=happened_at.desc&limit={limit}"
    )
    with httpx.Client(timeout=30) as client:
        response = client.get(_postgrest_url(config, "outreach_events", query), headers=_headers(config))
        response.raise_for_status()
        return response.json()


def reset_sales_activity() -> dict[str, int | bool]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")

    now = datetime.now(timezone.utc).isoformat()
    result: dict[str, int | bool] = {
        "lead_statuses_reset": 0,
        "outreach_events_deleted": 0,
        "assignments_archived": 0,
        "assignments_table_available": True,
    }

    with httpx.Client(timeout=30) as client:
        outreach_count = client.get(
            _postgrest_url(config, "outreach_events", "select=id"),
            headers=_headers(config, prefer="count=exact"),
        )
        outreach_count.raise_for_status()
        result["outreach_events_deleted"] = len(outreach_count.json())

        delete_outreach = client.delete(
            _postgrest_url(config, "outreach_events", "id=gt.0"),
            headers=_headers(config, prefer="return=minimal"),
        )
        delete_outreach.raise_for_status()

        lead_count = client.get(
            _postgrest_url(config, "leads", "select=id"),
            headers=_headers(config, prefer="count=exact"),
        )
        lead_count.raise_for_status()
        result["lead_statuses_reset"] = len(lead_count.json())

        reset_leads = client.patch(
            _postgrest_url(config, "leads", "id=gt.0"),
            headers=_headers(config, prefer="return=minimal"),
            json={"status": "yeni", "updated_at": now},
        )
        reset_leads.raise_for_status()

        assignment_count = client.get(
            _postgrest_url(config, "lead_assignments", "select=id&status=eq.active"),
            headers=_headers(config, prefer="count=exact"),
        )
        if assignment_count.status_code in {404, 400}:
            result["assignments_table_available"] = False
        else:
            assignment_count.raise_for_status()
            result["assignments_archived"] = len(assignment_count.json())
            archive_assignments = client.patch(
                _postgrest_url(config, "lead_assignments", "status=eq.active"),
                headers=_headers(config, prefer="return=minimal"),
                json={"status": "archived", "updated_at": now},
            )
            archive_assignments.raise_for_status()

    return result


def fetch_app_user_by_email(email: str) -> dict[str, Any] | None:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    query = (
        "select=id,email,name,role,title,avatar_url,password_hash,active,created_at,updated_at"
        f"&email=eq.{_eq(email.lower())}"
        "&limit=1"
    )
    with httpx.Client(timeout=20) as client:
        response = client.get(_postgrest_url(config, "app_users", query), headers=_headers(config))
        response.raise_for_status()
        rows = response.json()
    return rows[0] if rows else None


def fetch_app_users(limit: int = 100) -> list[dict[str, Any]]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    query = (
        "select=id,email,name,role,title,avatar_url,active,created_at,updated_at"
        "&order=created_at.asc"
        f"&limit={min(limit, 200)}"
    )
    with httpx.Client(timeout=20) as client:
        response = client.get(_postgrest_url(config, "app_users", query), headers=_headers(config))
        response.raise_for_status()
        return response.json()


def upsert_app_user(
    *,
    email: str,
    name: str,
    role: str,
    title: str | None = None,
    avatar_url: str | None = None,
    password_hash: str | None = None,
    active: bool = True,
) -> dict[str, Any]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    if role not in {"admin", "sales"}:
        raise ValueError("role must be admin or sales")
    now = datetime.now(timezone.utc).isoformat()
    row: dict[str, Any] = {
        "email": email.strip().lower(),
        "name": name.strip(),
        "role": role,
        "title": title.strip() if title else None,
        "avatar_url": avatar_url.strip() if avatar_url else None,
        "active": active,
        "updated_at": now,
    }
    if password_hash:
        row["password_hash"] = password_hash
    with httpx.Client(timeout=20) as client:
        response = client.post(
            _postgrest_url(config, "app_users", "on_conflict=email"),
            headers=_headers(config, prefer="resolution=merge-duplicates,return=representation"),
            json=row,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if isinstance(rows, list) and rows else rows


def set_app_user_active(email: str, active: bool) -> None:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    with httpx.Client(timeout=20) as client:
        response = client.patch(
            _postgrest_url(config, "app_users", f"email=eq.{_eq(email.lower())}"),
            headers=_headers(config, prefer="return=minimal"),
            json={"active": active, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
        response.raise_for_status()


ASSIGNMENT_STATUSES = {"active", "done", "snoozed", "archived"}


def fetch_lead_assignments(
    *,
    user_email: str | None = None,
    lead_name: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    query = (
        "select=id,lead_name,user_email,status,due_at,assigned_by,assigned_at,updated_at,meta"
        "&order=updated_at.desc"
        f"&limit={min(limit, 1000)}"
    )
    if user_email:
        query += f"&user_email=eq.{_eq(user_email.lower())}"
    if lead_name:
        query += f"&lead_name=eq.{_eq(lead_name)}"
    if status:
        query += f"&status=eq.{_eq(status)}"
    with httpx.Client(timeout=20) as client:
        response = client.get(_postgrest_url(config, "lead_assignments", query), headers=_headers(config))
        response.raise_for_status()
        return response.json()


def _in_list(values: list[str]) -> str:
    quoted = []
    for value in values:
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        quoted.append(f'"{escaped}"')
    return quote(f"({','.join(quoted)})", safe="")


def fetch_active_assignments_for_leads(lead_names: list[str]) -> list[dict[str, Any]]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    names = sorted({name for name in lead_names if name})
    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=20) as client:
        for start in range(0, len(names), 100):
            chunk = names[start:start + 100]
            query = (
                "select=id,lead_name,user_email,status"
                f"&lead_name=in.{_in_list(chunk)}"
                "&status=eq.active"
                "&limit=1000"
            )
            response = client.get(_postgrest_url(config, "lead_assignments", query), headers=_headers(config))
            response.raise_for_status()
            rows.extend(response.json())
    return rows


def fetch_lead_assignment_by_id(assignment_id: int) -> dict[str, Any] | None:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    query = (
        "select=id,lead_name,user_email,status,due_at,assigned_by,assigned_at,updated_at,meta"
        f"&id=eq.{assignment_id}"
        "&limit=1"
    )
    with httpx.Client(timeout=20) as client:
        response = client.get(_postgrest_url(config, "lead_assignments", query), headers=_headers(config))
        response.raise_for_status()
        rows = response.json()
    return rows[0] if rows else None


def upsert_lead_assignment(
    *,
    lead_name: str,
    user_email: str,
    assigned_by: str,
    due_at: str | None = None,
    status: str = "active",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    if status not in ASSIGNMENT_STATUSES:
        raise ValueError("assignment status is invalid")
    payload = {
        "target_lead_name": lead_name,
        "target_user_email": user_email.strip().lower(),
        "assignment_by": assigned_by.strip().lower(),
        "assignment_due_at": due_at,
        "assignment_status": status,
        "assignment_meta": meta or {},
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            f"{config.url}/rest/v1/rpc/assign_lead_owner",
            headers=_headers(config),
            json=payload,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if isinstance(rows, list) and rows else rows


def update_lead_assignment(
    assignment_id: int,
    *,
    status: str,
    meta: dict[str, Any] | None = None,
    due_at: str | None | object = _UNSET,
) -> None:
    if status not in ASSIGNMENT_STATUSES:
        raise ValueError("assignment status is invalid")
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    row: dict[str, Any] = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if meta is not None:
        row["meta"] = meta
    if due_at is not _UNSET:
        row["due_at"] = due_at
    with httpx.Client(timeout=20) as client:
        response = client.patch(
            _postgrest_url(config, "lead_assignments", f"id=eq.{assignment_id}"),
            headers=_headers(config, prefer="return=minimal"),
            json=row,
        )
        response.raise_for_status()


def attach_assignments_to_leads(
    leads: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_lead: dict[str, list[dict[str, Any]]] = {}
    for assignment in assignments:
        by_lead.setdefault(assignment.get("lead_name") or "", []).append(assignment)
    enriched = []
    for lead in leads:
        row = dict(lead)
        items = by_lead.get(row.get("name") or "", [])
        row["assignments"] = items
        active_items = [item for item in items if item.get("status") == "active"]
        active = max(active_items, key=lambda item: item.get("updated_at") or "") if active_items else None
        if active:
            row["assignment_id"] = active.get("id")
            row["assignment_status"] = active.get("status")
            row["assigned_to"] = active.get("user_email")
            row["assignment_due_at"] = active.get("due_at")
            row["assignment_meta"] = active.get("meta") or {}
        enriched.append(row)
    return enriched


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


def insert_audit_event(
    *,
    actor_email: str | None,
    event_type: str,
    target_type: str,
    target_key: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    config = supabase_config()
    if not config:
        return
    row = {
        "actor_email": actor_email,
        "event_type": event_type,
        "target_type": target_type,
        "target_key": target_key,
        "meta": meta or {},
    }
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                _postgrest_url(config, "audit_events"),
                headers=_headers(config, prefer="return=minimal"),
                json=row,
            )
            response.raise_for_status()
    except Exception:
        # Audit availability must not turn a valid CRM action into a duplicate retry.
        return


def check_login_rate_limit(key_hash: str, *, max_attempts: int, window_seconds: int) -> bool | None:
    config = supabase_config()
    if not config:
        return None
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                f"{config.url}/rest/v1/rpc/check_login_rate_limit",
                headers=_headers(config),
                json={
                    "attempt_key_hash": key_hash,
                    "attempt_limit": max_attempts,
                    "window_seconds": window_seconds,
                },
            )
            response.raise_for_status()
            return bool(response.json())
    except Exception:
        return None


def record_login_attempt(key_hash: str, *, success: bool) -> bool:
    config = supabase_config()
    if not config:
        return False
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                f"{config.url}/rest/v1/rpc/record_login_attempt",
                headers=_headers(config),
                json={"attempt_key_hash": key_hash, "attempt_succeeded": success},
            )
            response.raise_for_status()
            return True
    except Exception:
        return False


def estimate_search_tokens(*, max_results: int, deep_research: bool = True, ai_mode: str = "smart") -> dict[str, Any]:
    per_lead = 9000 if deep_research else 5200
    model_mix = "flash+pro" if ai_mode == "smart" else ai_mode
    estimated_tokens = max(1, int(max_results)) * per_lead
    blended_rate = float(env("DEEPSEEK_ESTIMATED_USD_PER_M_TOKENS", "1.25") or 1.25)
    estimated_cost_usd = round(estimated_tokens / 1_000_000 * blended_rate, 4)
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
    payload = {
        "query": query,
        "city": city,
        "max_results": max_results,
        "deep_research": deep_research,
        "ai_mode": ai_mode,
        "created_by": created_by,
        "estimated_tokens": estimate["estimated_tokens"],
        "estimated_cost_usd": estimate["estimated_cost_usd"],
        "reservation_meta": {"model_mix": estimate["model_mix"]},
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            f"{config.url}/rest/v1/rpc/create_admin_search_job",
            headers=_headers(config),
            json=payload,
        )
        if response.status_code != 404:
            response.raise_for_status()
            body = response.json()
            return body[0] if isinstance(body, list) and body else body

        # Compatibility path for deployments that have not applied migration 006 yet.
        legacy_job = {
            key: value for key, value in payload.items() if key not in {"reservation_meta"}
        }
        legacy_job["meta"] = {
            **payload["reservation_meta"],
            "queue_mode": "legacy_single_worker",
        }
        job_response = client.post(
            _postgrest_url(config, "admin_search_jobs"),
            headers=_headers(config, prefer="return=representation"),
            json=legacy_job,
        )
        job_response.raise_for_status()
        rows = job_response.json()
        job = rows[0] if isinstance(rows, list) and rows else rows
        ledger_response = client.post(
            _postgrest_url(config, "ai_token_ledger"),
            headers=_headers(config, prefer="return=minimal"),
            json={
                "job_id": job["id"],
                "kind": "reservation",
                "provider": "deepseek",
                "model": estimate["model_mix"],
                "estimated_tokens": estimate["estimated_tokens"],
                "estimated_cost_usd": estimate["estimated_cost_usd"],
                "meta": {"query": query, "city": city, "max_results": max_results},
            },
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


def claim_search_jobs(limit: int = 1) -> list[dict[str, Any]]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured.")
    with httpx.Client(timeout=20) as client:
        response = client.post(
            f"{config.url}/rest/v1/rpc/claim_admin_search_jobs",
            headers=_headers(config),
            json={"job_limit": min(max(int(limit), 1), 10)},
        )
        if response.status_code != 404:
            response.raise_for_status()
            body = response.json()
            return body if isinstance(body, list) else []

        # GitHub Actions concurrency keeps this fallback single-worker until migration 006.
        queued = fetch_search_jobs(limit=min(max(int(limit), 1), 10), status="queued")
        claimed = []
        for job in reversed(queued):
            claim_response = client.patch(
                _postgrest_url(
                    config,
                    "admin_search_jobs",
                    f"id=eq.{int(job['id'])}&status=eq.queued",
                ),
                headers=_headers(config, prefer="return=representation"),
                json={
                    "status": "running",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "result": {"queue_mode": "legacy_single_worker"},
                },
            )
            claim_response.raise_for_status()
            rows = claim_response.json()
            if rows:
                claimed.append(rows[0])
        return claimed


def record_token_usage(*, job_id: int, model: str, usage: dict[str, Any]) -> dict[str, Any]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured.")
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    cached_tokens = int(
        usage.get("prompt_cache_hit_tokens")
        or (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        or 0
    )
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    input_rate = float(env("DEEPSEEK_INPUT_USD_PER_M_TOKENS", "0.28") or 0.28)
    cached_rate = float(env("DEEPSEEK_CACHED_INPUT_USD_PER_M_TOKENS", "0.028") or 0.028)
    output_rate = float(env("DEEPSEEK_OUTPUT_USD_PER_M_TOKENS", "0.42") or 0.42)
    uncached_tokens = max(prompt_tokens - cached_tokens, 0)
    cost = (
        uncached_tokens * input_rate
        + cached_tokens * cached_rate
        + completion_tokens * output_rate
    ) / 1_000_000
    row = {
        "job_id": job_id,
        "kind": "usage",
        "provider": "deepseek",
        "model": model,
        "estimated_tokens": 0,
        "actual_tokens": total_tokens,
        "estimated_cost_usd": 0,
        "actual_cost_usd": round(cost, 6),
        "meta": {
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "completion_tokens": completion_tokens,
        },
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            _postgrest_url(config, "ai_token_ledger"),
            headers=_headers(config, prefer="return=representation"),
            json=row,
        )
        response.raise_for_status()
        body = response.json()
        return body[0] if isinstance(body, list) and body else body


def fetch_ai_generation(cache_key: str) -> dict[str, Any] | None:
    config = supabase_config()
    if not config:
        return None
    query = (
        "select=cache_key,task,provider,model,content,usage,created_at,updated_at"
        f"&cache_key=eq.{_eq(cache_key)}&limit=1"
    )
    with httpx.Client(timeout=20) as client:
        response = client.get(_postgrest_url(config, "ai_generations", query), headers=_headers(config))
        if response.status_code == 404:
            return None
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None


def upsert_ai_generation(
    *,
    cache_key: str,
    task: str,
    provider: str,
    model: str,
    content: str,
    usage: dict[str, Any],
) -> None:
    config = supabase_config()
    if not config:
        return
    row = {
        "cache_key": cache_key,
        "task": task,
        "provider": provider,
        "model": model,
        "content": content,
        "usage": usage,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            _postgrest_url(config, "ai_generations", "on_conflict=cache_key"),
            headers=_headers(config, prefer="resolution=merge-duplicates,return=minimal"),
            json=row,
        )
        response.raise_for_status()


def fetch_token_summary() -> dict[str, Any]:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    query = "select=estimated_tokens,actual_tokens,estimated_cost_usd,actual_cost_usd,kind,created_at&order=created_at.desc&limit=5000"
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
