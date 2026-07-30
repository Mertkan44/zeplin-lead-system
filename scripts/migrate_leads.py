import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.dashboard.build import build_dashboard
from src.ai.generator import AI_PROMPT_VERSION, has_email_evidence
from src.audit.findings import analyze_lead
from src.services import discovery_services, estimate_value, match_services, recommended_package


WEBSITE_DEFAULTS = {
    "has_website": False,
    "website_url": None,
    "final_url": None,
    "audit_version": None,
    "audit_status": None,
    "lookup_status": "unknown",
    "checked_at": None,
    "has_ssl": None,
    "is_mobile_friendly": None,
    "load_time_ms": None,
    "website_loads": None,
    "has_schema": None,
    "has_og": None,
    "meta_description": None,
    "has_robots": None,
    "has_sitemap": None,
    "has_email_capture": None,
    "has_whatsapp": None,
    "has_analytics": None,
    "has_contact_form": None,
    "has_phone_link": None,
    "has_reservation_signal": None,
    "has_order_signal": None,
    "is_indexable": None,
    "has_canonical": None,
    "has_local_business_schema": None,
    "schema_status": "not_checked",
    "schema_types": [],
    "schema_names": [],
    "schema_fields": [],
    "schema_block_count": 0,
    "schema_invalid_count": 0,
    "og_fields": [],
    "og_missing_fields": [],
    "response_time_samples_ms": [],
    "performance_status": "not_checked",
    "internal_links_checked": 0,
    "broken_internal_links": [],
    "instagram_links": [],
    "facebook_links": [],
    "tiktok_url": None,
    "phone_numbers": [],
    "emails": [],
    "contact_page_urls": [],
    "menu_page_urls": [],
    "booking_urls": [],
    "robots_blocks_site": None,
    "placeholder_detected": None,
    "placeholder_reason": None,
    "word_count": None,
    "h1_count": None,
    "h1_texts": [],
    "title": None,
    "title_length": None,
    "meta_description_length": None,
    "canonical_url": None,
    "image_count": None,
    "images_with_alt": None,
    "image_alt_coverage": None,
    "form_control_count": None,
    "labeled_form_control_count": None,
    "form_label_coverage": None,
}

SOCIAL_DEFAULTS = {
    "has_instagram": False,
    "instagram_url": None,
    "instagram_username": None,
    "lookup_status": "unknown",
    "identity_confidence": 0,
    "identity_evidence": None,
    "checked_at": None,
    "has_facebook": False,
    "facebook_url": None,
    "stats": {
        "followers": None,
        "following": None,
        "post_count": None,
        "avg_likes": None,
        "avg_comments": None,
        "engagement_rate": None,
        "lookup_status": "not_checked",
        "engagement_sample_size": 0,
        "checked_at": None,
    },
    "tiktok": {"has_tiktok": None, "tiktok_url": None, "tiktok_username": None},
}

MAPS_DEFAULTS = {
    "source_status": "unknown",
    "checked_at": None,
    "identity_name": None,
    "identity_confidence": 0,
    "website_lookup_status": "unknown",
    "phone_lookup_status": "unknown",
    "address_lookup_status": "unknown",
    "rating_lookup_status": "unknown",
    "review_count_lookup_status": "unknown",
}

DELIVERY_DEFAULTS = {
    "has_yemeksepeti": None,
    "yemeksepeti_url": None,
    "has_getir": None,
    "getir_url": None,
}


def deep_merge(defaults: dict, current: dict | None) -> dict:
    result = deepcopy(defaults)
    current = current or {}
    for key, value in current.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def infer_sector(lead: dict) -> str:
    if lead.get("sector") and lead.get("sector") != "default":
        return lead["sector"]
    text = " ".join(str(lead.get(k) or "") for k in ("query", "category", "name")).lower()
    if any(token in text for token in ("restoran", "restaurant", "cafe", "kafe", "teras", "lokanta")):
        return "restaurant"
    if any(token in text for token in ("diş", "dental", "klinik", "clinic", "sağlık", "doktor", "estetik")):
        return "health"
    if any(token in text for token in ("kuaför", "güzellik", "salon", "berber", "hair", "beauty")):
        return "salon"
    if any(token in text for token in ("mağaza", "butik", "store", "shop", "perakende")):
        return "retail"
    if any(token in text for token in ("oto", "otomotiv", "galeri", "servis", "automotive")):
        return "auto"
    return "default"


