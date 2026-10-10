from http.server import BaseHTTPRequestHandler
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from collections import Counter
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import lead_read_scope, normalize_email, require_auth
from src.activity import enrich_outreach_event, manual_verification_from_event
from src.http_api import send_internal_error, send_json, send_options
from src.metrics import PERIODS, WEEKS, build_metrics, period_bounds
from src.opportunities import command as opportunity_command
from src.sales_assistant import build_sales_playbook
from src.research_brief import build_research_brief
from src.workflow import build_lead_workflow, build_team_performance
from src.integrations.google_places import is_configured as places_configured
from src.lead_facts import apply_effective_facts
from src.ai.generator import ai_state
from src.storage.supabase import (
    attach_assignments_to_leads,
    fetch_activity_states,
    fetch_all_assignments,
    fetch_all_leads,
    fetch_events_since,
    fetch_leads_by_names,
    is_enabled as supabase_enabled,
    schema_status,
    CommandRejected,
    fetch_opportunities,
    fetch_opportunity_history,
    change_opportunity_stage,
)

# Recent events feed today's counts and the activity feed. Current state (latest
# contact result, latest manual verification) comes from lead_activity_state, so
# it does not depend on this window; a lead's full timeline is /api/outreach?lead=.
ACTIVITY_WINDOW_DAYS = 30
# The browser gets at most this many window events (newest first) plus every
# lead's latest contact and verification; counts still use the whole window.
FEED_EVENT_LIMIT = 1000


def _lead_ready_for_email(lead: dict) -> bool:
    research = ((lead.get("research") or {}).get("website") or {})
    emails = research.get("emails") or []
    return bool(lead.get("ai_email") and (lead.get("email") or emails))


def _lead_missing_contact(lead: dict) -> bool:
    return not bool(lead.get("phone") or lead.get("address"))


def _is_today_event(event: dict, action: str) -> bool:
    if event.get("action") != action:
        return False
    happened_at = event.get("happened_at") or event.get("created_at")
    if not happened_at:
        return False
    try:
        raw = str(happened_at).replace("Z", "+00:00")
        event_date = datetime.fromisoformat(raw).astimezone(ZoneInfo("Europe/Istanbul")).date()
    except ValueError:
        return False
    return event_date == datetime.now(ZoneInfo("Europe/Istanbul")).date()


