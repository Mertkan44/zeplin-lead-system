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
from src.http_api import read_json, send_internal_error, send_json, send_options
from src.integrations.google_places import ambiguous_candidate_ids, is_configured, merge_place_result, search_place
from src.storage.supabase import (
    fetch_lead_assignments,
    fetch_lead_by_name,
    fetch_leads_by_names,
    fetch_place_owner,
    fetch_places_refresh_state,
    insert_audit_event,
    insert_run_log,
    upsert_leads,
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


STALE_AFTER_DAYS = 30


def _refresh_one(lead: dict, *, place_id: str | None = None, verified_by: str | None = None) -> tuple[dict, dict]:
    result = search_place(lead, place_id=place_id, verified_by=verified_by)
    if result.get("status") == "verified":
        owner = fetch_place_owner(str(result.get("place_id")))
        if owner is not None and owner != lead.get("lead_id"):
            # The same Google business is already another lead: a duplicate to
            # merge (scripts/lead_identity_report.py), not data to copy over.
            result = {
                "status": "ambiguous",
                "reason": "place_owned_by_other_lead",
                "attempted_at": result.get("attempted_at"),
                "candidates": [],
                "query": result.get("query"),
            }
    if result.get("status") == "provider_error":
        return lead, result
    updated = merge_place_result(lead, result)
    upsert_leads([updated])
    return updated, result


def _last_lookup(row: dict):
    """Latest verified refresh or definitive attempt; provider errors retry sooner."""
    times = [_parse_datetime(row.get("refreshed_at"))]
    if row.get("attempt_status") != "provider_error":
        times.append(_parse_datetime(row.get("attempted_at")))
    times = [value for value in times if value]
    return max(times) if times else None


def _place_summary(result: dict) -> dict:
    return {
        key: result.get(key)
        for key in (
            "status", "reason", "match_method", "match_confidence", "location_match",
            "match_evidence", "display_name", "formatted_address", "candidates",
        )
        if result.get(key) is not None
    }


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
        lead_name = str(payload.get("lead_name") or "").strip()
        chosen_place_id = str(payload.get("place_id") or "").strip() or None
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
            if chosen_place_id and chosen_place_id not in ambiguous_candidate_ids(lead):
                send_json(self, 400, {"ok": False, "error": "place_id is not a candidate for this lead"}, allow_methods="GET, POST, OPTIONS")
                return
            _, result = _refresh_one(lead, place_id=chosen_place_id, verified_by=normalize_email(user.get("sub")))
            insert_audit_event(
                actor_email=user.get("sub"),
                event_type="google_place_refreshed",
                target_type="lead",
                target_key=lead_name,
                meta={
                    "status": result.get("status"),
                    "reason": result.get("reason") or result.get("error"),
                    "method": result.get("match_method"),
                    "place_id": result.get("place_id"),
                    "confidence": result.get("match_confidence"),
                },
            )
            if result.get("status") == "provider_error":
                send_json(
                    self,
                    502,
                    {"ok": False, "error": "Google Places şu anda yanıt vermedi; biraz sonra tekrar dene.", "place": _place_summary(result)},
                    allow_methods="GET, POST, OPTIONS",
                )
                return
            send_json(self, 200, {"ok": True, "place": _place_summary(result)}, allow_methods="GET, POST, OPTIONS")
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
            stale_before = datetime.now(timezone.utc) - timedelta(days=STALE_AFTER_DAYS)
            oldest = datetime.min.replace(tzinfo=timezone.utc)
            stale = sorted(
                (
                    row for row in fetch_places_refresh_state()
                    if (_last_lookup(row) or oldest) < stale_before
                ),
                key=lambda row: _last_lookup(row) or oldest,
            )[:batch_size]
            candidates = fetch_leads_by_names([row["name"] for row in stale])
            refreshed = []
            failed = []
            for lead in candidates:
                try:
                    _, result = _refresh_one(lead)
                    if result.get("status") == "provider_error":
                        failed.append({"lead_name": lead.get("name"), "error": result.get("error")})
                    else:
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
