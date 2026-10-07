from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo


_FOOD_TERMS = {
    "restaurant",
    "restoran",
    "cafe",
    "kafe",
    "lokanta",
    "meyhane",
    "pastane",
    "bakery",
    "bar",
    "breakfast",
    "kahvaltı",
    "kahvalti",
}

BUSINESS_TIMEZONE = ZoneInfo("Europe/Istanbul")

_CHECK_LABELS = {
    "google": "Google Maps",
    "instagram": "Instagram",
    "menu": "Menü",
    "website": "Website",
}


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _business_date(value: Any) -> date | None:
    parsed = _parse_datetime(value)
    return parsed.astimezone(BUSINESS_TIMEZONE).date() if parsed else None


def requires_menu_check(lead: dict[str, Any]) -> bool:
    identity = " ".join(
        str(lead.get(field) or "").casefold()
        for field in ("sector", "category", "name")
    )
    return any(re.search(rf"\b{re.escape(term)}\b", identity) for term in _FOOD_TERMS)


def required_manual_checks(lead: dict[str, Any]) -> list[str]:
    checks = ["google", "instagram", "website"]
    if requires_menu_check(lead):
        checks.insert(2, "menu")
    return checks


def _has_contact_channel(lead: dict[str, Any]) -> bool:
    research_emails = (((lead.get("research") or {}).get("website") or {}).get("emails") or [])
    manual_instagram = ((lead.get("manual_verification") or {}).get("instagram") or {})
    return bool(
        lead.get("phone")
        or lead.get("email")
        or research_emails
        or (lead.get("social") or {}).get("instagram_url")
        or manual_instagram.get("url")
    )


def build_lead_workflow(
    lead: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    events = events or []
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    manual = lead.get("manual_verification") or {}
    places = ((lead.get("research") or {}).get("google_places") or {})
    places_refreshed_at = _parse_datetime(places.get("refreshed_at"))
    places_verified = bool(
        places.get("status") == "verified"
        and places_refreshed_at
        and places_refreshed_at >= now - timedelta(days=30)
    )
    required = required_manual_checks(lead)
    checks = []
    for key in required:
        value = manual.get(key) or {}
        checked = bool(value.get("checked")) or (key == "google" and places_verified)
        status = str(value.get("status") or "unknown")
        if key == "google" and places_verified:
            status = "found"
        complete = checked and status != "unknown"
        checks.append(
            {
                "key": key,
                "label": _CHECK_LABELS[key],
                "complete": complete,
                "checked": checked,
                "status": status,
                "source": "google_places" if key == "google" and places_verified else "manual",
            }
        )

    lead_events = [event for event in events if event.get("lead_name") == lead.get("name")]
    contact_results = [event for event in lead_events if event.get("action") == "contact_result_recorded"]
    latest_contact = contact_results[0] if contact_results else None
    follow_up_at = _parse_datetime((latest_contact or {}).get("follow_up_at"))
    status = lead.get("status") or "yeni"
    checks_complete = all(item["complete"] for item in checks)
    contact_available = _has_contact_channel(lead)
    ready = checks_complete and contact_available

    if status in {"converted", "lost"}:
        stage = "closed"
        stage_label = "Kapatıldı"
    elif follow_up_at and follow_up_at <= now:
        stage = "follow_up_due"
        stage_label = "Takip zamanı geldi"
    elif latest_contact:
        stage = "contacted"
        stage_label = "Temas kaydedildi"
    elif ready:
        stage = "ready_to_contact"
        stage_label = "Aramaya hazır"
    else:
        stage = "verification_required"
        stage_label = "Kontrol bekliyor"

    completed_count = sum(1 for item in checks if item["complete"])
    missing = [item["label"] for item in checks if not item["complete"]]
    if not contact_available:
        missing.append("İletişim kanalı")
    return {
        "stage": stage,
        "stage_label": stage_label,
        "ready_to_contact": ready,
        "checks_complete": checks_complete,
        "contact_available": contact_available,
        "checks": checks,
        "completed_count": completed_count,
        "required_count": len(checks),
        "missing": missing,
        "latest_contact_at": (
            (latest_contact or {}).get("happened_at") or (latest_contact or {}).get("created_at")
        ),
        "latest_outcome": (latest_contact or {}).get("outcome"),
        "latest_outcome_label": (latest_contact or {}).get("outcome_label"),
        "follow_up_at": follow_up_at.isoformat() if follow_up_at else None,
        "follow_up_due": stage != "closed" and bool(follow_up_at and follow_up_at <= now),
    }


def build_team_performance(
    assignments: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = now.astimezone(BUSINESS_TIMEZONE).date()
    emails = {
        str(item.get("user_email") or "").strip().lower()
        for item in assignments
        if item.get("user_email")
    }
    emails.update(
        str(event.get("actor_email") or "").strip().lower()
        for event in events
        if event.get("actor_email")
    )
    rows = []
    for email in sorted(emails):
        actor_events = [
            event for event in events
            if str(event.get("actor_email") or "").strip().lower() == email
        ]
        today_events = [
            event for event in actor_events
            if _business_date(event.get("happened_at") or event.get("created_at")) == today
        ]
        active_assignments = [
            item for item in assignments
            if str(item.get("user_email") or "").strip().lower() == email
            and item.get("status") == "active"
        ]
        contact_events = [
            event for event in today_events if event.get("action") == "contact_result_recorded"
        ]
        overdue_assignments = [
            item for item in active_assignments
            if (_parse_datetime(item.get("due_at")) or datetime.max.replace(tzinfo=timezone.utc)) <= now
        ]
        rows.append(
            {
                "email": email,
                "active_assignments": len(active_assignments),
                "checks_today": sum(1 for event in today_events if event.get("action") == "manual_verification_saved"),
                "contacts_today": len(contact_events),
                "calls_today": sum(
                    1 for event in today_events
                    if event.get("action") == "contact_result_recorded" and event.get("channel") == "phone"
                ),
                "won_total": sum(
                    1 for event in actor_events
                    if event.get("action") == "contact_result_recorded" and event.get("outcome") == "won"
                ),
                "interested_today": sum(
                    1 for event in contact_events
                    if event.get("outcome") in {"reached_interested", "proposal_requested"}
                ),
                "no_answer_today": sum(
                    1 for event in contact_events if event.get("outcome") == "no_answer"
                ),
                "follow_ups_created_today": sum(
                    1 for event in contact_events if event.get("follow_up_at")
                ),
                "overdue_follow_ups": len(overdue_assignments),
            }
        )
    return rows
