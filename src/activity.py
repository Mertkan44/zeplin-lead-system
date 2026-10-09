from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


ACTIVITY_PREFIX = "ZEPLIN_ACTIVITY_V1:"
DRAFT_PREFIX = "ZEPLIN_DRAFT_V1:"
MANUAL_PREFIX = "ZEPLIN_MANUAL_V1:"

CONTACT_CHANNELS = {"phone", "whatsapp", "instagram", "email", "other"}
CONTACT_OUTCOMES = {
    "reached_interested",
    "reached_later",
    "no_answer",
    "wrong_number",
    "not_interested",
    "proposal_requested",
    "won",
    "lost",
}

OUTCOME_LABELS = {
    "reached_interested": "İlgilendi",
    "reached_later": "Daha sonra görüşülecek",
    "no_answer": "Ulaşılamadı",
    "wrong_number": "Numara yanlış",
    "not_interested": "İlgilenmedi",
    "proposal_requested": "Teklif istedi",
    "won": "Anlaşma yapıldı",
    "lost": "Fırsat kaybedildi",
}

CHANNEL_LABELS = {
    "phone": "Telefon",
    "whatsapp": "WhatsApp",
    "instagram": "Instagram",
    "email": "E-posta",
    "other": "Diğer",
}

DRAFT_CHANNELS = {"phone", "whatsapp", "instagram", "email"}
DRAFT_STATUSES = {"approved", "needs_edit"}
MANUAL_STATUSES = {
    "google": {"found", "not_found", "unknown"},
    "instagram": {"active", "inactive", "not_found", "unknown"},
    "menu": {"current", "outdated", "not_found", "unknown"},
    "website": {"working", "outdated", "not_found", "unknown"},
}

FOLLOW_UP_DELAYS = {
    "reached_interested": 2,
    "proposal_requested": 1,
    "reached_later": 1,
    "no_answer": 1,
}


def _parse_iso(value: str | None, *, field: str) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _default_follow_up_at(outcome: str, *, now: datetime | None = None) -> str | None:
    days = FOLLOW_UP_DELAYS.get(outcome)
    if days is None:
        return None
    local_now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Europe/Istanbul"))
    follow_up = (local_now + timedelta(days=days)).replace(hour=10, minute=0, second=0, microsecond=0)
    return follow_up.astimezone(timezone.utc).isoformat()


