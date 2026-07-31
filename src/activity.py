from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


ACTIVITY_PREFIX = "ZEPLIN_ACTIVITY_V1:"

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


def build_contact_result(payload: dict[str, Any]) -> dict[str, Any]:
    channel = str(payload.get("channel") or "").strip().lower()
    outcome = str(payload.get("outcome") or "").strip().lower()
    if channel not in CONTACT_CHANNELS:
        raise ValueError("channel is invalid")
    if outcome not in CONTACT_OUTCOMES:
        raise ValueError("outcome is invalid")

    follow_up_at = _parse_iso(payload.get("follow_up_at"), field="follow_up_at")
    if outcome in {"reached_later", "no_answer"} and not follow_up_at:
        raise ValueError("follow_up_at is required for this outcome")

    service_slugs = []
    for value in payload.get("service_slugs") or []:
        slug = str(value or "").strip()
        if slug and slug not in service_slugs:
            service_slugs.append(slug[:80])

    return {
        "version": 1,
        "kind": "contact_result",
        "channel": channel,
        "outcome": outcome,
        "outcome_label": OUTCOME_LABELS[outcome],
        "channel_label": CHANNEL_LABELS[channel],
        "follow_up_at": follow_up_at,
        "service_slugs": service_slugs[:10],
        "contact_name": str(payload.get("contact_name") or "").strip()[:120] or None,
        "note": str(payload.get("note") or "").strip()[:4000] or None,
    }


def encode_activity_note(activity: dict[str, Any]) -> str:
    return ACTIVITY_PREFIX + json.dumps(activity, ensure_ascii=False, separators=(",", ":"))


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


def enrich_outreach_event(event: dict[str, Any]) -> dict[str, Any]:
    row = dict(event)
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
