from http.server import BaseHTTPRequestHandler
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import require_auth
from src.storage.supabase import is_enabled as supabase_enabled, set_lead_status


def _send_json(handler: BaseHTTPRequestHandler, status: int, payload) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            require_auth(self)
        except PermissionError:
            _send_json(self, 401, {"ok": False, "error": "login required"})
            return
        if not supabase_enabled():
            _send_json(self, 503, {"ok": False, "error": "supabase is not configured"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            _send_json(self, 400, {"ok": False, "error": "invalid json"})
            return
        name = payload.get("name")
        status = payload.get("status")
        if not name or not status:
            _send_json(self, 400, {"ok": False, "error": "name and status are required"})
            return
        try:
            set_lead_status(name, status)
            _send_json(self, 200, {"ok": True})
        except Exception as exc:
            _send_json(self, 502, {"ok": False, "error": str(exc)})