def _summary(
    leads: list[dict],
    assignments: list[dict],
    events: list[dict],
    latest_results: dict[str, dict],
) -> dict:
    active_assignments = [item for item in assignments if item.get("status") == "active"]
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    due_follow_ups = []
    closed_names = {
        lead.get("name") for lead in leads if lead.get("status") in {"converted", "lost"}
    }
    for lead_name, event in latest_results.items():
        follow_up_at = event.get("follow_up_at")
        if not follow_up_at or lead_name in closed_names:
            continue
        try:
            due = datetime.fromisoformat(str(follow_up_at).replace("Z", "+00:00")).astimezone(
                ZoneInfo("Europe/Istanbul")
            )
        except ValueError:
            continue
        if due <= now:
            due_follow_ups.append(event)
    today_results = [
        event for event in events if _is_today_event(event, "contact_result_recorded")
    ]
    overdue_assignments = []
    for assignment in active_assignments:
        due_at = assignment.get("due_at")
        if not due_at:
            continue
        try:
            due = datetime.fromisoformat(str(due_at).replace("Z", "+00:00")).astimezone(
                ZoneInfo("Europe/Istanbul")
            )
        except ValueError:
            continue
        if due <= now:
            overdue_assignments.append(assignment)

    service_counts = Counter(
        slug
        for event in events
        if event.get("action") == "contact_result_recorded"
        and event.get("outcome") in {"reached_interested", "proposal_requested"}
        for slug in (event.get("service_slugs") or [])
    )
    return {
        "lead_count": len(leads),
        "assigned_count": len(active_assignments),
        "unassigned_count": sum(1 for lead in leads if not lead.get("assigned_to")),
        "verification_pending_count": sum(
            1 for lead in leads
            if (lead.get("workflow") or {}).get("stage") == "verification_required"
        ),
        "ready_to_contact_count": sum(
            1 for lead in leads
            if (lead.get("workflow") or {}).get("stage") == "ready_to_contact"
        ),
        "today_call_count": sum(
            1 for event in events
            if _is_today_event(event, "contact_result_recorded") and event.get("channel") == "phone"
        ),
        "today_result_count": len(today_results),
        "today_no_answer_count": sum(1 for event in today_results if event.get("outcome") == "no_answer"),
        "today_interested_count": sum(
            1 for event in today_results
            if event.get("outcome") in {"reached_interested", "proposal_requested"}
        ),
        "today_follow_up_created_count": sum(1 for event in today_results if event.get("follow_up_at")),
        "mail_ready_count": sum(1 for lead in leads if _lead_ready_for_email(lead)),
        "missing_info_count": sum(1 for lead in leads if _lead_missing_contact(lead)),
        "follow_up_count": sum(1 for lead in leads if lead.get("status") == "follow_up"),
        "follow_up_due_count": len(due_follow_ups),
        "overdue_follow_up_count": len(overdue_assignments),
        "service_interest": [
            {"slug": slug, "count": count} for slug, count in service_counts.most_common(8)
        ],
        "won_count": sum(1 for lead in leads if lead.get("status") == "converted"),
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="GET, POST, OPTIONS")

    def do_POST(self):
        from src.http_api import read_json
        try:
            user = require_auth(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "login required"})
            return
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "error": "supabase is not configured"})
            return
        if (parse_qs(urlparse(self.path).query).get("view") or [""])[0] != "pipeline":
            send_json(self, 400, {"ok": False, "error": "view= pipeline required"})
            return
        try:
            values = opportunity_command(read_json(self))
            result = change_opportunity_stage(actor=normalize_email(user.get("sub")), is_admin=user.get("role") == "admin", **values)
            send_json(self, 200, {"ok": True, **result})
        except CommandRejected as exc:
            send_json(self, exc.status, {"ok": False, "error": exc.code, "code": exc.code})
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            send_internal_error(self, exc, error="opportunity save failed")

    def _send_pipeline(self, user, query):
        try:
            actor = normalize_email(user.get("sub"))
            is_admin = user.get("role") == "admin"
            lead_raw = (query.get("lead_id") or [None])[0]
            if lead_raw is not None:
                before_raw = (query.get("before") or [None])[0]
                lead_id = int(lead_raw)
                before = int(before_raw) if before_raw else None
                if lead_id <= 0 or before is not None and before <= 0:
                    raise ValueError("invalid history cursor")
                items = fetch_opportunity_history(actor=actor, is_admin=is_admin, lead_id=lead_id, before=before)
                send_json(self, 200, {"ok": True, "items": items, "next_before": items[-1]["id"] if len(items) == 50 else None})
            else:
                send_json(self, 200, {"ok": True, "opportunities": fetch_opportunities(actor=actor, is_admin=is_admin)})
        except ValueError:
            send_json(self, 400, {"ok": False, "error": "Geçerli işletme kimliği ve tarihçe imleci gerekli."})
        except Exception as exc:
            send_internal_error(self, exc, error="opportunity fetch failed")

    def _send_metrics(self, user: dict, period: str) -> None:
        """GET /api/workspace?view=metrics&period=7|30|90|all (src/metrics.py)."""
        if period not in PERIODS:
            send_json(self, 400, {"ok": False, "error": "period must be one of 7, 30, 90, all"}, allow_methods="GET, OPTIONS")
            return
        try:
            scope = lead_read_scope(user)
            if scope is None:
                leads = fetch_all_leads()
            else:
                readable_names, _assignments = scope
                leads = fetch_leads_by_names(readable_names) if readable_names else []
            names = {lead.get("name") for lead in leads}
            lead_ids = [lead.get("lead_id") for lead in leads if lead.get("lead_id") is not None]
            states = fetch_activity_states(None if scope is None else lead_ids) if lead_ids or scope is None else {}
            now = datetime.now(timezone.utc)
            start, _end = period_bounds(period, now)
            # Events for the period and for the weekly series, whichever reaches back further.
            weekly_start = now - timedelta(weeks=WEEKS + 1)
            since = weekly_start if start is None or start > weekly_start else start
            since_iso = "1970-01-01T00:00:00+00:00" if start is None else since.isoformat()
            events = fetch_events_since(since_iso, None if scope is None else names) if names else []
            metrics = build_metrics(leads, events, states, period=period, now=now)
            send_json(self, 200, {"ok": True, "metrics": metrics}, allow_methods="GET, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="metrics failed", allow_methods="GET, OPTIONS")

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
        if (query.get("view") or [""])[0] == "pipeline":
            self._send_pipeline(user, query)
            return
        if (query.get("view") or [""])[0] == "metrics":
            self._send_metrics(user, (query.get("period") or ["30"])[0])
            return
        try:
            user_email = normalize_email(user.get("sub"))
            scope = lead_read_scope(user)
            if scope is None:
                leads = fetch_all_leads()
                assignments = fetch_all_assignments()
            else:
                readable_names, assignments = scope
                leads = fetch_leads_by_names(readable_names) if readable_names else []
            leads = attach_assignments_to_leads(leads, assignments)
            visible_names = {lead.get("name") for lead in leads}
            lead_ids = [lead.get("lead_id") for lead in leads if lead.get("lead_id") is not None]
            states = fetch_activity_states(None if scope is None else lead_ids) if lead_ids or scope is None else {}
            since = (datetime.now(timezone.utc) - timedelta(days=ACTIVITY_WINDOW_DAYS)).isoformat()
            events = [
                enrich_outreach_event(event)
                for event in (fetch_events_since(since, None if scope is None else visible_names) if visible_names else [])
            ]
            feed = events[:FEED_EVENT_LIMIT]
            feed_truncated = len(events) > FEED_EVENT_LIMIT

            latest_results: dict[str, dict] = {}
            latest_manual: dict[str, dict] = {}
            won_by_actor: Counter = Counter()
            seen_event_ids = {event.get("id") for event in feed}
            names_by_id = {lead.get("lead_id"): lead.get("name") for lead in leads}
            for lead_id, state in states.items():
                lead_name = names_by_id.get(lead_id)
                if not lead_name:
                    continue
                contact = state.get("latest_contact")
                if contact:
                    contact = {**enrich_outreach_event(dict(contact)), "follow_up_at": state.get("latest_follow_up_at")}
                    latest_results[lead_name] = contact
                    if contact.get("outcome") == "won" and state.get("latest_contact_actor"):
                        won_by_actor[state["latest_contact_actor"]] += 1
                    if contact.get("id") not in seen_event_ids:
                        feed.append(contact)
                        seen_event_ids.add(contact.get("id"))
                manual_event = state.get("latest_manual_verification")
                if manual_event:
                    manual = manual_verification_from_event(manual_event)
                    if manual:
                        latest_manual[lead_name] = manual
                    manual_event = enrich_outreach_event(dict(manual_event))
                    if manual_event.get("id") not in seen_event_ids:
                        feed.append(manual_event)
                        seen_event_ids.add(manual_event.get("id"))
            feed.sort(key=lambda event: (event.get("happened_at") or "", event.get("id") or 0), reverse=True)

            leads = [
                apply_effective_facts({**lead, "manual_verification": latest_manual.get(lead.get("name"))})
                for lead in leads
            ]
            leads = [{**lead, "ai_state": ai_state(lead)} for lead in leads]
            leads = [
                {
                    **lead,
                    "research_brief_v2": build_research_brief(lead),
                    "sales_playbook": build_sales_playbook(
                        lead,
                        sender_name=user.get("name"),
                    ),
                }
                for lead in leads
            ]
            leads = [
                {
                    **lead,
                    "workflow": build_lead_workflow(
                        lead,
                        [latest_results[lead["name"]]] if lead.get("name") in latest_results else [],
                    ),
                }
                for lead in leads
            ]
            schema = None
            if scope is None:
                try:
                    schema = schema_status()
                except Exception as exc:
                    self.log_error("schema readiness check failed: %s", exc)
                    schema = {"ready": False, "version": None, "failed_checks": ["readiness_check_failed"]}
            send_json(
                self,
                200,
                {
                    "ok": True,
                    "schema": schema,
                    "user": {
                        "email": user_email,
                        "name": user.get("name"),
                        "role": user.get("role"),
                        "title": user.get("title"),
                        "avatar_url": user.get("avatar_url"),
                    },
                    "summary": _summary(leads, assignments, events, latest_results),
                    "team_performance": build_team_performance(assignments, events, won_totals=won_by_actor),
                    "integrations": {"google_places": places_configured()},
                    "leads": leads,
                    "assignments": assignments,
                    "outreach": feed,
                    "outreach_truncated": feed_truncated,
                },
                allow_methods="GET, OPTIONS",
            )
        except Exception as exc:
            send_internal_error(self, exc, error="workspace fetch failed", allow_methods="GET, OPTIONS")
