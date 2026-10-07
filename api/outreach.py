from http.server import BaseHTTPRequestHandler
import re
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
    contact_request_hash,
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
    CommandRejected,
    fetch_outreach_events,
    insert_outreach_event,
    is_enabled as supabase_enabled,
    record_contact_result,
)

_IDEMPOTENCY_KEY = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


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
            if action == "contact_result_recorded" or payload.get("outcome"):
                self._record_contact_result(user, lead_name, payload)
                return
            note = payload.get("note")
            if action == "draft_reviewed":
                note = encode_draft_note(build_draft_review(payload))
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
            send_json(self, 200, {"ok": True, "event": response_event, "status": None})
        except CommandRejected as exc:
            send_json(self, exc.status, {"ok": False, "error": exc.code, "code": exc.code})
        except PermissionError as exc:
            send_json(self, 403, {"ok": False, "error": str(exc)})
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            send_internal_error(self, exc, error="outreach save failed")

    def _record_contact_result(self, user: dict, lead_name: str, payload: dict) -> None:
        """One transaction: event, lead status, owner follow-up and audit (migration 009)."""
        idempotency_key = str(
            payload.get("idempotency_key") or self.headers.get("Idempotency-Key") or ""
        ).strip()
        if not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            raise ValueError("idempotency_key must be a UUID")
        expected_revision = payload.get("expected_revision")
        if expected_revision is not None and (
            isinstance(expected_revision, bool) or not isinstance(expected_revision, int)
        ):
            raise ValueError("expected_revision must be an integer")
        activity = build_contact_result(payload)
        outcome = activity["outcome"]
        result = record_contact_result(
            idempotency_key=idempotency_key,
            request_hash=contact_request_hash(lead_name, payload),
            actor_email=normalize_email(user.get("sub")),
            actor_is_admin=user.get("role") == "admin",
            lead_name=lead_name,
            expected_revision=expected_revision,
            activity=activity,
            note=encode_activity_note(activity),
            lead_status=status_for_outcome(outcome),
            assignment_status=assignment_status_for_outcome(outcome),
        )
        event = enrich_outreach_event(
            {
                "id": result.get("event_id"),
                "lead_name": lead_name,
                "action": "contact_result_recorded",
                "note": encode_activity_note({**activity, "follow_up_at": result.get("follow_up_at") or activity.get("follow_up_at")}),
                "happened_at": result.get("happened_at"),
                "actor_email": result.get("actor_email"),
                "source": "dashboard",
                "idempotency_key": idempotency_key,
            }
        )
        send_json(
            self,
            200,
            {
                "ok": True,
                "event": event,
                "status": result.get("lead_status"),
                "lead_revision": result.get("lead_revision"),
                "replayed": bool(result.get("replayed")),
            },
        )
