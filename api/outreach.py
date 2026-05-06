from http.server import BaseHTTPRequestHandler
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.storage.supabase import (
    fetch_outreach_events,
    insert_outreach_event,
    is_enabled as supabase_enabled,
)


def _send_json(handler: BaseHTTPRequestHandler, status: int, payload) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if not supabase_enabled():
            _send_json(self, 200, [])
            return
        query = parse_qs(urlparse(self.path).query)
        limit_raw = query.get("limit", ["500"])[0]
        lead_name = query.get("lead", [None])[0]
        try:
            limit = min(int(limit_raw), 1000)
        except ValueError:
            limit = 500
        try:
            events = fetch_outreach_events(limit=limit)
            if lead_name:
                events = [event for event in events if event.get("lead_name") == lead_name]
            _send_json(self, 200, events)
        except Exception as exc:
            _send_json(self, 502, {"ok": False, "error": f"supabase outreach fetch failed: {exc}"})

    def do_POST(self):
        if not supabase_enabled():
            _send_json(self, 503, {"ok": False, "error": "supabase is not configured"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            _send_json(self, 400, {"ok": False, "error": "invalid json"})
            return
        lead_name = payload.get("lead_name")
        action = payload.get("action")
        note = payload.get("note")
        happened_at = payload.get("happened_at")
        if not lead_name or not action:
            _send_json(self, 400, {"ok": False, "error": "lead_name and action are required"})
            return
        try:
            insert_outreach_event(
                lead_name=lead_name,
                action=action,
                note=note,
                happened_at=happened_at,
            )
            _send_json(self, 200, {"ok": True})
        except Exception as exc:
            _send_json(self, 502, {"ok": False, "error": str(exc)})