def normalize_score(scoring: dict) -> dict:
    score = int(scoring.get("score") or 0)
    grade = scoring.get("grade")
    if not grade:
        grade = "A" if score >= 80 else "B" if score >= 55 else "C" if score >= 35 else "D"
    return {
        "score": score,
        "max_score": int(scoring.get("max_score") or 100),
        "grade": grade,
        "issues": list(scoring.get("issues") or []),
        "opportunities": list(scoring.get("opportunities") or []),
    }


def fallback_report(lead: dict) -> str:
    findings = [
        finding
        for finding in (lead.get("audit_findings") or [])
        if finding.get("status") in {"confirmed", "likely"}
    ][:3]
    if not findings:
        return (
            "NE TESPİT ETTİK?\n"
            "- Satış görüşmesinde kullanılabilecek yeterli güvene sahip açık henüz doğrulanmadı.\n\n"
            "GÖRÜŞMEDE SOR\n"
            "- İşletmenin şu anda en çok geliştirmek istediği dijital kanal hangisi?\n\n"
            "DOĞRULANMAYANLAR\n"
            "- Derin denetim ve kaynak kontrolü tamamlanmalı."
        )
    lines = "\n".join(
        f"- {item['title']}: {item.get('evidence') or 'Kanıt kaydı mevcut.'}"
        for item in findings
    )
    services = ", ".join(
        item.get("name")
        for item in (lead.get("matched_services") or [])[:2]
        if item.get("name")
    ) or "Hizmet eşleşmesi görüşmede doğrulanmalı"
    return (
        f"NE TESPİT ETTİK?\n{lines}\n\n"
        f"BİZ NE SUNABİLİRİZ?\n- {services}\n\n"
        "GÖRÜŞMEDE SOR\n- Bu açık mevcut müşteri akışınızda size nasıl yansıyor?"
    )


def fallback_email(lead: dict) -> str:
    verified = [
        finding
        for finding in (lead.get("audit_findings") or [])
        if finding.get("status") == "confirmed"
        and int(finding.get("confidence") or 0) >= 80
    ]
    if not verified:
        return "TASLAK İÇİN YETERLİ KANIT YOK"
    first_issue = verified[0]
    return (
        f"Konu: {lead['name']} için kısa bir dijital sağlık notu\n\n"
        "Merhaba,\n\n"
        f"{lead['name']} için yaptığımız kontrolde \"{first_issue['title']}\" başlığını not ettik. "
        f"{first_issue.get('impact') or 'Bu durum müşteri deneyimini etkileyebilir.'}\n\n"
        "Zeplin Media olarak bu başlık için uygulanabilir bir çözüm planı çıkarabiliriz. "
        "Bu hafta 15 dakikalık bir görüşme uygun olur mu?\n\n"
        "Zeplin Media satış ekibi"
    )


