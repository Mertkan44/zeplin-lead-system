"""Lead identity signals: external provider ids and likely duplicates.

Mirrors `public.lead_google_place_id` in migration 008 so the dry-run report
and the database agree on which provider id a lead carries.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

_MAPS_PLACE_ID = re.compile(r"!19s([A-Za-z0-9_-]{10,})")
# Shared hosts that say nothing about which business a lead is.
_PLATFORM_DOMAINS = {
    "instagram.com", "facebook.com", "wa.me", "linktr.ee", "google.com",
    "business.site", "sites.google.com", "tiktok.com", "youtube.com",
}


def lead_external_id(lead: dict[str, Any]) -> str:
    """external_id the Python sync writes: a name+city hash, not a stable identity."""
    identity = (
        f"{str(lead.get('name') or '').strip().casefold()}|"
        f"{str(lead.get('city') or '').strip().casefold()}"
    )
    return f"name-city:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


def google_place_id(lead: dict[str, Any]) -> str | None:
    places = ((lead.get("research") or {}).get("google_places") or {})
    if places.get("status") == "verified" and places.get("place_id"):
        return str(places["place_id"])
    match = _MAPS_PLACE_ID.search(str(lead.get("maps_url") or ""))
    return match.group(1) if match else None


def _phone_key(value: Any) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) < 7:
        return None
    # Compare the national number so "0212..." and "+90 212..." meet.
    return digits[-10:]


def _domain_key(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    host = urlparse(raw if "://" in raw else f"https://{raw}").hostname or ""
    host = host.lower().removeprefix("www.")
    if not host or host in _PLATFORM_DOMAINS:
        return None
    return host


def _website(lead: dict[str, Any]) -> Any:
    website = lead.get("website")
    if isinstance(website, dict):
        return website.get("website_url")
    return lead.get("website_url") or website


def _label(lead: dict[str, Any]) -> dict[str, Any]:
    return {"id": lead.get("id"), "name": lead.get("name"), "city": lead.get("city")}


def find_identity_conflicts(
    leads: list[dict[str, Any]],
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Group leads that share an identity signal. Nothing here merges anything.

    `sources` are lead_sources rows (live database only); with them the report
    also lists leads whose place id is already recorded for a different lead.
    """
    by_place: dict[str, list] = defaultdict(list)
    by_phone: dict[str, list] = defaultdict(list)
    by_domain: dict[str, list] = defaultdict(list)
    without_place_id = []
    for lead in leads:
        place_id = google_place_id(lead)
        if place_id:
            by_place[place_id].append(_label(lead))
        else:
            without_place_id.append(_label(lead))
        phone = _phone_key(lead.get("phone"))
        if phone:
            by_phone[phone].append(_label(lead))
        domain = _domain_key(_website(lead))
        if domain:
            by_domain[domain].append(_label(lead))

    def shared(groups: dict[str, list]) -> list[dict[str, Any]]:
        return [
            {"key": key, "leads": items}
            for key, items in sorted(groups.items())
            if len(items) > 1
        ]

    source_owner = {
        (row.get("provider"), row.get("provider_id")): row.get("lead_id")
        for row in (sources or [])
    }
    place_owned_elsewhere = []
    place_not_recorded = []
    shared_place_ids = {key for key, items in by_place.items() if len(items) > 1}
    if sources is not None:
        for lead in leads:
            place_id = google_place_id(lead)
            if not place_id or place_id in shared_place_ids:
                continue
            owner = source_owner.get(("google_places", place_id))
            if owner is None:
                place_not_recorded.append({**_label(lead), "place_id": place_id})
            elif owner != lead.get("id"):
                place_owned_elsewhere.append({**_label(lead), "place_id": place_id, "recorded_for": owner})
    external_id_mismatch = [
        _label(lead) for lead in leads
        if lead.get("external_id") and lead.get("external_id") != lead_external_id(lead)
    ]

    return {
        "lead_count": len(leads),
        "place_owned_elsewhere": place_owned_elsewhere,
        "place_not_recorded": place_not_recorded,
        "external_id_mismatch": external_id_mismatch,
        "without_place_id": without_place_id,
        "shared_place_id": shared(by_place),
        "shared_phone": shared(by_phone),
        "shared_website": shared(by_domain),
    }
