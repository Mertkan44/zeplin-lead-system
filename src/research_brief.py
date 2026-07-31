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
        "finding_type": finding.get("finding_type") or "gap",
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


def _is_restaurant(lead: dict[str, Any]) -> bool:
    text = f"{lead.get('category') or ''} {lead.get('sector') or ''}".lower()
    return any(value in text for value in ("restoran", "restaurant", "kafe", "cafe", "yeme", "food"))


def _manual_research(lead: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    manual = lead.get("manual_verification") or {}
    checked_at = manual.get("checked_at")
    checked_by = manual.get("checked_by")
    facts: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    checked_groups: set[str] = set()

    def add_fact(group: str, title: str, evidence: str, *, source_url: str | None = None) -> None:
        facts.append(
            {
                "code": f"manual.{group}",
                "title": title,
                "evidence": evidence,
                "confidence": 100,
                "source_url": source_url,
                "source_label": "Ekip tarafından doğrulandı",
                "checked_at": checked_at,
                "checked_by": checked_by,
            }
        )

    def add_gap(
        group: str,
        title: str,
        evidence: str,
        impact: str,
        service_slugs: list[str],
        *,
        source_url: str | None = None,
    ) -> None:
        gaps.append(
            {
                "code": f"manual.{group}",
                "title": title,
                "evidence": evidence,
                "impact": impact,
                "confidence": 100,
                "severity": "high",
                "status": "confirmed",
                "finding_type": "gap",
                "source_url": source_url,
                "source_label": "Ekip tarafından doğrulandı",
                "checked_at": checked_at,
                "checked_by": checked_by,
                "service_slugs": service_slugs,
                "talking_point": "Manuel kontrolde doğrulanan bu başlığı mevcut durumunu sorarak aç.",
                "verification": None,
            }
        )

    google = manual.get("google") or {}
    if google.get("checked"):
        status = google.get("status")
        if status == "unknown":
            status = None
        else:
            checked_groups.add("google")
        rating = google.get("rating")
        review_count = google.get("review_count")
        metric = " · ".join(
            value
            for value in (
                f"{rating}/5 puan" if rating is not None else None,
                f"{review_count} yorum" if review_count is not None else None,
            )
            if value
        )
        if status == "not_found":
            add_gap(
                "google",
                "Google işletme profili bulunamadı",
                "Ekip Google Maps üzerinde işletme profilini bulamadı.",
                "Yerel aramalarda bulunabilirliği ve güven sinyallerini zayıflatabilir.",
                ["seo_organic"],
                source_url=lead.get("maps_url"),
            )
        elif status == "found":
            add_fact(
                "google",
                "Google profili manuel kontrol edildi",
                metric or "Profil bulundu; puan ve yorum sayısı ayrıca girilmedi.",
                source_url=lead.get("maps_url"),
            )

    instagram = manual.get("instagram") or {}
    if instagram.get("checked"):
        status = instagram.get("status")
        if status != "unknown":
            checked_groups.add("instagram")
        source_url = instagram.get("url") or (lead.get("social") or {}).get("instagram_url")
        if status in {"inactive", "not_found"}:
            add_gap(
                "instagram",
                "Instagram kanalı aktif kullanılmıyor" if status == "inactive" else "Instagram hesabı bulunamadı",
                "Ekip hesabı manuel kontrol ederek bu durumu doğruladı.",
                "Düzenli görünürlük, içerik sürekliliği ve sosyal kanaldan güven oluşturmayı sınırlayabilir.",
                ["social_media", "post_design", "reels_production"],
                source_url=source_url,
            )
        elif status == "active":
            metric = " · ".join(
                value
                for value in (
                    f"{instagram.get('followers')} takipçi" if instagram.get("followers") is not None else None,
                    f"{instagram.get('post_count')} gönderi" if instagram.get("post_count") is not None else None,
                )
                if value
            )
            add_fact(
                "instagram",
                "Instagram manuel kontrol edildi",
                metric or "Hesap kontrol edildi; metrik girilmedi.",
                source_url=source_url,
            )

    menu = manual.get("menu") or {}
    if menu.get("checked"):
        status = menu.get("status")
        if status != "unknown":
            checked_groups.add("menu")
        if status in {"outdated", "not_found"} and _is_restaurant(lead):
            add_gap(
                "menu",
                "Dijital menü güncel değil" if status == "outdated" else "Dijital menü bulunamadı",
                "Ekip işletmenin herkese açık menü durumunu manuel kontrol etti.",
                "Ürünlerin güncel ve iştah açıcı biçimde sunulmasını, müşterinin karar sürecini etkileyebilir.",
                ["menu_shoot"],
                source_url=menu.get("url"),
            )
        elif status == "current":
            add_fact(
                "menu",
                "Menü manuel kontrol edildi",
                "Menü güncel görünüyor." if status == "current" else "Kontrol tamamlandı; sonuç kesinleştirilemedi.",
                source_url=menu.get("url"),
            )

    website = manual.get("website") or {}
    if website.get("checked"):
        status = website.get("status")
        if status != "unknown":
            checked_groups.add("website")
        source_url = website.get("url") or (lead.get("website") or {}).get("website_url")
        if status in {"outdated", "not_found"}:
            add_gap(
                "website",
                "Website güncel değil" if status == "outdated" else "Website bulunamadı",
                "Ekip website durumunu manuel kontrol ederek doğruladı.",
                "İşletmenin hizmetlerini anlatmasını ve dijital kanallardan güvenli iletişim toplamasını sınırlayabilir.",
                ["website_creation"],
                source_url=source_url,
            )
        elif status == "working":
            add_fact(
                "website",
                "Website manuel kontrol edildi",
                "Website çalışıyor." if status == "working" else "Kontrol tamamlandı; sonuç kesinleştirilemedi.",
                source_url=source_url,
            )
    return facts, gaps, checked_groups


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
    manual_facts, manual_gaps, checked_groups = _manual_research(lead)
    confirmed = [_finding_row(item) for item in gaps if int(item.get("confidence") or 0) >= 80]
    confirmed.extend(manual_gaps)
    likely = [_finding_row(item) for item in gaps if int(item.get("confidence") or 0) < 80]
    strengths = [_check_row(item) for item in checks if item.get("status") == "pass"]
    unknown_prefixes = {
        "google": ("maps.",),
        "instagram": ("social.",),
        "website": ("website.presence",),
    }
    suppressed_codes = tuple(
        prefix
        for group in checked_groups
        for prefix in unknown_prefixes.get(group, ())
    )
    unknowns = [
        _check_row(item)
        for item in checks
        if item.get("status") == "unknown"
        and not str(item.get("code") or "").startswith(suppressed_codes)
    ]

    source_urls = list(
        dict.fromkeys(
            str(item.get("source_url"))
            for item in [*findings, *checks, *manual_facts, *manual_gaps]
            if item.get("source_url")
        )
    )
    checked_dates = [
        parsed
        for parsed in (
            _parse_date(item.get("checked_at"))
            for item in [*findings, *checks, *manual_facts, *manual_gaps]
        )
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
    elif findings or strengths or manual_facts or manual_gaps:
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
        "manual_facts": manual_facts[:6],
        "manual_gaps": manual_gaps[:6],
        "manual_verification": lead.get("manual_verification"),
        "unknowns": unknowns[:8],
        "manual_checks": manual_checks[:8],
        "counts": {
            "confirmed": len(confirmed),
            "likely": len(likely),
            "opportunities": len(opportunities),
            "strengths": len(strengths),
            "unknown": len(unknowns),
            "manual": len(manual_facts) + len(manual_gaps),
        },
        "guardrail": (
            "Yalnızca doğrulanmış açıkları müşteriye tespit olarak söyle. "
            "Muhtemel ve bilinmeyen başlıkları soru olarak kullan."
        ),
    }