def build_contact_result(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    channel = str(payload.get("channel") or "").strip().lower()
    outcome = str(payload.get("outcome") or "").strip().lower()
    if channel not in CONTACT_CHANNELS:
        raise ValueError("channel is invalid")
    if outcome not in CONTACT_OUTCOMES:
        raise ValueError("outcome is invalid")

    requested_follow_up_at = _parse_iso(payload.get("follow_up_at"), field="follow_up_at")
    follow_up_at = requested_follow_up_at or _default_follow_up_at(outcome, now=now)

    service_slugs = []
    for value in payload.get("service_slugs") or []:
        slug = str(value or "").strip()
        if slug and slug not in service_slugs:
            service_slugs.append(slug[:80])

    return {
        "version": 2,
        "kind": "contact_result",
        "channel": channel,
        "outcome": outcome,
        "outcome_label": OUTCOME_LABELS[outcome],
        "channel_label": CHANNEL_LABELS[channel],
        "follow_up_at": follow_up_at,
        "follow_up_automatic": bool(follow_up_at and not requested_follow_up_at),
        "service_slugs": service_slugs[:10],
        "contact_name": str(payload.get("contact_name") or "").strip()[:120] or None,
        "note": str(payload.get("note") or "").strip()[:4000] or None,
    }


def contact_request_hash(lead_name: str, payload: dict[str, Any]) -> str:
    """Fingerprint of what the user submitted, for idempotent retries.

    Built from the submitted fields, not from computed ones such as the default
    follow-up date, so a retry an hour later still matches the first attempt.
    """
    fields = {
        "lead_name": lead_name,
        "channel": str(payload.get("channel") or "").strip().lower(),
        "outcome": str(payload.get("outcome") or "").strip().lower(),
        "follow_up_at": payload.get("follow_up_at") or None,
        "service_slugs": [str(item) for item in payload.get("service_slugs") or []],
        "contact_name": str(payload.get("contact_name") or "").strip(),
        "note": str(payload.get("note") or "").strip(),
        "expected_revision": payload.get("expected_revision"),
    }
    canonical = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def encode_activity_note(activity: dict[str, Any]) -> str:
    return ACTIVITY_PREFIX + json.dumps(activity, ensure_ascii=False, separators=(",", ":"))


def build_draft_review(payload: dict[str, Any]) -> dict[str, Any]:
    channel = str(payload.get("channel") or "").strip().lower()
    status = str(payload.get("draft_status") or "approved").strip().lower()
    body = str(payload.get("body") or "").strip()
    if channel not in DRAFT_CHANNELS:
        raise ValueError("channel is invalid")
    if status not in DRAFT_STATUSES:
        raise ValueError("draft_status is invalid")
    if not body:
        raise ValueError("body is required")
    return {
        "version": 1,
        "kind": "draft_review",
        "channel": channel,
        "channel_label": CHANNEL_LABELS[channel],
        "status": status,
        "subject": str(payload.get("subject") or "").strip()[:300] or None,
        "body": body[:8000],
    }


def encode_draft_note(review: dict[str, Any]) -> str:
    return DRAFT_PREFIX + json.dumps(review, ensure_ascii=False, separators=(",", ":"))


def _optional_int(value: Any, *, field: str) -> int | None:
    if value in {None, ""}:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _manual_section(payload: dict[str, Any], name: str) -> dict[str, Any]:
    raw = payload.get(name) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be an object")
    checked = bool(raw.get("checked"))
    status = str(raw.get("status") or "unknown").strip().lower()
    if status not in MANUAL_STATUSES[name]:
        raise ValueError(f"{name}.status is invalid")
    row: dict[str, Any] = {"checked": checked, "status": status}
    if name == "google":
        rating = raw.get("rating")
        if rating not in {None, ""}:
            try:
                rating = round(float(rating), 1)
            except (TypeError, ValueError) as exc:
                raise ValueError("google.rating must be a number") from exc
            if not 0 <= rating <= 5:
                raise ValueError("google.rating must be between 0 and 5")
        else:
            rating = None
        row.update(
            {
                "rating": rating,
                "review_count": _optional_int(raw.get("review_count"), field="google.review_count"),
            }
        )
    elif name == "instagram":
        row.update(
            {
                "followers": _optional_int(raw.get("followers"), field="instagram.followers"),
                "post_count": _optional_int(raw.get("post_count"), field="instagram.post_count"),
                "url": str(raw.get("url") or "").strip()[:1000] or None,
            }
        )
    else:
        row["url"] = str(raw.get("url") or "").strip()[:1000] or None
    return row


def build_manual_verification(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("manual_verification") or payload
    if not isinstance(source, dict):
        raise ValueError("manual_verification must be an object")
    sections = {name: _manual_section(source, name) for name in MANUAL_STATUSES}
    if not any(row["checked"] for row in sections.values()):
        raise ValueError("at least one manual check is required")
    return {
        "version": 1,
        "kind": "manual_verification",
        **sections,
        "notes": str(source.get("notes") or "").strip()[:2000] or None,
    }


def encode_manual_note(verification: dict[str, Any]) -> str:
    return MANUAL_PREFIX + json.dumps(verification, ensure_ascii=False, separators=(",", ":"))


def decode_activity_note(note: Any) -> dict[str, Any] | None:
    if not isinstance(note, str) or not note.startswith(ACTIVITY_PREFIX):
        return None
    try:
        data = json.loads(note[len(ACTIVITY_PREFIX) :])
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("kind") != "contact_result":
        return None
    return data


def decode_draft_note(note: Any) -> dict[str, Any] | None:
    if not isinstance(note, str) or not note.startswith(DRAFT_PREFIX):
        return None
    try:
        data = json.loads(note[len(DRAFT_PREFIX) :])
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("kind") != "draft_review":
        return None
    return data


def decode_manual_note(note: Any) -> dict[str, Any] | None:
    if not isinstance(note, str) or not note.startswith(MANUAL_PREFIX):
        return None
    try:
        data = json.loads(note[len(MANUAL_PREFIX) :])
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("kind") != "manual_verification":
        return None
    return data


def manual_verification_from_event(event: dict[str, Any] | None) -> dict[str, Any] | None:
    """The lead's `manual_verification` from its latest manual_verification_saved
    event (lead_activity_state), with who checked it and when."""
    manual = decode_manual_note((event or {}).get("note"))
    if not manual:
        return None
    return {
        **manual,
        "checked_at": event.get("happened_at") or event.get("created_at"),
        "checked_by": event.get("actor_email"),
    }


def enrich_outreach_event(event: dict[str, Any]) -> dict[str, Any]:
    row = dict(event)
    manual = decode_manual_note(row.get("note"))
    if manual:
        checked = [name for name in MANUAL_STATUSES if (manual.get(name) or {}).get("checked")]
        row.update(
            {
                "manual_verification": manual,
                "note": f"{len(checked)} alan manuel doğrulandı",
                "activity_version": manual.get("version"),
            }
        )
        return row
    draft = decode_draft_note(row.get("note"))
    if draft:
        row.update(
            {
                "channel": draft.get("channel"),
                "channel_label": draft.get("channel_label"),
                "draft_status": draft.get("status"),
                "draft_subject": draft.get("subject"),
                "draft_body": draft.get("body"),
                "note": f"{draft.get('channel_label')} taslağı onaylandı",
                "activity_version": draft.get("version"),
            }
        )
        return row
    activity = decode_activity_note(row.get("note"))
    if not activity:
        return row
    row.update(
        {
            "channel": activity.get("channel"),
            "outcome": activity.get("outcome"),
            "outcome_label": activity.get("outcome_label"),
            "channel_label": activity.get("channel_label"),
            "follow_up_at": activity.get("follow_up_at"),
            "follow_up_automatic": bool(activity.get("follow_up_automatic")),
            "service_slugs": activity.get("service_slugs") or [],
            "contact_name": activity.get("contact_name"),
            "note": activity.get("note"),
            "activity_version": activity.get("version"),
        }
    )
    return row


def status_for_outcome(outcome: str) -> str:
    if outcome == "won":
        return "converted"
    if outcome in {"lost", "not_interested"}:
        return "lost"
    if outcome == "wrong_number":
        return "missing_info"
    if outcome in {"reached_later", "no_answer"}:
        return "follow_up"
    return "contacted"


def assignment_status_for_outcome(outcome: str) -> str:
    return "done" if outcome in {"won", "lost", "not_interested"} else "active"
