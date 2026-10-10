from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from src.config import env
from src.lead_identity import lead_external_id


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


_READ_ONLY_LEAD_KEYS = {"lead_id", "revision", "supabase_updated_at"}


def _lead_row(lead: dict[str, Any]) -> dict[str, Any]:
    scoring = lead.get("scoring") or {}
    package = lead.get("recommended_package") or {}
    data_quality = lead.get("data_quality") or {}
    now = datetime.now(timezone.utc).isoformat()
    maps_url = str(lead.get("maps_url") or "").strip()
    # Database-side fields attached on read must not be written back into raw.
    raw = {key: value for key, value in lead.items() if key not in _READ_ONLY_LEAD_KEYS}
    return {
        "external_id": lead_external_id(lead),
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
        "raw": raw,
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
        if response.status_code in {400, 403, 404, 409}:
            body = response.json()
            code = str(body.get("message") or "")
            if str(body.get("code") or "").startswith("PT") and code.isupper():
                raise CommandRejected(response.status_code, code)
        response.raise_for_status()


class CommandRejected(Exception):
    """A database command refused the request (PostgREST PTxxx error)."""

    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


def record_contact_result(
    *,
    idempotency_key: str,
    request_hash: str,
    actor_email: str,
    actor_is_admin: bool,
    lead_name: str,
    expected_revision: int | None,
    activity: dict[str, Any],
    note: str,
    lead_status: str,
    assignment_status: str,
) -> dict[str, Any]:
    """Record a contact result atomically through public.record_contact_result."""
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    payload = {
        "p_idempotency_key": idempotency_key,
        "p_request_hash": request_hash,
        "p_actor_email": actor_email,
        "p_actor_is_admin": actor_is_admin,
        "p_lead_name": lead_name,
        "p_expected_revision": expected_revision,
        "p_channel": activity["channel"],
        "p_outcome": activity["outcome"],
        "p_follow_up_at": activity.get("follow_up_at"),
        "p_service_slugs": activity.get("service_slugs") or [],
        "p_contact_name": activity.get("contact_name"),
        "p_note": note,
        "p_lead_status": lead_status,
        "p_assignment_status": assignment_status,
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            f"{config.url}/rest/v1/rpc/record_contact_result",
            headers=_headers(config),
            json=payload,
        )
    if response.status_code in {400, 403, 404, 409}:
        try:
            body = response.json()
        except ValueError:
            body = {}
        code = str(body.get("message") or "")
        if str(body.get("code") or "").startswith("PT") and code.isupper():
            raise CommandRejected(response.status_code, code)
    response.raise_for_status()
    return response.json()


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


_LEAD_COLUMNS = "id,raw,status,created_at,updated_at,revision,sales_priority_score"
_EVENT_COLUMNS = (
    "id,lead_id,lead_name,action,note,happened_at,created_at,actor_email,source,idempotency_key,"
    "channel,outcome,follow_up_at,service_slugs,contact_name"
)
_PAGE = 1000
_NAME_CHUNK = 100


def _require_config() -> SupabaseConfig:
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    return config


def _lead_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    raw = row.get("raw") or {}
    if not isinstance(raw, dict):
        return None
    raw["lead_id"] = row.get("id")
    raw["status"] = row.get("status") or raw.get("status") or "yeni"
    raw["supabase_updated_at"] = row.get("updated_at")
    # When the lead entered the CRM (reports count new leads by this, not by analysis).
    if row.get("created_at"):
        raw["created_at"] = row["created_at"]
    raw["revision"] = row.get("revision")
    return raw


def _priority_order(row: dict[str, Any]) -> tuple:
    """Same order as the database: highest priority first, unknown last, then id."""
    priority = row.get("sales_priority_score")
    return (priority is None, -(priority or 0), row.get("id") or 0)


def _get_all(client: httpx.Client, config: SupabaseConfig, table: str, query: str) -> list[dict[str, Any]]:
    """Follow offset pages until a short page; the query must carry a stable order."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = client.get(
            _postgrest_url(config, table, f"{query}&limit={_PAGE}&offset={offset}"),
            headers=_headers(config),
        )
        response.raise_for_status()
        page = response.json()
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        offset += _PAGE


def _chunks(values: list[Any]) -> list[list[Any]]:
    return [values[start:start + _NAME_CHUNK] for start in range(0, len(values), _NAME_CHUNK)]


def fetch_all_leads() -> list[dict[str, Any]]:
    """Every lead, highest sales priority first. Admin scope only."""
    config = _require_config()
    with httpx.Client(timeout=60) as client:
        rows = _get_all(
            client, config, "leads",
            f"select={_LEAD_COLUMNS}&order=sales_priority_score.desc.nullslast,id.asc",
        )
    return [lead for lead in (_lead_from_row(row) for row in rows) if lead is not None]


def fetch_leads_by_names(names: set[str] | list[str]) -> list[dict[str, Any]]:
    """The given leads only (a sales user's readable scope), highest priority first."""
    config = _require_config()
    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=60) as client:
        for chunk in _chunks(sorted(name for name in names if name)):
            response = client.get(
                _postgrest_url(config, "leads", f"select={_LEAD_COLUMNS}&name=in.{_in_list(chunk)}"),
                headers=_headers(config),
            )
            response.raise_for_status()
            rows.extend(response.json())
    rows.sort(key=_priority_order)
    return [lead for lead in (_lead_from_row(row) for row in rows) if lead is not None]


def fetch_lead_by_name(name: str) -> dict[str, Any] | None:
    config = _require_config()
    with httpx.Client(timeout=20) as client:
        response = client.get(
            _postgrest_url(config, "leads", f"select={_LEAD_COLUMNS}&name=eq.{_eq(name)}&limit=1"),
            headers=_headers(config),
        )
        response.raise_for_status()
        rows = response.json()
    return _lead_from_row(rows[0]) if rows else None


def fetch_lead_by_id(lead_id: int) -> dict[str, Any] | None:
    config = _require_config()
    with httpx.Client(timeout=20) as client:
        response = client.get(
            _postgrest_url(config, "leads", f"select={_LEAD_COLUMNS}&id=eq.{int(lead_id)}&limit=1"),
            headers=_headers(config),
        )
        response.raise_for_status()
        rows = response.json()
    return _lead_from_row(rows[0]) if rows else None


def fetch_readable_leads(user_email: str) -> list[dict[str, Any]]:
    """Rows of public.readable_leads: the leads a sales user may read (migration 010)."""
    config = _require_config()
    with httpx.Client(timeout=20) as client:
        response = client.post(
            f"{config.url}/rest/v1/rpc/readable_leads",
            headers=_headers(config),
            json={"p_email": user_email},
        )
        response.raise_for_status()
        return response.json()


def fetch_activity_states(lead_ids: list[int] | None = None) -> dict[int, dict[str, Any]]:
    """lead_activity_state rows by lead id; None means every lead (admin)."""
    config = _require_config()
    columns = (
        "lead_id,latest_contact,latest_contact_at,latest_contact_actor,latest_outcome,"
        "latest_follow_up_at,contact_result_count,latest_manual_verification,latest_manual_verification_at"
    )
    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=60) as client:
        if lead_ids is None:
            rows = _get_all(client, config, "lead_activity_state", f"select={columns}&order=lead_id.asc")
        else:
            for chunk in _chunks(sorted({int(item) for item in lead_ids if item is not None})):
                ids = ",".join(str(item) for item in chunk)
                response = client.get(
                    _postgrest_url(config, "lead_activity_state", f"select={columns}&lead_id=in.({ids})"),
                    headers=_headers(config),
                )
                response.raise_for_status()
                rows.extend(response.json())
    return {int(row["lead_id"]): row for row in rows}


