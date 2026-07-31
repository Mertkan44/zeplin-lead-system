from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


STALE_AFTER_DAYS = 30


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source_label(url: str | None) -> str:
    if not url:
        return "Kaynak belirtilmedi"
    host = (urlparse(url).hostname or "").removeprefix("www.").lower()
    if "google." in host or "goo.gl" in host:
        return "Google Maps"
    if "instagram.com" in host:
        return "Instagram"
    return host or "Website"


def _finding_row(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": finding.get("code"),
        "title": finding.get("title"),
        "evidence": finding.get("evidence"),
        "impact": finding.get("impact"),
        "confidence": int(finding.get("confidence") or 0),
        "severity": finding.get("severity") or "info",
        "source_url": finding.get("source_url"),
        "source_label": _source_label(finding.get("source_url")),
        "checked_at": finding.get("checked_at"),
        "talking_point": finding.get("talking_point"),
        "verification": finding.get("verification"),
        "service_slugs": finding.get("service_slugs") or [],
    }


def _check_row(check: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": check.get("code"),
        "title": check.get("label"),
        "note": check.get("note"),
        "confidence": int(check.get("confidence") or 0),
        "source_url": check.get("source_url"),
        "source_label": _source_label(check.get("source_url")),
        "checked_at": check.get("checked_at"),
    }


def build_research_brief(lead: dict[str, Any]) -> dict[str, Any]:
    findings = [
        finding
        for finding in (lead.get("audit_findings") or [])
        if finding.get("status") in {"confirmed", "likely"}
    ]
    checks = lead.get("audit_checks") or []
    scoring = lead.get("scoring") or {}

    gaps = [item for item in findings if item.get("finding_type", "gap") != "opportunity"]
    opportunities = [item for item in findings if item.get("finding_type") == "opportunity"]
    confirmed = [_finding_row(item) for item in gaps if int(item.get("confidence") or 0) >= 80]
    likely = [_finding_row(item) for item in gaps if int(item.get("confidence") or 0) < 80]
    strengths = [_check_row(item) for item in checks if item.get("status") == "pass"]
    unknowns = [_check_row(item) for item in checks if item.get("status") == "unknown"]

    source_urls = list(
        dict.fromkeys(
            str(item.get("source_url"))
            for item in [*findings, *checks]
            if item.get("source_url")
        )
    )
    checked_dates = [
        parsed
        for parsed in (_parse_date(item.get("checked_at")) for item in [*findings, *checks])
        if parsed
    ]
    checked_at = max(checked_dates) if checked_dates else _parse_date(lead.get("last_analyzed"))
    age_days = (
        max(0, (datetime.now(timezone.utc) - checked_at).days)
        if checked_at
        else None
    )
    stale = age_days is None or age_days > STALE_AFTER_DAYS
    coverage = int(scoring.get("coverage") or 0)
    confidence = int(scoring.get("confidence") or 0)

    if confirmed and coverage >= 35 and confidence >= 70 and not stale:
        status = "ready"
        status_label = "Görüşmeye hazır"
    elif findings or strengths:
        status = "partial"
        status_label = "Kısmi araştırma"
    else:
        status = "discovery"
        status_label = "Önce keşif"

    manual_checks = []
    for item in unknowns[:6]:
        manual_checks.append(
            {
                **item,
                "next_step": "Kaynağı açıp manuel kontrol et; doğrulanmadan müşteriye açık gibi sunma.",
            }
        )
    for item in [*confirmed, *likely]:
        if item.get("verification"):
            manual_checks.append(
                {
                    "code": item.get("code"),
                    "title": f"{item.get('title')} için son teyit",
                    "note": item.get("verification"),
                    "source_url": item.get("source_url"),
                    "source_label": item.get("source_label"),
                    "checked_at": item.get("checked_at"),
                    "next_step": item.get("verification"),
                }
            )

    return {
        "version": 1,
        "status": status,
        "status_label": status_label,
        "checked_at": checked_at.isoformat() if checked_at else None,
        "age_days": age_days,
        "stale": stale,
        "coverage": coverage,
        "confidence": confidence,
        "source_count": len(source_urls),
        "sources": [
            {"label": _source_label(url), "url": url}
            for url in source_urls
        ],
        "confirmed_gaps": confirmed[:6],
        "likely_gaps": likely[:4],
        "opportunities": [_finding_row(item) for item in opportunities[:5]],
        "verified_strengths": strengths[:6],
        "unknowns": unknowns[:8],
        "manual_checks": manual_checks[:8],
        "counts": {
            "confirmed": len(confirmed),
            "likely": len(likely),
            "opportunities": len(opportunities),
            "strengths": len(strengths),
            "unknown": len(unknowns),
        },
        "guardrail": (
            "Yalnızca doğrulanmış açıkları müşteriye tespit olarak söyle. "
            "Muhtemel ve bilinmeyen başlıkları soru olarak kullan."
        ),
    }
