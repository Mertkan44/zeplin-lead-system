from http.server import BaseHTTPRequestHandler
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import normalize_email, require_auth
from src.http_api import send_json, send_options
from src.storage.supabase import (
    attach_assignments_to_leads,
    fetch_lead_assignments,
    fetch_leads_full,
    fetch_outreach_events,
    is_enabled as supabase_enabled,
)


def _lead_ready_for_email(lead: dict) -> bool:
    return bool(lead.get("ai_email") and (lead.get("phone") or (lead.get("website") or {}).get("website_url")))


def _lead_missing_contact(lead: dict) -> bool:
    return not bool(lead.get("phone") or lead.get("address"))


def _is_today_event(event: dict, action: str) -> bool:
    if event.get("action") != action:
        return False
    happened_at = event.get("happened_at") or event.get("created_at")
    if not happened_at:
        return False
    try:
        raw = str(happened_at).replace("Z", "+00:00")
        event_date = datetime.fromisoformat(raw).astimezone(timezone.utc).date()
    except ValueError:
        return False
    return event_date == datetime.now(timezone.utc).date()


def _summary(leads: list[dict], assignments: list[dict], events: list[dict]) -> dict:
    active_assignments = [item for item in assignments if item.get("status") == "active"]
    return {
        "lead_count": len(leads),
        "assigned_count": len(active_assignments),
        "today_call_count": sum(1 for event in events if _is_today_event(event, "call_made")),
        "mail_ready_count": sum(1 for lead in leads if _lead_ready_for_email(lead)),
        "missing_info_count": sum(1 for lead in leads if _lead_missing_contact(lead)),
        "follow_up_count": sum(1 for lead in leads if lead.get("status") == "follow_up"),
        "won_count": sum(1 for lead in leads if lead.get("status") == "converted"),
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="GET, OPTIONS")

    def do_GET(self):
        try:
            user = require_auth(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "login required"}, allow_methods="GET, OPTIONS")
            return
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "error": "supabase is not configured"}, allow_methods="GET, OPTIONS")
            return
        try:
            user_email = normalize_email(user.get("sub"))
            leads = fetch_leads_full(limit=1000)
            assignments = fetch_lead_assignments(
                user_email=None if user.get("role") == "admin" else user_email,
                limit=1000,
            )
            if user.get("role") != "admin":
                assigned_names = {item.get("lead_name") for item in assignments}
                leads = [lead for lead in leads if lead.get("name") in assigned_names]
            leads = attach_assignments_to_leads(leads, assignments)
            events = fetch_outreach_events(limit=500)
            if user.get("role") != "admin":
                assigned_names = {lead.get("name") for lead in leads}
                events = [event for event in events if event.get("lead_name") in assigned_names]
            send_json(
                self,
                200,
                {
                    "ok": True,
                    "user": {
                        "email": user_email,
                        "name": user.get("name"),
                        "role": user.get("role"),
                        "title": user.get("title"),
                        "avatar_url": user.get("avatar_url"),
                    },
                    "summary": _summary(leads, assignments, events),
                    "leads": leads,
                    "assignments": assignments,
                    "outreach": events,
                },
                allow_methods="GET, OPTIONS",
            )
        except Exception as exc:
            send_json(self, 502, {"ok": False, "error": str(exc)}, allow_methods="GET, OPTIONS")
