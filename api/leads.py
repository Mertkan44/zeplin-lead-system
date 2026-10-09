from http.server import BaseHTTPRequestHandler
import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import lead_read_scope, normalize_email, require_auth
from src.activity import enrich_outreach_event, manual_verification_from_event
from src.http_api import send_internal_error, send_json, send_options
from src.ai.generator import ai_state
from src.lead_facts import apply_effective_facts
from src.workflow import build_lead_workflow
from src.storage.supabase import (
    LEAD_STATUSES,
    attach_assignments_to_leads,
    fetch_activity_states,
    fetch_lead_assignments,
    fetch_lead_by_id,
    fetch_lead_by_name,
    is_enabled as supabase_enabled,
    list_leads_page,
)

_METHODS = "GET, OPTIONS"


def encode_cursor(cursor: dict | None) -> str | None:
    if not cursor:
        return None
    raw = json.dumps({"p": cursor.get("priority"), "i": cursor.get("id")}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(value: str | None) -> tuple[int | None, int | None]:
    """Returns (after_priority, after_id); raises ValueError on a malformed cursor."""
    if not value:
        return None, None
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        priority, lead_id = data.get("p"), data.get("i")
    except (ValueError, AttributeError, UnicodeDecodeError) as exc:
        raise ValueError("cursor is invalid") from exc
    for item in (priority, lead_id):
        if item is not None and (isinstance(item, bool) or not isinstance(item, int)):
            raise ValueError("cursor is invalid")
    if lead_id is None:
        raise ValueError("cursor is invalid")
    return priority, lead_id


class handler(BaseHTTPRequestHandler):
    """GET /api/leads            -> one page: {items, next_cursor, total, total_is_exact}
       GET /api/leads?id=123     -> one lead with assignments and current activity
       GET /api/leads?name=...   -> same, by name

    List filters: cursor, limit (1-100), q (name/city/sector), status.
    Access is decided in the database (public.readable_leads / list_leads)."""

    def do_OPTIONS(self):
        send_options(self, allow_methods=_METHODS)

    def do_GET(self):
        try:
            user = require_auth(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "login required"}, allow_methods=_METHODS)
            return
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "error": "supabase is not configured"}, allow_methods=_METHODS)
            return
        query = parse_qs(urlparse(self.path).query)

        def first(key: str) -> str | None:
            return query.get(key, [None])[0] or None

        try:
            if first("id") or first("name"):
                self._detail(user, lead_id=first("id"), name=first("name"))
            else:
                self._list(user, first)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods=_METHODS)
        except Exception as exc:
            send_internal_error(self, exc, error="lead fetch failed", allow_methods=_METHODS)

    def _list(self, user, first) -> None:
        after_priority, after_id = decode_cursor(first("cursor"))
        try:
            limit = int(first("limit") or 50)
        except ValueError as exc:
            raise ValueError("limit must be an integer") from exc
        status = first("status")
        if status is not None and status not in LEAD_STATUSES:
            raise ValueError("status is invalid")
        search = (first("q") or "").strip()[:80] or None
        page = list_leads_page(
            actor_email=normalize_email(user.get("sub")),
            is_admin=user.get("role") == "admin",
            after_priority=after_priority,
            after_id=after_id,
            limit=min(max(limit, 1), 100),
            search=search,
            status=status,
        )
        send_json(
            self,
            200,
            {
                "ok": True,
                "items": page.get("items") or [],
                "next_cursor": encode_cursor(page.get("next_cursor")),
                "total": page.get("total"),
                "total_is_exact": bool(page.get("total_is_exact")),
            },
            allow_methods=_METHODS,
        )

    def _detail(self, user, *, lead_id, name) -> None:
        if lead_id is not None:
            try:
                lead = fetch_lead_by_id(int(lead_id))
            except ValueError as exc:
                raise ValueError("id must be an integer") from exc
        else:
            lead = fetch_lead_by_name(name)
        scope = lead_read_scope(user)
        # Same answer for "missing" and "not yours": do not confirm other people's leads.
        if not lead or (scope is not None and lead.get("name") not in scope[0]):
            send_json(self, 404, {"ok": False, "error": "lead not found"}, allow_methods=_METHODS)
            return
        assignments = (
            fetch_lead_assignments(lead_name=lead["name"], limit=50) if scope is None
            else [item for item in scope[1] if item.get("lead_name") == lead["name"]]
        )
        lead = attach_assignments_to_leads([lead], assignments)[0]
        state = fetch_activity_states([lead["lead_id"]]).get(lead["lead_id"]) or {}
        latest_contact = enrich_outreach_event(dict(state["latest_contact"])) if state.get("latest_contact") else None
        activity = {
            "latest_contact": latest_contact,
            "latest_manual_verification": (
                enrich_outreach_event(dict(state["latest_manual_verification"]))
                if state.get("latest_manual_verification") else None
            ),
            "contact_result_count": state.get("contact_result_count", 0),
        }
        # The same effective values and stage the workspace shows.
        lead = apply_effective_facts(
            {**lead, "manual_verification": manual_verification_from_event(state.get("latest_manual_verification"))}
        )
        lead["workflow"] = build_lead_workflow(lead, [latest_contact] if latest_contact else [])
        lead["ai_state"] = ai_state(lead)
        send_json(self, 200, {"ok": True, "lead": lead, "activity": activity}, allow_methods=_METHODS)
