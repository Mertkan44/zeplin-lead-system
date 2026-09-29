from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import normalize_email, require_admin, require_auth
from src.http_api import read_json, send_internal_error, send_json, send_options, text_field
from src.storage.supabase import (
    fetch_app_user_by_email,
    fetch_lead_assignment_by_id,
    fetch_lead_assignments,
    is_enabled as supabase_enabled,
    update_lead_assignment,
    upsert_lead_assignment,
    insert_audit_event,
)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="GET, POST, PATCH, OPTIONS")

    def do_GET(self):
        try:
            user = require_auth(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "login required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "error": "supabase is not configured"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        query = parse_qs(urlparse(self.path).query)
        lead_name = (query.get("lead", [None])[0] or None)
        status = (query.get("status", [None])[0] or None)
        user_email = normalize_email(query.get("user", [None])[0])
        if user.get("role") != "admin":
            user_email = normalize_email(user.get("sub"))
            status = "active"
        try:
            assignments = fetch_lead_assignments(
                user_email=user_email or None,
                lead_name=lead_name,
                status=status,
                limit=None,
            )
            send_json(self, 200, {"ok": True, "assignments": assignments}, allow_methods="GET, POST, PATCH, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="assignment fetch failed", allow_methods="GET, POST, PATCH, OPTIONS")

    def do_POST(self):
        try:
            admin = require_admin(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "admin login required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            payload = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            lead_name = text_field(payload, "lead_name", max_len=300)
            user_email = normalize_email(text_field(payload, "user_email", max_len=320))
            due_at = text_field(payload, "due_at", max_len=40) or None
            status = text_field(payload, "status", max_len=20) or "active"
            if "meta" in payload and not isinstance(payload["meta"], dict):
                raise ValueError("meta must be an object")
            if status not in {"active", "done", "snoozed", "archived"}:
                raise ValueError("status is invalid")
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if not lead_name or not user_email:
            send_json(self, 400, {"ok": False, "error": "lead_name and user_email are required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            assignee = fetch_app_user_by_email(user_email)
            if not assignee or not assignee.get("active", True):
                send_json(self, 400, {"ok": False, "error": "active assignee not found"}, allow_methods="GET, POST, PATCH, OPTIONS")
                return
            assignment = upsert_lead_assignment(
                lead_name=lead_name,
                user_email=user_email,
                assigned_by=admin.get("sub") or "admin",
                due_at=due_at,
                status=status,
                meta=payload.get("meta") if isinstance(payload.get("meta"), dict) else None,
            )
            insert_audit_event(
                actor_email=admin.get("sub"),
                event_type="lead_assigned",
                target_type="lead",
                target_key=lead_name,
                meta={"user_email": user_email, "due_at": due_at, "status": status},
            )
            send_json(self, 200, {"ok": True, "assignment": assignment}, allow_methods="GET, POST, PATCH, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="assignment save failed", allow_methods="GET, POST, PATCH, OPTIONS")

    def do_PATCH(self):
        try:
            user = require_auth(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "login required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            payload = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            assignment_id = int(payload.get("id") or 0)
        except (TypeError, ValueError):
            assignment_id = 0
        try:
            status = text_field(payload, "status", max_len=20)
            if status not in {"active", "done", "snoozed", "archived"}:
                raise ValueError("status is invalid")
            if "meta" in payload and not isinstance(payload["meta"], dict):
                raise ValueError("meta must be an object")
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if not assignment_id or not status:
            send_json(self, 400, {"ok": False, "error": "id and status are required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            assignment = fetch_lead_assignment_by_id(assignment_id)
            if not assignment:
                send_json(self, 404, {"ok": False, "error": "assignment not found"}, allow_methods="GET, POST, PATCH, OPTIONS")
                return
            if user.get("role") != "admin" and normalize_email(assignment.get("user_email")) != normalize_email(user.get("sub")):
                send_json(self, 403, {"ok": False, "error": "assignment belongs to another user"}, allow_methods="GET, POST, PATCH, OPTIONS")
                return
            if user.get("role") != "admin" and (
                assignment.get("status") != "active" or status not in {"active", "done", "snoozed"}
            ):
                send_json(self, 403, {"ok": False, "error": "assignment transition requires admin"}, allow_methods="GET, POST, PATCH, OPTIONS")
                return
            update_lead_assignment(
                assignment_id,
                status=status,
                meta=payload.get("meta") if isinstance(payload.get("meta"), dict) else None,
            )
            insert_audit_event(
                actor_email=user.get("sub"),
                event_type="assignment_updated",
                target_type="assignment",
                target_key=str(assignment_id),
                meta={"status": status},
            )
            send_json(self, 200, {"ok": True}, allow_methods="GET, POST, PATCH, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="assignment update failed", allow_methods="GET, POST, PATCH, OPTIONS")
