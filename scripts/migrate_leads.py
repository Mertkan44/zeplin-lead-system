import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.dashboard.build import build_dashboard
from src.services import estimate_value, match_services


WEBSITE_DEFAULTS = {
    "has_website": False,
    "website_url": None,
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
    "tiktok_url": None,
}

SOCIAL_DEFAULTS = {
    "has_instagram": False,
    "instagram_url": None,
    "instagram_username": None,
    "has_facebook": False,
    "facebook_url": None,
    "stats": {
        "followers": None,
        "following": None,
        "post_count": None,
        "avg_likes": None,
        "avg_comments": None,
        "engagement_rate": None,
    },
    "tiktok": {"has_tiktok": None, "tiktok_url": None, "tiktok_username": None},
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
    if lead.get("sector"):
        return lead["sector"]
    text = " ".join(str(lead.get(k) or "") for k in ("query", "category", "name")).lower()
    if any(token in text for token in ("restoran", "restaurant", "cafe", "kafe", "teras", "lokanta")):
        return "restaurant"
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
    issues = lead["scoring"]["issues"][:3]
    opportunities = lead["scoring"]["opportunities"][:3]
    issue_line = ", ".join(issues) if issues else "kritik bir açık görünmüyor"
    opp_line = ", ".join(opportunities) if opportunities else "mevcut görünürlüğü koruma"
    return (
        f"{lead['name']} için dijital görünürlük skoru {lead['scoring']['score']}/100. "
        f"Öne çıkan bulgular: {issue_line}. "
        f"Zeplin Media tarafında ilk fırsatlar: {opp_line}. "
        "İlk temas için kısa bir teknik sağlık kontrolü ve net aksiyon listesi önerilir."
    )


def fallback_email(lead: dict) -> str:
    first_issue = (lead["scoring"]["issues"] or ["dijital görünürlüğünüzde geliştirilebilir noktalar"])[0]
    return (
        f"Konu: {lead['name']} için kısa bir dijital sağlık notu\n\n"
        "Merhaba,\n\n"
        f"{lead['name']} için yaptığımız hızlı kontrolde özellikle \"{first_issue}\" başlığını not ettik. "
        "Bu tip küçük açıklar arama görünürlüğünü, müşteri güvenini ve dönüşümü doğrudan etkileyebiliyor.\n\n"
        "Zeplin Media olarak size kısa bir analiz ve uygulanabilir aksiyon listesi çıkarabiliriz. "
        "Bu hafta 15 dakikalık bir görüşme uygun olur mu?\n\n"
        "Mertkan | Zeplin Media"
    )


def priority_model(lead: dict) -> tuple[int, str, str]:
    score = lead["scoring"]["score"]
    value = lead.get("estimated_value_tl") or 0
    issues = lead["scoring"].get("issues") or []
    has_contact = bool(lead.get("phone") or lead.get("address"))
    has_ai = bool(lead.get("ai_report") and lead.get("ai_email"))
    has_services = bool(lead.get("matched_services"))
    audit_depth = lead.get("data_quality", {}).get("has_audit_depth", False)

    priority = 0
    if score < 40:
        priority += 32
    elif score < 55:
        priority += 24
    elif score < 75:
        priority += 16
    else:
        priority += 8
    priority += min(28, value // 2500)
    priority += min(12, len(issues) * 3)
    if has_contact:
        priority += 14
    if has_ai:
        priority += 10
    if has_services:
        priority += 8
    if audit_depth:
        priority += 8

    if not has_contact:
        action = "Telefon/adres tamamla"
        reason = "Ulaşım bilgisi eksik olduğu için satış aksiyonu başlamadan önce veri tamamlanmalı."
    elif not has_ai:
        action = "AI rapor ve mail üret"
        reason = "İlk temas içeriği eksik."
    elif not has_services:
        action = "Derin audit yap"
        reason = "Satılabilir hizmet eşleşmesi oluşmamış."
    elif score < 55:
        action = "Öncelikli arama yap"
        reason = "Dijital açık net ve çözüm potansiyeli yüksek."
    else:
        action = "Satış mailini gönder"
        reason = "İlk temas için rapor ve teklif başlığı hazır."

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
    normalized["website"] = deep_merge(WEBSITE_DEFAULTS, normalized.get("website"))
    normalized["social"] = deep_merge(SOCIAL_DEFAULTS, normalized.get("social"))
    normalized["delivery"] = deep_merge(DELIVERY_DEFAULTS, normalized.get("delivery"))
    normalized["scoring"] = normalize_score(normalized.get("scoring") or {})
    normalized["matched_services"] = match_services(normalized)
    normalized["estimated_value_tl"] = estimate_value(normalized)
    normalized["ai_report"] = normalized.get("ai_report") or fallback_report(normalized)
    normalized["ai_email"] = normalized.get("ai_email") or fallback_email(normalized)
    normalized["last_analyzed"] = normalized.get("last_analyzed") or datetime.now().strftime("%Y-%m-%d %H:%M")
    normalized["schema_version"] = 2
    website = normalized["website"]
    has_audit_depth = all(
        website.get(key) is not None
        for key in ("has_schema", "has_og", "has_email_capture", "has_whatsapp")
    )
    normalized["data_quality"] = {
        "has_contact": bool(normalized.get("phone") or normalized.get("address")),
        "has_maps_rating": normalized.get("rating") is not None,
        "has_service_match": bool(normalized["matched_services"]),
        "has_ai": bool(normalized.get("ai_report") and normalized.get("ai_email")),
        "has_audit_depth": has_audit_depth,
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
