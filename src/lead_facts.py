"""Effective lead facts: one value per field, shared by every reader.

A lead's contact and profile fields can come from three places: the scrape
(stored on the lead), verified Google Places data (research.google_places) and
the team's latest manual check (an outreach event, attached as
`manual_verification` with `checked_at` / `checked_by`). `apply_effective_facts`
resolves them once, so the dashboard, the workflow stage, service matching and
AI all see the same values:

- per field, the first fresh source in precedence order wins; manual checks
  come first, so a later scrape or Places refresh never silently replaces a
  person's correction;
- Google rating and review count are the same Google figure read twice, so the
  newer of the manual and Places readings wins;
- every fact carries value, status (present/absent), source, observed_at,
  verified_by, stale and the differing values of other sources (conflicts);
- audit findings about a website or Instagram profile that is no longer the
  effective one stop counting as evidence, and a manual "not found" becomes a
  finding of its own; services are re-matched only when this changes anything.

Stale limits are owner policy (report question 5); Places keeps its 30 days.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from src.audit.findings import manual_absence_findings
from src.lead_identity import domain_key, phone_key
from src.services import discovery_services, estimate_value, match_services, recommended_package

STALE_AFTER_DAYS = {"manual": 90, "google_places": 30, "scrape": 90}

# Findings a person's "it exists" check contradicts.
_WEBSITE_ABSENCE_CODES = {"website.absent", "website.invalid_candidate"}
_INSTAGRAM_ABSENCE_CODES = {"social.instagram_absent"}


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_stale(source: str, observed_at: Any, now: datetime) -> bool:
    """Older than the source's limit. An unknown time is stale, except for a
    manual check, whose time is always recorded by the event that carries it."""
    observed = _parse(observed_at)
    if observed is None:
        return source != "manual"
    return observed < now - timedelta(days=STALE_AFTER_DAYS[source])


def _instagram_key(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.strip("/").split("/")[0].lower() if parsed.path else ""
    return f"{host}/{path}" if path else host or None


def _address_key(value: Any) -> str | None:
    words = [word for word in str(value or "").casefold().replace(",", " ").split() if word not in {"türkiye", "turkey"}]
    return " ".join(words) or None


def _number_key(value: Any) -> str | None:
    return None if value is None else str(value)


_KEYS = {
    "website_url": domain_key,
    "instagram_url": _instagram_key,
    "phone": phone_key,
    "rating": _number_key,
    "review_count": _number_key,
    # Places and scraped Maps links never look alike; they are not compared.
    "maps_url": lambda value: "maps",
    "address": _address_key,
    "menu_url": lambda value: str(value).strip() or None if value else None,
}


def _observation(source, value, observed_at, *, verified_by=None, absent=False):
    return {
        "source": source,
        "value": None if absent else value,
        "status": "absent" if absent else "present",
        "observed_at": observed_at,
        "verified_by": verified_by,
    }


def _resolve(field: str, observations: list[Any], now: datetime) -> dict | None:
    """First fresh observation in the given order wins; if all are stale, the first."""
    observations = [item for item in observations if item]
    if not observations:
        return None
    for item in observations:
        item["stale"] = is_stale(item["source"], item["observed_at"], now)
    fresh = [item for item in observations if not item["stale"]]
    chosen = (fresh or observations)[0]
    key = _KEYS[field]
    chosen_key = key(chosen["value"]) if chosen["status"] == "present" else None
    conflicts = [
        {"source": item["source"], "value": item["value"], "status": item["status"], "observed_at": item["observed_at"]}
        for item in observations
        if item is not chosen and (
            item["status"] != chosen["status"]
            or (item["status"] == "present" and key(item["value"]) != chosen_key)
        )
    ]
    return {**chosen, "conflicts": conflicts}


def _manual_section(manual: dict[str, Any], name: str) -> dict[str, Any] | None:
    section = manual.get(name) or {}
    if not section.get("checked") or section.get("status") in {None, "unknown"}:
        return None
    return section


def build_lead_facts(lead: dict[str, Any], *, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    manual = lead.get("manual_verification") or {}
    manual_at, manual_by = manual.get("checked_at"), manual.get("checked_by")
    places = ((lead.get("research") or {}).get("google_places") or {})
    places = places if places.get("status") == "verified" else {}
    places_at = places.get("refreshed_at")
    website = lead.get("website") if isinstance(lead.get("website"), dict) else {}
    social = lead.get("social") or {}
    scraped_at = lead.get("last_analyzed")

    facts: dict[str, dict[str, Any]] = {}

    def add(field, observations):
        fact = _resolve(field, observations, now)
        if fact:
            facts[field] = fact

    manual_website = _manual_section(manual, "website")
    scraped_website = website.get("website_url") if website.get("has_website") is not False else None
    add("website_url", [
        manual_website and _observation(
            "manual", manual_website.get("url") or scraped_website, manual_at, verified_by=manual_by,
            absent=manual_website.get("status") == "not_found" or not (manual_website.get("url") or scraped_website),
        ),
        places.get("website_url") and _observation("google_places", places["website_url"], places_at),
        (scraped_website or website.get("has_website") is False) and _observation(
            "scrape", scraped_website, website.get("checked_at") or scraped_at, absent=not scraped_website,
        ),
    ])

    manual_instagram = _manual_section(manual, "instagram")
    scraped_instagram = social.get("instagram_url")
    add("instagram_url", [
        manual_instagram and _observation(
            "manual", manual_instagram.get("url") or scraped_instagram, manual_at, verified_by=manual_by,
            absent=manual_instagram.get("status") == "not_found" or not (manual_instagram.get("url") or scraped_instagram),
        ),
        (scraped_instagram or social.get("lookup_status") == "not_found") and _observation(
            "scrape", scraped_instagram, social.get("checked_at") or scraped_at, absent=not scraped_instagram,
        ),
    ])

    add("phone", [
        places.get("phone") and _observation("google_places", places["phone"], places_at),
        lead.get("phone") and _observation("scrape", lead["phone"], scraped_at),
    ])

    manual_google = _manual_section(manual, "google") or {}
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    for field in ("rating", "review_count"):
        google_readings = sorted(
            [
                item for item in (
                    manual_google.get(field) is not None and _observation(
                        "manual", manual_google[field], manual_at, verified_by=manual_by,
                    ),
                    places.get(field) is not None and _observation("google_places", places[field], places_at),
                ) if item
            ],
            key=lambda item: _parse(item["observed_at"]) or oldest,
            reverse=True,
        )
        add(field, [
            *google_readings,
            lead.get(field) is not None and _observation("scrape", lead[field], scraped_at),
        ])

    add("maps_url", [
        places.get("maps_url") and _observation("google_places", places["maps_url"], places_at),
        lead.get("maps_url") and _observation("scrape", lead["maps_url"], scraped_at),
    ])
    add("address", [
        places.get("formatted_address") and _observation("google_places", places["formatted_address"], places_at),
        lead.get("address") and _observation("scrape", lead["address"], scraped_at),
    ])
    manual_menu = _manual_section(manual, "menu")
    if manual_menu:
        add("menu_url", [_observation(
            "manual", manual_menu.get("url"), manual_at, verified_by=manual_by,
            absent=manual_menu.get("status") == "not_found" or not manual_menu.get("url"),
        )])
    return facts


def _source_matches(finding: dict[str, Any], key_fn, old_key: str | None) -> bool:
    return bool(old_key) and key_fn(finding.get("source_url")) == old_key


def effective_findings(lead: dict[str, Any], facts: dict[str, dict[str, Any]]) -> tuple[list[dict], list[str]] | None:
    """(findings, superseded codes) when facts change the audit evidence, else None."""
    audit = lead.get("audit") or {}
    # Legacy leads (no findings-based audit) keep their trigger-based matching.
    if not (int(audit.get("version") or 0) >= 3 or "audit_findings" in lead):
        return None
    findings = audit.get("findings") or lead.get("audit_findings") or []
    if not findings and not lead.get("manual_verification"):
        return None
    website = lead.get("website") if isinstance(lead.get("website"), dict) else {}
    audited_site = domain_key(website.get("final_url") or website.get("website_url"))
    audited_instagram = _instagram_key((lead.get("social") or {}).get("instagram_url"))
    site_fact = facts.get("website_url") or {}
    instagram_fact = facts.get("instagram_url") or {}

    site_replaced = site_fact.get("source") == "manual" and (
        site_fact.get("status") == "absent" or domain_key(site_fact.get("value")) != audited_site
    )
    instagram_replaced = instagram_fact.get("source") == "manual" and (
        instagram_fact.get("status") == "absent" or _instagram_key(instagram_fact.get("value")) != audited_instagram
    )
    site_present = site_fact.get("source") == "manual" and site_fact.get("status") == "present"
    instagram_present = instagram_fact.get("source") == "manual" and instagram_fact.get("status") == "present"

    kept, superseded = [], []
    for finding in findings:
        code = finding.get("code")
        if (
            (site_present and code in _WEBSITE_ABSENCE_CODES)
            or (instagram_present and code in _INSTAGRAM_ABSENCE_CODES)
            or (site_replaced and _source_matches(finding, domain_key, audited_site))
            or (instagram_replaced and _source_matches(finding, _instagram_key, audited_instagram))
        ):
            superseded.append(code)
            continue
        kept.append(finding)
    manual = [
        finding for finding in manual_absence_findings(lead.get("manual_verification"))
        if (finding["code"] == "website.absent" and site_fact.get("source") == "manual")
        or (finding["code"] == "social.instagram_absent" and instagram_fact.get("source") == "manual")
    ]
    kept_codes = {finding.get("code") for finding in kept}
    added = [finding for finding in manual if finding["code"] not in kept_codes]
    if not superseded and not added:
        return None
    return kept + added, superseded


def apply_effective_facts(lead: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """A copy of the lead with effective values on the usual fields, `facts`
    describing each, and services re-matched if the evidence changed.

    For reading only: never write the result back as the stored lead.
    """
    facts = build_lead_facts(lead, now=now)
    row = dict(lead)
    row["facts"] = facts

    def value(field):
        fact = facts.get(field)
        return (fact["value"], fact["status"]) if fact else (None, None)

    website = dict(lead.get("website") or {}) if isinstance(lead.get("website"), dict) else {}
    site, site_status = value("website_url")
    if site_status:
        website["website_url"] = site
        website["has_website"] = site_status == "present"
        row["website"] = website
    social = dict(lead.get("social") or {})
    instagram, instagram_status = value("instagram_url")
    if instagram_status and (facts["instagram_url"]["source"] == "manual" or instagram_status == "present"):
        social["instagram_url"] = instagram
        if facts["instagram_url"]["source"] == "manual":
            social["has_instagram"] = instagram_status == "present"
        row["social"] = social
    for field in ("phone", "rating", "review_count", "maps_url", "address"):
        field_value, status = value(field)
        if status == "present":
            row[field] = field_value

    changed = effective_findings(lead, facts)
    if changed:
        findings, superseded = changed
        row["audit"] = {**(lead.get("audit") or {}), "findings": findings, "superseded_codes": superseded}
        if "audit_findings" in lead:
            row["audit_findings"] = findings
        row["matched_services"] = match_services(row)
        row["discovery_services"] = discovery_services(row)
        row["recommended_package"] = recommended_package(row)
        row["estimated_value_tl"] = estimate_value(row)
    return row
