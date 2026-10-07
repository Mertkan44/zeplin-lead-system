from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import lead_read_scope, require_auth
from src.http_api import send_internal_error, send_json, send_options
from src.storage.supabase import fetch_leads_full, is_enabled as supabase_enabled


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

        query = parse_qs(urlparse(self.path).query)
        try:
            limit = min(max(int(query.get("limit", ["500"])[0]), 1), 1000)
        except ValueError:
            limit = 500
        try:
            leads = fetch_leads_full(limit=limit)
            scope = lead_read_scope(user)
            if scope is not None:
                readable_names, _ = scope
                leads = [lead for lead in leads if lead.get("name") in readable_names]
            send_json(self, 200, leads, allow_methods="GET, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="lead fetch failed", allow_methods="GET, OPTIONS")
