from http.server import BaseHTTPRequestHandler
import sys
from datetime import datetime
from collections import Counter
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import normalize_email, require_auth
from src.activity import enrich_outreach_event
from src.http_api import send_internal_error, send_json, send_options
from src.sales_assistant import build_sales_playbook
from src.research_brief import build_research_brief
from src.workflow import build_lead_workflow, build_team_performance
from src.integrations.google_places import is_configured as places_configured
from src.storage.supabase import (
    attach_assignments_to_leads,
    fetch_lead_assignments,
    fetch_leads_full,
    fetch_outreach_events,
    is_enabled as supabase_enabled,
)


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


def _summary(leads: list[dict], assignments: list[dict], events: list[dict]) -> dict:
    active_assignments = [item for item in assignments if item.get("status") == "active"]
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    due_follow_ups = []
    latest_results: dict[str, dict] = {}
    for event in events:
        if event.get("action") != "contact_result_recorded":
            continue
        lead_name = event.get("lead_name") or ""
        if lead_name and lead_name not in latest_results:
            latest_results[lead_name] = event
    for event in latest_results.values():
        if any(lead.get("name") == event.get("lead_name") and lead.get("status") in {"converted", "lost"} for lead in leads):
            continue
        follow_up_at = event.get("follow_up_at")
        if not follow_up_at:
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
        try:
            user_email = normalize_email(user.get("sub"))
            leads = fetch_leads_full(limit=None)
            assignments = fetch_lead_assignments(
                user_email=None if user.get("role") == "admin" else user_email,
                status=None if user.get("role") == "admin" else "active",
                limit=None,
            )
            if user.get("role") != "admin":
                assigned_names = {item.get("lead_name") for item in assignments}
                leads = [lead for lead in leads if lead.get("name") in assigned_names]
            leads = attach_assignments_to_leads(leads, assignments)
            events = [
                enrich_outreach_event(event)
                for event in fetch_outreach_events(limit=None)
            ]
            if user.get("role") != "admin":
                assigned_names = {lead.get("name") for lead in leads}
                events = [event for event in events if event.get("lead_name") in assigned_names]
            latest_manual: dict[str, dict] = {}
            for event in events:
                lead_name = event.get("lead_name")
                if (
                    lead_name
                    and lead_name not in latest_manual
                    and event.get("action") == "manual_verification_saved"
                    and event.get("manual_verification")
                ):
                    latest_manual[lead_name] = {
                        **event["manual_verification"],
                        "checked_at": event.get("happened_at") or event.get("created_at"),
                        "checked_by": event.get("actor_email"),
                    }
            leads = [
                {**lead, "manual_verification": latest_manual.get(lead.get("name"))}
                for lead in leads
            ]
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
                {**lead, "workflow": build_lead_workflow(lead, events)}
                for lead in leads
            ]
            send_json(
                self,
                200,
                {
                    "ok": True,
                    "user": {
                        "email": user_email,
                        "name": user.get("name"),
                        "role": user.get("role"),
                        "title": user.get("title"),
                        "avatar_url": user.get("avatar_url"),
                    },
                    "summary": _summary(leads, assignments, events),
                    "team_performance": build_team_performance(assignments, events),
                    "integrations": {"google_places": places_configured()},
                    "leads": leads,
                    "assignments": assignments,
                    "outreach": events,
                },
                allow_methods="GET, OPTIONS",
            )
        except Exception as exc:
            send_internal_error(self, exc, error="workspace fetch failed", allow_methods="GET, OPTIONS")
