from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import require_auth, require_lead_access
from src.http_api import read_json, send_internal_error, send_json, send_options
from src.storage.supabase import insert_audit_event, is_enabled as supabase_enabled, set_lead_status


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="POST, OPTIONS")

    def do_POST(self):
        try:
            user = require_auth(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "login required"}, allow_methods="POST, OPTIONS")
            return
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "error": "supabase is not configured"}, allow_methods="POST, OPTIONS")
            return
        try:
            payload = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="POST, OPTIONS")
            return
        name = (payload.get("name") or "").strip()
        status = (payload.get("status") or "").strip()
        if not name or not status:
            send_json(self, 400, {"ok": False, "error": "name and status are required"}, allow_methods="POST, OPTIONS")
            return
        try:
            require_lead_access(user, name)
            set_lead_status(name, status)
            insert_audit_event(
                actor_email=user.get("sub"),
                event_type="lead_status_changed",
                target_type="lead",
                target_key=name,
                meta={"status": status},
            )
            send_json(self, 200, {"ok": True}, allow_methods="POST, OPTIONS")
        except PermissionError as exc:
            send_json(self, 403, {"ok": False, "error": str(exc)}, allow_methods="POST, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="status save failed", allow_methods="POST, OPTIONS")
