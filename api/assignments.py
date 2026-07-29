from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import normalize_email, require_admin, require_auth
from src.http_api import read_json, send_internal_error, send_json, send_options
from src.storage.supabase import (
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
        try:
            assignments = fetch_lead_assignments(
                user_email=user_email or None,
                lead_name=lead_name,
                status=status,
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
        lead_name = (payload.get("lead_name") or "").strip()
        user_email = normalize_email(payload.get("user_email"))
        due_at = payload.get("due_at")
        status = (payload.get("status") or "active").strip()
        if not lead_name or not user_email:
            send_json(self, 400, {"ok": False, "error": "lead_name and user_email are required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
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
        status = (payload.get("status") or "").strip()
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
