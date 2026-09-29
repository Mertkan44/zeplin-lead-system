from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import normalize_email, require_auth, require_lead_access
from src.activity import (
    assignment_status_for_outcome,
    build_contact_result,
    build_draft_review,
    build_manual_verification,
    encode_activity_note,
    encode_draft_note,
    encode_manual_note,
    enrich_outreach_event,
    status_for_outcome,
)
from src.http_api import read_json, send_internal_error, send_json, send_options, text_field
from src.storage.supabase import (
    fetch_outreach_events,
    is_enabled as supabase_enabled,
    record_outreach_action,
    normalize_outreach_action,
    fetch_lead_assignments,
    fetch_lead_by_name,
)
from src.workflow import build_lead_workflow


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
            offset = max(int(query.get("offset", ["0"])[0]), 0)
        except ValueError:
            limit = 500
            offset = 0
        try:
            if lead_name:
                require_lead_access(user, lead_name)
            events = [enrich_outreach_event(event) for event in fetch_outreach_events(limit=None, lead_name=lead_name)]
            if user.get("role") != "admin":
                assignments = fetch_lead_assignments(
                    user_email=normalize_email(user.get("sub")), status="active", limit=None
                )
                assigned = {item.get("lead_name") for item in assignments}
                events = [event for event in events if event.get("lead_name") in assigned]
            send_json(self, 200, events[offset:offset + limit])
        except PermissionError as exc:
            send_json(self, 403, {"ok": False, "error": str(exc)})
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
        try:
            lead_name = text_field(payload, "lead_name", max_len=300)
            action = text_field(payload, "action", max_len=60)
            source = text_field(payload, "source", max_len=40) or "dashboard"
            idempotency_key = text_field(payload, "idempotency_key", max_len=120) or None
            happened_at = text_field(payload, "happened_at", max_len=40) or None
            if action not in {"contact_result_recorded", "draft_reviewed", "manual_verification_saved"}:
                note = text_field(payload, "note", max_len=4000) or None
            else:
                note = None
            if happened_at:
                from datetime import datetime
                datetime.fromisoformat(happened_at.replace("Z", "+00:00"))
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)})
            return
        if not lead_name or not action:
            send_json(self, 400, {"ok": False, "error": "lead_name and action are required"})
            return
        try:
            require_lead_access(user, lead_name)
            is_contact = action == "contact_result_recorded" or bool(payload.get("outcome"))
            if user.get("role") != "admin" and (is_contact or action in {"deal_won", "deal_lost"}):
                lead = fetch_lead_by_name(lead_name)
                if not lead:
                    send_json(self, 404, {"ok": False, "error": "lead not found"})
                    return
                lead_events = [enrich_outreach_event(item) for item in fetch_outreach_events(limit=None, lead_name=lead_name)]
                manual = next((item for item in lead_events if item.get("manual_verification")), None)
                if manual:
                    lead = {**lead, "manual_verification": {
                        **manual["manual_verification"],
                        "checked_at": manual.get("happened_at") or manual.get("created_at"),
                    }}
                if not build_lead_workflow(lead, lead_events)["ready_to_contact"]:
                    send_json(self, 409, {"ok": False, "error": "lead verification is incomplete"})
                    return
            activity = None
            draft_review = None
            if is_contact:
                action = "contact_result_recorded"
                activity = build_contact_result(payload)
                note = encode_activity_note(activity)
            elif action == "draft_reviewed":
                draft_review = build_draft_review(payload)
                note = encode_draft_note(draft_review)
            elif action == "manual_verification_saved":
                note = encode_manual_note(build_manual_verification(payload))
            action = normalize_outreach_action(action)
            outcome = activity["outcome"] if activity else None
            action_status = status_for_outcome(outcome) if outcome else {
                "deal_won": "converted", "deal_lost": "lost",
                "email_sent": "contacted", "call_completed": "contacted",
                "proposal_sent": "contacted", "follow_up_scheduled": "follow_up",
            }.get(action)
            assignment_status = (
                assignment_status_for_outcome(outcome) if outcome else
                "done" if action in {"deal_won", "deal_lost"} else None
            )
            result = record_outreach_action(
                lead_name=lead_name,
                action=action,
                note=note,
                happened_at=happened_at,
                actor_email=normalize_email(user.get("sub")),
                source=source,
                idempotency_key=idempotency_key,
                status=action_status,
                assignment_status=assignment_status,
                follow_up_at=activity.get("follow_up_at") if activity else None,
                assignment_meta={
                    "last_outcome": outcome,
                    "last_channel": activity.get("channel"),
                    "last_contact_at": happened_at,
                    "follow_up_at": activity.get("follow_up_at"),
                    "service_slugs": activity.get("service_slugs") or [],
                } if activity else {},
                activity=activity,
            )
            stored_event = result.get("event") or {}
            response_event = enrich_outreach_event(
                {
                    "lead_name": lead_name,
                    **stored_event,
                }
            )
            send_json(
                self,
                200,
                {
                    "ok": True,
                    "event": response_event,
                    "status": action_status if result.get("inserted") and not result.get("stale") else None,
                    "duplicate": not bool(result.get("inserted")),
                    "stale": bool(result.get("stale")),
                },
            )
        except PermissionError as exc:
            send_json(self, 403, {"ok": False, "error": str(exc)})
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            send_internal_error(self, exc, error="outreach save failed")
