from __future__ import annotations

import hmac
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import normalize_email, require_auth
from src.config import env
from src.http_api import read_json, send_internal_error, send_json, send_options, text_field
from src.integrations.google_places import is_configured, merge_place_result, search_place
from src.storage.supabase import (
    fetch_lead_assignments,
    fetch_leads_full,
    fetch_lead_by_name,
    insert_audit_event,
    insert_run_log,
    patch_lead_fields,
)


def _parse_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _places_refreshed_at(lead: dict):
    return _parse_datetime((((lead.get("research") or {}).get("google_places") or {}).get("refreshed_at")))


def _refresh_one(lead: dict) -> tuple[dict, dict]:
    result = search_place(lead)
    updated = merge_place_result(lead, result)
    patch_lead_fields(lead["name"], lead.get("supabase_updated_at"), {
        key: updated.get(key) for key in (
            "research", "maps_url", "address", "rating", "review_count", "phone", "website"
        )
    })
    return updated, result


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="GET, POST, OPTIONS")

    def do_POST(self):
        try:
            user = require_auth(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "login required"}, allow_methods="GET, POST, OPTIONS")
            return
        try:
            payload = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, OPTIONS")
            return
        try:
            lead_name = text_field(payload, "lead_name", max_len=300)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, OPTIONS")
            return
        if not lead_name:
            send_json(self, 400, {"ok": False, "error": "lead_name is required"}, allow_methods="GET, POST, OPTIONS")
            return
        if not is_configured():
            send_json(self, 503, {"ok": False, "error": "Google Places is not configured"}, allow_methods="GET, POST, OPTIONS")
            return
        try:
            lead = fetch_lead_by_name(lead_name)
            if not lead:
                send_json(self, 404, {"ok": False, "error": "lead not found"}, allow_methods="GET, POST, OPTIONS")
                return
            if user.get("role") != "admin":
                assignments = fetch_lead_assignments(
                    user_email=normalize_email(user.get("sub")),
                    lead_name=lead_name,
                    status="active",
                )
                if not assignments:
                    send_json(self, 403, {"ok": False, "error": "lead is not assigned to this user"}, allow_methods="GET, POST, OPTIONS")
                    return
            _, result = _refresh_one(lead)
            insert_audit_event(
                actor_email=user.get("sub"),
                event_type="google_place_refreshed",
                target_type="lead",
                target_key=lead_name,
                meta={"status": result.get("status"), "confidence": result.get("match_confidence")},
            )
            send_json(self, 200, {"ok": True, "place": result}, allow_methods="GET, POST, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="Google Places refresh failed", allow_methods="GET, POST, OPTIONS")

    def do_GET(self):
        secret = env("CRON_SECRET") or ""
        authorization = self.headers.get("Authorization") or ""
        if not secret or not hmac.compare_digest(authorization, f"Bearer {secret}"):
            send_json(self, 401, {"ok": False, "error": "cron authorization required"}, allow_methods="GET, POST, OPTIONS")
            return
        if not is_configured():
            send_json(self, 503, {"ok": False, "error": "Google Places is not configured"}, allow_methods="GET, POST, OPTIONS")
            return
        try:
            batch_size = max(1, min(int(env("PLACES_REFRESH_BATCH_SIZE", "5") or 5), 10))
            stale_before = datetime.now(timezone.utc) - timedelta(days=30)
            leads = fetch_leads_full(limit=None)
            candidates = sorted(
                [lead for lead in leads if (_places_refreshed_at(lead) or datetime.min.replace(tzinfo=timezone.utc)) < stale_before],
                key=lambda lead: _places_refreshed_at(lead) or datetime.min.replace(tzinfo=timezone.utc),
            )[:batch_size]
            refreshed = []
            failed = []
            for lead in candidates:
                try:
                    _, result = _refresh_one(lead)
                    refreshed.append({"lead_name": lead.get("name"), "status": result.get("status")})
                except Exception as exc:
                    failed.append({"lead_name": lead.get("name"), "error": type(exc).__name__})
            insert_run_log(
                kind="places_refresh",
                status="success" if not failed else "partial",
                message=f"{len(refreshed)} Google Places kaydı yenilendi",
                meta={"refreshed": refreshed, "failed": failed},
            )
            send_json(self, 200, {"ok": True, "refreshed": refreshed, "failed": failed}, allow_methods="GET, POST, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="scheduled Google Places refresh failed", allow_methods="GET, POST, OPTIONS")
