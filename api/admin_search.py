from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urllib.parse import parse_qs, urlparse

from src.ai.usage import business_day_start
from src.auth import require_admin
from src.http_api import read_json, send_internal_error, send_json, send_options
from src.storage.supabase import (
    create_search_job,
    estimate_search_tokens,
    fetch_search_jobs,
    fetch_spend_summary,
    is_enabled as supabase_enabled,
)


def _clean_text(value: str | None, *, max_len: int = 80) -> str:
    return (value or "").strip()[:max_len]


def _job_options(source: dict) -> tuple[int, bool, str]:
    """(max_results, deep_research, ai_mode) from a request; raises ValueError."""
    ai_mode = _clean_text(str(source.get("ai_mode") or "smart"), max_len=20)
    if ai_mode not in {"smart", "flash", "pro"}:
        raise ValueError("ai_mode must be smart, flash, or pro")
    try:
        max_results = min(max(int(source.get("max_results") or 10), 1), 30)
    except (TypeError, ValueError):
        max_results = 10
    deep = source.get("deep_research", True)
    deep_research = deep if isinstance(deep, bool) else str(deep).lower() not in {"0", "false", "no"}
    return max_results, deep_research, ai_mode


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
        query = {key: values[0] for key, values in parse_qs(urlparse(self.path).query).items()}
        try:
            if query.get("estimate"):
                # The panel shows exactly the estimate the job will reserve.
                max_results, deep_research, ai_mode = _job_options(query)
                send_json(self, 200, {"ok": True, "estimate": estimate_search_tokens(
                    max_results=max_results, deep_research=deep_research, ai_mode=ai_mode,
                )})
                return
            send_json(
                self,
                200,
                {
                    "ok": True,
                    "jobs": fetch_search_jobs(limit=20),
                    "token_summary": fetch_spend_summary(today_start=business_day_start()),
                },
            )
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)})
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
        try:
            max_results, deep_research, ai_mode = _job_options(payload)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)})
            return

        if not query or not city:
            send_json(self, 400, {"ok": False, "error": "query and city are required"})
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
            send_json(self, 200, {"ok": True, "job": job, "estimate": {
                "estimated_tokens": job.get("estimated_tokens"),
                "estimated_cost_usd": job.get("estimated_cost_usd"),
            }})
        except Exception as exc:
            send_internal_error(self, exc, error="search job creation failed")