def priority_model(lead: dict) -> tuple[int, str, str]:
    score = lead["scoring"]["score"]
    score_status = lead["scoring"].get("score_status") or "insufficient"
    coverage = int(lead["scoring"].get("coverage") or 0)
    value = lead.get("estimated_value_tl") or 0
    findings = lead.get("audit_findings") or []
    issues = [item for item in findings if item.get("status") in {"confirmed", "likely"}]
    has_contact = bool((lead.get("data_quality") or {}).get("has_contact"))
    has_report = bool(lead.get("ai_report"))
    has_email = bool(lead.get("ai_email"))
    has_services = bool(lead.get("matched_services"))
    audit_depth = lead.get("data_quality", {}).get("has_audit_depth", False)

    priority = 0
    if score_status != "insufficient":
        if score < 40:
            priority += 28
        elif score < 60:
            priority += 22
        elif score < 80:
            priority += 14
        else:
            priority += 6
    else:
        priority += min(10, coverage // 5)
    priority += min(28, value // 2500)
    priority += min(20, sum(
        {"critical": 8, "high": 5, "medium": 3, "low": 1}.get(item.get("severity"), 1)
        for item in issues
    ))
    if has_contact:
        priority += 14
    if has_report:
        priority += 10
    if has_services:
        priority += 8
    if audit_depth:
        priority += 8

    if not has_contact:
        action = "İletişim kanalını doğrula"
        reason = "Telefon, e-posta veya doğrulanmış sosyal iletişim kanalı henüz hazır değil."
    elif not has_services:
        action = "Derin audit yap"
        reason = f"Kanıtlı hizmet eşleşmesi yok; denetim kapsamı %{coverage} ve kaynaklar genişletilmeli."
    elif score_status == "insufficient":
        action = "Derin audit yap"
        reason = f"Denetim kapsamı %{coverage}; satış iddiasından önce daha fazla kaynak kontrol edilmeli."
    elif not has_report:
        action = "İhtiyaç raporu üret"
        reason = (
            "Kanıtlı bulgular var; çalışan için görüşme özeti"
            + (" ve kontrollü mail taslağı" if has_email_evidence(lead) else "")
            + " hazırlanmalı."
        )
    elif not has_email:
        action = "Kanıtlı bulguları telefonla görüş"
        reason = "İhtiyaç özeti hazır; otomatik mail için yeterli güçlü kanıt yok."
    elif any(item.get("severity") in {"critical", "high"} for item in issues):
        action = "Öncelikli arama yap"
        reason = "Yüksek etkili ve kaynak gösterilebilir bir açık doğrulandı."
    else:
        action = "Görüşme taslağını gözden geçir"
        reason = "Kanıt, hizmet yönü ve çalışan onaylı temas içeriği hazır."

    return min(100, int(priority)), action, reason


def normalize_lead(lead: dict) -> dict:
    normalized = deepcopy(lead)
    normalized["name"] = normalized.get("name") or "İsimsiz Lead"
    normalized["city"] = normalized.get("city") or ""
    normalized["query"] = normalized.get("query") or ""
    normalized["maps_url"] = normalized.get("maps_url") or ""
    normalized["sector"] = infer_sector(normalized)
    normalized["phone"] = normalized.get("phone")
    normalized["address"] = normalized.get("address")
    normalized["rating"] = normalized.get("rating")
    normalized["review_count"] = normalized.get("review_count")
    normalized["category"] = normalized.get("category")
    normalized["status"] = normalized.get("status") or "yeni"
    normalized["website"] = deep_merge(WEBSITE_DEFAULTS, normalized.get("website"))
    normalized["social"] = deep_merge(SOCIAL_DEFAULTS, normalized.get("social"))
    normalized["delivery"] = deep_merge(DELIVERY_DEFAULTS, normalized.get("delivery"))
    existing_maps = normalized.get("maps") or {}
    normalized["maps"] = deep_merge(MAPS_DEFAULTS, existing_maps)
    if not existing_maps:
        normalized["maps"]["source_status"] = "legacy_unverified"
        normalized["maps"]["website_lookup_status"] = (
            "found" if normalized["website"].get("website_url") else "unknown"
        )
        normalized["maps"]["phone_lookup_status"] = (
            "found" if normalized.get("phone") else "unknown"
        )
        normalized["maps"]["address_lookup_status"] = (
            "found" if normalized.get("address") else "unknown"
        )
        normalized["maps"]["rating_lookup_status"] = (
            "found" if normalized.get("rating") is not None else "unknown"
        )
        normalized["maps"]["review_count_lookup_status"] = "legacy_unverified"
    if normalized["website"].get("lookup_status") == "unknown":
        normalized["website"]["lookup_status"] = normalized["maps"].get("website_lookup_status") or "unknown"
    if normalized["social"].get("lookup_status") == "unknown" and (
        normalized["social"].get("has_instagram") is not None
    ):
        normalized["social"]["lookup_status"] = "legacy_unverified"
    website_instagram_links = normalized["website"].get("instagram_links") or []
    instagram_url = normalized["social"].get("instagram_url")
    if (
        instagram_url
        and normalized["social"].get("lookup_status") == "found"
        and int(normalized["social"].get("identity_confidence") or 0) >= 70
        and any(
        instagram_url.rstrip("/").casefold() == link.rstrip("/").casefold()
        for link in website_instagram_links
        )
    ):
        normalized["social"]["lookup_status"] = "found"
        normalized["social"]["identity_confidence"] = 98
        normalized["social"]["identity_evidence"] = normalized["social"].get(
            "identity_evidence"
        ) or "Instagram linki işletmenin websitesinde ve marka kimliğiyle doğrulandı."

    audit = analyze_lead(normalized)
    normalized["audit"] = audit
    normalized["audit_findings"] = audit["findings"]
    normalized["audit_checks"] = audit["checks"]
    normalized["scoring"] = audit["scoring"]
    normalized["matched_services"] = match_services(normalized)
    normalized["discovery_services"] = discovery_services(normalized)
    normalized["recommended_package"] = recommended_package(normalized)
    normalized["estimated_value_tl"] = estimate_value(normalized)
    if normalized.get("ai_prompt_version") != AI_PROMPT_VERSION:
        normalized["research_brief"] = None
        normalized["ai_report"] = None
        normalized["ai_email"] = None
    normalized["ai_prompt_version"] = (
        AI_PROMPT_VERSION
        if normalized.get("ai_report")
        and (normalized.get("ai_email") or not has_email_evidence(normalized))
        else None
    )
    normalized["last_analyzed"] = normalized.get("last_analyzed") or datetime.now().strftime("%Y-%m-%d %H:%M")
    normalized["schema_version"] = 3
    audit_summary = audit["summary"]
    research_emails = (
        ((normalized.get("research") or {}).get("website") or {}).get("emails")
        or []
    )
    verified_social = (
        normalized["social"].get("has_instagram") is True
        and int(normalized["social"].get("identity_confidence") or 0) >= 70
    )
    has_contact = bool(normalized.get("phone") or research_emails or verified_social)
    has_audit_depth = int(audit_summary.get("coverage") or 0) >= 60
    normalized["data_quality"] = {
        "has_contact": has_contact,
        "contact_channels": [
            channel
            for channel, available in {
                "phone": bool(normalized.get("phone")),
                "email": bool(research_emails),
                "instagram": verified_social,
            }.items()
            if available
        ],
        "has_maps_rating": (
            normalized.get("rating") is not None
            and normalized["maps"].get("rating_lookup_status") == "found"
        ),
        "has_service_match": bool(normalized["matched_services"]),
        "has_ai": bool(normalized.get("ai_report")),
        "has_ai_email": bool(normalized.get("ai_email")),
        "has_audit_depth": has_audit_depth,
        "audit_coverage": audit_summary.get("coverage"),
        "audit_confidence": audit_summary.get("confidence"),
        "score_status": audit_summary.get("score_status"),
        "unknown_checks": audit_summary.get("unknown_checks"),
    }
    priority, next_action, priority_reason = priority_model(normalized)
    normalized["sales_priority_score"] = priority
    normalized["next_action"] = next_action
    normalized["priority_reason"] = priority_reason
    return normalized


def migrate(path: Path) -> list[dict]:
    leads = json.loads(path.read_text(encoding="utf-8"))
    return [normalize_lead(lead) for lead in leads]


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Zeplin lead JSON data.")
    parser.add_argument("--input", default="leads_final.json")
    parser.add_argument("--output", default="leads_final.json")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()

    output = ROOT / args.output
    migrated = migrate(ROOT / args.input)
    if args.write:
        output.write_text(json.dumps(migrated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {output}")
    else:
        print(json.dumps(migrated, ensure_ascii=False, indent=2))
    if args.build:
        build_dashboard(output)
        print("rebuilt public/index.html")


if __name__ == "__main__":
    main()
