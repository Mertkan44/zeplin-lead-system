from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path
import os
import re

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import current_user
from src.http_api import send_internal_error, send_json, send_options
from src.storage.supabase import is_enabled as supabase_enabled, schema_status


class handler(BaseHTTPRequestHandler):
    """Readiness probe: is the database schema the one this code expects?

    Anyone gets {ok, ready}; admins also get the version and failed checks.
    Responds 503 when not ready so uptime monitors can alert on it.
    """

    def do_OPTIONS(self):
        send_options(self, allow_methods="GET, OPTIONS")

    def do_GET(self):
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "ready": False, "error": "supabase is not configured"}, allow_methods="GET, OPTIONS")
            return
        try:
            status = schema_status()
        except Exception as exc:
            send_internal_error(self, exc, error="readiness check failed", allow_methods="GET, OPTIONS")
            return
        user = current_user(self)
        payload = {"ok": status["ready"], "ready": status["ready"]}
        commit = os.getenv("VERCEL_GIT_COMMIT_SHA", "")
        if re.fullmatch(r"[0-9a-f]{40}", commit):
            payload["release"] = commit
        if user and user.get("role") == "admin":
            payload["schema"] = status
        send_json(self, 200 if status["ready"] else 503, payload, allow_methods="GET, OPTIONS")
