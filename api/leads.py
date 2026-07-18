from http.server import BaseHTTPRequestHandler
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.storage.supabase import fetch_leads_full, is_enabled as supabase_enabled


def _local_leads() -> list[dict]:
    return json.loads((ROOT / "leads_final.json").read_text(encoding="utf-8"))


def _send_json(handler: BaseHTTPRequestHandler, status: int, payload) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        limit_raw = query.get("limit", ["500"])[0]
        try:
            limit = min(int(limit_raw), 1000)
        except ValueError:
            limit = 500
        if supabase_enabled():
            try:
                _send_json(self, 200, fetch_leads_full(limit=limit))
                return
            except Exception:
                _send_json(self, 200, _local_leads()[:limit])
                return
        _send_json(self, 200, _local_leads()[:limit])
