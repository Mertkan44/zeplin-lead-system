from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import require_admin
from src.http_api import read_json, send_internal_error, send_json, send_options
from src.storage.supabase import (
    create_search_job,
    estimate_search_tokens,
    fetch_search_jobs,
    fetch_token_summary,
    is_enabled as supabase_enabled,
)


def _clean_text(value: str | None, *, max_len: int = 80) -> str:
    return (value or "").strip()[:max_len]


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="GET, POST, OPTIONS")

    def do_GET(self):
        try:
            require_admin(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "admin login required"})
            return
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "error": "supabase is not configured"})
            return
        try:
            send_json(
                self,
                200,
                {
                    "ok": True,
                    "jobs": fetch_search_jobs(limit=20),
                    "token_summary": fetch_token_summary(),
                },
            )
        except Exception as exc:
            send_internal_error(self, exc, error="search queue fetch failed")

    def do_POST(self):
        try:
            admin = require_admin(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "admin login required"})
            return
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "error": "supabase is not configured"})
            return
        try:
            payload = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)})
            return

        query = _clean_text(payload.get("query"))
        city = _clean_text(payload.get("city"))
        deep_research = bool(payload.get("deep_research", True))
        ai_mode = _clean_text(payload.get("ai_mode") or "smart", max_len=20)
        try:
            max_results = min(max(int(payload.get("max_results") or 10), 1), 30)
        except (TypeError, ValueError):
            max_results = 10

        if not query or not city:
            send_json(self, 400, {"ok": False, "error": "query and city are required"})
            return
        if ai_mode not in {"smart", "flash", "pro"}:
            send_json(self, 400, {"ok": False, "error": "ai_mode must be smart, flash, or pro"})
            return

        try:
            job = create_search_job(
                query=query,
                city=city,
                max_results=max_results,
                deep_research=deep_research,
                ai_mode=ai_mode,
                created_by=admin.get("sub") or "admin",
            )
            estimate = estimate_search_tokens(max_results=max_results, deep_research=deep_research, ai_mode=ai_mode)
            send_json(self, 200, {"ok": True, "job": job, "estimate": estimate})
        except Exception as exc:
            send_internal_error(self, exc, error="search job creation failed")
