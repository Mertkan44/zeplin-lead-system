from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import normalize_email, require_auth, require_lead_access
from src.http_api import read_json, send_internal_error, send_json, send_options
from src.storage.supabase import (
    fetch_lead_assignments,
    fetch_outreach_events,
    insert_outreach_event,
    is_enabled as supabase_enabled,
)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="GET, POST, OPTIONS")

    def do_GET(self):
        try:
            user = require_auth(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "login required"})
            return
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "error": "supabase is not configured"})
            return
        query = parse_qs(urlparse(self.path).query)
        lead_name = query.get("lead", [None])[0]
        try:
            limit = min(max(int(query.get("limit", ["500"])[0]), 1), 1000)
        except ValueError:
            limit = 500
        try:
            events = fetch_outreach_events(limit=limit)
            if user.get("role") != "admin":
                assignments = fetch_lead_assignments(
                    user_email=normalize_email(user.get("sub")), status="active", limit=1000
                )
                assigned = {item.get("lead_name") for item in assignments}
                events = [event for event in events if event.get("lead_name") in assigned]
            if lead_name:
                events = [event for event in events if event.get("lead_name") == lead_name]
            send_json(self, 200, events)
        except Exception as exc:
            send_internal_error(self, exc, error="outreach fetch failed")

    def do_POST(self):
        try:
            user = require_auth(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "login required"})
            return
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "error": "supabase is not configured"})
            return
        try:
            payload = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)})
            return
        lead_name = (payload.get("lead_name") or "").strip()
        action = (payload.get("action") or "").strip()
        if not lead_name or not action:
            send_json(self, 400, {"ok": False, "error": "lead_name and action are required"})
            return
        try:
            require_lead_access(user, lead_name)
            insert_outreach_event(
                lead_name=lead_name,
                action=action,
                note=payload.get("note"),
                happened_at=payload.get("happened_at"),
                actor_email=normalize_email(user.get("sub")),
                source=(payload.get("source") or "dashboard")[:40],
                idempotency_key=(payload.get("idempotency_key") or None),
            )
            send_json(self, 200, {"ok": True})
        except PermissionError as exc:
            send_json(self, 403, {"ok": False, "error": str(exc)})
        except Exception as exc:
            send_internal_error(self, exc, error="outreach save failed")
