from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import lead_read_scope, normalize_email, require_auth, require_lead_access
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
from src.http_api import read_json, send_internal_error, send_json, send_options
from src.storage.supabase import (
    fetch_lead_assignments,
    fetch_outreach_events,
    insert_outreach_event,
    is_enabled as supabase_enabled,
    set_lead_status,
    update_lead_assignment,
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
            events = [enrich_outreach_event(event) for event in fetch_outreach_events(limit=limit)]
            scope = lead_read_scope(user)
            if scope is not None:
                readable_names, _ = scope
                events = [event for event in events if event.get("lead_name") in readable_names]
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
            activity = None
            draft_review = None
            note = payload.get("note")
            if action == "contact_result_recorded" or payload.get("outcome"):
                action = "contact_result_recorded"
                activity = build_contact_result(payload)
                note = encode_activity_note(activity)
            elif action == "draft_reviewed":
                draft_review = build_draft_review(payload)
                note = encode_draft_note(draft_review)
            elif action == "manual_verification_saved":
                note = encode_manual_note(build_manual_verification(payload))
            insert_outreach_event(
                lead_name=lead_name,
                action=action,
                note=note,
                happened_at=payload.get("happened_at"),
                actor_email=normalize_email(user.get("sub")),
                source=(payload.get("source") or "dashboard")[:40],
                idempotency_key=(payload.get("idempotency_key") or None),
            )
            if activity:
                outcome = activity["outcome"]
                set_lead_status(lead_name, status_for_outcome(outcome))
                active_assignments = fetch_lead_assignments(
                    lead_name=lead_name,
                    status="active",
                    limit=10,
                )
                if active_assignments:
                    assignment = active_assignments[0]
                    previous_meta = assignment.get("meta") or {}
                    update_lead_assignment(
                        int(assignment["id"]),
                        status=assignment_status_for_outcome(outcome),
                        due_at=activity.get("follow_up_at"),
                        meta={
                            **previous_meta,
                            "last_outcome": outcome,
                            "last_channel": activity.get("channel"),
                            "last_contact_at": payload.get("happened_at"),
                            "follow_up_at": activity.get("follow_up_at"),
                            "service_slugs": activity.get("service_slugs") or [],
                        },
                    )
            response_event = enrich_outreach_event(
                {
                    "lead_name": lead_name,
                    "action": action,
                    "note": note,
                    "happened_at": payload.get("happened_at"),
                    "actor_email": normalize_email(user.get("sub")),
                    "source": (payload.get("source") or "dashboard")[:40],
                    "idempotency_key": payload.get("idempotency_key"),
                }
            )
            send_json(
                self,
                200,
                {
                    "ok": True,
                    "event": response_event,
                    "status": status_for_outcome(activity["outcome"]) if activity else None,
                },
            )
        except PermissionError as exc:
            send_json(self, 403, {"ok": False, "error": str(exc)})
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            send_internal_error(self, exc, error="outreach save failed")