def fetch_events_since(since_iso: str, lead_names: set[str] | list[str] | None = None) -> list[dict[str, Any]]:
    """Events newer than since_iso, newest first; None means every lead (admin)."""
    config = _require_config()
    base = f"select={_EVENT_COLUMNS}&happened_at=gte.{_eq(since_iso)}&order=happened_at.desc,id.desc"
    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=60) as client:
        if lead_names is None:
            rows = _get_all(client, config, "outreach_events", base)
        else:
            for chunk in _chunks(sorted(name for name in lead_names if name)):
                rows.extend(_get_all(client, config, "outreach_events", f"{base}&lead_name=in.{_in_list(chunk)}"))
            rows.sort(key=lambda row: (row.get("happened_at") or "", row.get("id") or 0), reverse=True)
    return rows


def fetch_event_page(
    *,
    lead_names: set[str] | list[str] | None,
    before_id: int | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Newest events first, keyset-paginated by id; None means every lead (admin)."""
    config = _require_config()
    limit = min(max(int(limit), 1), 200)
    base = f"select={_EVENT_COLUMNS}&order=id.desc&limit={limit}"
    if before_id is not None:
        base += f"&id=lt.{int(before_id)}"
    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=30) as client:
        chunks = [None] if lead_names is None else _chunks(sorted(name for name in lead_names if name))
        for chunk in chunks:
            query = base if chunk is None else f"{base}&lead_name=in.{_in_list(chunk)}"
            response = client.get(_postgrest_url(config, "outreach_events", query), headers=_headers(config))
            response.raise_for_status()
            rows.extend(response.json())
    rows.sort(key=lambda row: row.get("id") or 0, reverse=True)
    return rows[:limit]


def list_leads_page(
    *,
    actor_email: str,
    is_admin: bool,
    after_priority: int | None,
    after_id: int | None,
    limit: int,
    search: str | None,
    status: str | None,
) -> dict[str, Any]:
    """One page of public.list_leads (migration 010): minimal rows, cursor, exact total."""
    config = _require_config()
    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{config.url}/rest/v1/rpc/list_leads",
            headers=_headers(config),
            json={
                "p_actor_email": actor_email,
                "p_is_admin": is_admin,
                "p_after_priority": after_priority,
                "p_after_id": after_id,
                "p_limit": limit,
                "p_search": search,
                "p_status": status,
            },
        )
        response.raise_for_status()
        return response.json()


def fetch_places_refresh_state() -> list[dict[str, Any]]:
    """Name, last verified refresh and last lookup attempt of every lead, for the daily cron."""
    config = _require_config()
    with httpx.Client(timeout=60) as client:
        return _get_all(
            client, config, "leads",
            "select=id,name,refreshed_at:raw->research->google_places->>refreshed_at,"
            "attempted_at:raw->research->google_places->last_attempt->>attempted_at,"
            "attempt_status:raw->research->google_places->last_attempt->>status&order=id.asc",
        )


def fetch_place_owner(place_id: str) -> int | None:
    """lead_id that a Google place id is recorded for in lead_sources, if any."""
    config = _require_config()
    with httpx.Client(timeout=20) as client:
        response = client.get(
            _postgrest_url(
                config,
                "lead_sources",
                f"select=lead_id&provider=eq.google_places&provider_id=eq.{quote(place_id, safe='')}&limit=1",
            ),
            headers=_headers(config),
        )
        response.raise_for_status()
        rows = response.json()
    return int(rows[0]["lead_id"]) if rows else None


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


REQUIRED_SCHEMA_VERSION = "013"


def fetch_schema_readiness() -> dict[str, Any]:
    """Raw `schema_readiness()` result; a database older than 008 has no such RPC."""
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    with httpx.Client(timeout=10) as client:
        response = client.post(f"{config.url}/rest/v1/rpc/schema_readiness", headers=_headers(config), json={})
        if response.status_code == 404:
            return {"version": None, "checks": {"schema_readiness": False}}
        response.raise_for_status()
        return response.json() or {}


def evaluate_schema_readiness(raw: dict[str, Any]) -> dict[str, Any]:
    version = raw.get("version")
    failed = sorted(name for name, passed in (raw.get("checks") or {}).items() if passed is not True)
    version_ok = bool(version) and str(version) >= REQUIRED_SCHEMA_VERSION
    return {
        "ready": version_ok and not failed,
        "version": version,
        "required_version": REQUIRED_SCHEMA_VERSION,
        "failed_checks": failed,
    }


def schema_status() -> dict[str, Any]:
    raw = fetch_schema_readiness()
    if str(raw.get("version") or "") >= "013":
        checks = _rpc("opportunity_schema_readiness", {})
        raw = {**raw, "checks": {**(raw.get("checks") or {}), **(checks or {"opportunity_schema": False})}}
    return evaluate_schema_readiness(raw)


def _count(client: httpx.Client, config: SupabaseConfig, table: str, query: str) -> int:
    response = client.get(
        _postgrest_url(config, table, f"select=id&{query}&limit=1"),
        headers=_headers(config, prefer="count=exact"),
    )
    response.raise_for_status()
    total = (response.headers.get("content-range") or "*/0").rsplit("/", 1)[-1]
    return int(total) if total.isdigit() else 0


def fetch_identity_snapshot() -> dict[str, Any]:
    """Read-only data for scripts/lead_identity_report.py."""
    config = supabase_config()
    if not config:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    with httpx.Client(timeout=60) as client:
        leads: list[dict[str, Any]] = []
        offset = 0
        while True:
            response = client.get(
                _postgrest_url(
                    config,
                    "leads",
                    "select=id,name,city,phone,maps_url,website_url,external_id,"
                    "research:raw->research"
                    f"&order=id.asc&limit=1000&offset={offset}",
                ),
                headers=_headers(config),
            )
            response.raise_for_status()
            page = response.json()
            leads.extend(page)
            if len(page) < 1000:
                break
            offset += 1000
        sources_response = client.get(
            _postgrest_url(config, "lead_sources", "select=lead_id,provider,provider_id&limit=10000"),
            headers=_headers(config),
        )
        sources = sources_response.json() if sources_response.status_code == 200 else None
        lead_id_gaps = None
        if sources is not None:
            lead_id_gaps = {
                "outreach_events": _count(client, config, "outreach_events", "lead_id=is.null"),
                "lead_assignments": _count(client, config, "lead_assignments", "lead_id=is.null"),
            }
    return {"leads": leads, "sources": sources, "lead_id_gaps": lead_id_gaps}


def fetch_all_assignments() -> list[dict[str, Any]]:
    """Every assignment row (admin workspace), newest change first."""
    config = _require_config()
    with httpx.Client(timeout=60) as client:
        return _get_all(
            client, config, "lead_assignments",
            "select=id,lead_name,user_email,status,due_at,assigned_by,assigned_at,updated_at,meta"
            "&order=updated_at.desc,id.desc",
        )


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
    except Exception as exc:
        # Audit availability must not turn a valid CRM action into a duplicate retry.
        # Log only categories: exception text can contain credentials, actor or CRM data.
        logging.getLogger("zeplin.operations").error(json.dumps({
            "event": "audit_persistence_failed",
            "operation": event_type,
            "error_type": type(exc).__name__,
        }))
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
    """See src/ai/pricing.estimate_search: the panel and the reservation use the same estimate."""
    from src.ai.pricing import estimate_search

    return estimate_search(max_results=max_results, deep_research=deep_research, ai_mode=ai_mode)


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


def _rpc(name: str, payload: dict[str, Any], *, timeout: float = 20) -> Any:
    config = _require_config()
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{config.url}/rest/v1/rpc/{name}", headers=_headers(config), json=payload)
        response.raise_for_status()
        return response.json() if response.content else None


def claim_ai_generation(
    *,
    cache_key: str,
    task: str,
    owner: str,
    lease_seconds: int,
    provider: str,
    requested_model: str,
    lead_id: int | None = None,
    input_hash: str | None = None,
    prompt_version: str | None = None,
    catalog_version: str | None = None,
) -> dict[str, Any]:
    """{"status": ready|claimed|busy, ...} (migration 011)."""
    return _rpc("claim_ai_generation", {
        "p_cache_key": cache_key, "p_task": task, "p_owner": owner, "p_lease_seconds": lease_seconds,
        "p_provider": provider, "p_requested_model": requested_model, "p_lead_id": lead_id,
        "p_input_hash": input_hash, "p_prompt_version": prompt_version, "p_catalog_version": catalog_version,
    }) or {}


def complete_ai_generation(*, cache_key: str, content: str, provider: str, model: str, usage: dict[str, Any]) -> bool:
    return bool(_rpc("complete_ai_generation", {
        "p_cache_key": cache_key, "p_content": content, "p_provider": provider, "p_model": model, "p_usage": usage,
    }))


def replace_ai_generation(*, cache_key: str, content: str, provider: str, model: str, usage: dict[str, Any]) -> None:
    """Overwrite a finished text (a forced regeneration)."""
    config = _require_config()
    with httpx.Client(timeout=20) as client:
        response = client.patch(
            _postgrest_url(config, "ai_generations", f"cache_key=eq.{_eq(cache_key)}"),
            headers=_headers(config, prefer="return=minimal"),
            json={"status": "ready", "content": content, "provider": provider, "model": model, "usage": usage},
        )
        response.raise_for_status()


def fail_ai_generation(*, cache_key: str, owner: str, error: str) -> None:
    _rpc("fail_ai_generation", {"p_cache_key": cache_key, "p_owner": owner, "p_error": error[:500]})


def insert_usage_event(row: dict[str, Any]) -> None:
    """One ai_token_ledger row (src/ai/usage.py builds it)."""
    config = _require_config()
    with httpx.Client(timeout=20) as client:
        response = client.post(
            _postgrest_url(config, "ai_token_ledger"),
            headers=_headers(config, prefer="return=minimal"),
            json=row,
        )
        response.raise_for_status()


def record_reservation_release(job_id: int, *, status: str) -> None:
    """Close a search job's reservation, once: its estimate stops counting as reserved."""
    config = _require_config()
    with httpx.Client(timeout=20) as client:
        existing = client.get(
            _postgrest_url(config, "ai_token_ledger", f"select=id&job_id=eq.{int(job_id)}&kind=eq.release&limit=1"),
            headers=_headers(config),
        )
        existing.raise_for_status()
        if existing.json():
            return
        response = client.post(
            _postgrest_url(config, "ai_token_ledger"),
            headers=_headers(config, prefer="return=minimal"),
            json={"job_id": int(job_id), "kind": "release", "estimated_tokens": 0, "estimated_cost_usd": 0,
                  "meta": {"job_status": status}},
        )
        response.raise_for_status()


def fetch_model_rates() -> list[dict[str, Any]]:
    config = _require_config()
    with httpx.Client(timeout=10) as client:
        response = client.get(
            _postgrest_url(
                config, "ai_model_rates",
                "select=provider,model,effective_from,input_usd_per_m,cached_input_usd_per_m,output_usd_per_m",
            ),
            headers=_headers(config),
        )
        response.raise_for_status()
        return response.json()


def fetch_spend_summary(*, today_start: datetime | None = None) -> dict[str, Any]:
    """Whole-ledger AI totals from the database (ai_spend_summary, migration 011)."""
    return _rpc("ai_spend_summary", {"p_today_start": today_start.isoformat() if today_start else None}) or {}


def fetch_opportunities(*, actor: str, is_admin: bool) -> list[dict[str, Any]]:
    return _rpc('list_opportunities', {'p_actor': actor, 'p_is_admin': is_admin}) or []


def fetch_opportunity_history(*, actor: str, is_admin: bool, lead_id: int, before: int | None) -> list[dict[str, Any]]:
    return _rpc('read_opportunity_history', {'p_actor': actor, 'p_is_admin': is_admin, 'p_lead_id': lead_id,
                                            'p_before': before, 'p_limit': 50}) or []


def change_opportunity_stage(**values) -> dict[str, Any]:
    config = _require_config()
    with httpx.Client(timeout=20) as client:
        response = client.post(config.url + '/rest/v1/rpc/change_opportunity_stage',
                               headers=_headers(config), json={'p_' + key: value for key, value in values.items()})
    if response.status_code in {400, 403, 404, 409}:
        body = response.json()
        code = str(body.get('message') or '')
        if str(body.get('code') or '').startswith('PT') and code.isupper():
            raise CommandRejected(response.status_code, code)
    response.raise_for_status()
    return response.json()
