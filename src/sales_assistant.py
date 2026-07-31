from __future__ import annotations

from typing import Any


def _verified_findings(lead: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        finding
        for finding in (lead.get("audit_findings") or [])
        if finding.get("status") in {"confirmed", "likely"}
        and finding.get("title")
        and finding.get("evidence")
    ]


def _services(lead: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    matched = lead.get("matched_services") or []
    if matched:
        return matched[:3], False
    return (lead.get("discovery_services") or [])[:3], True


def _business_type(lead: dict[str, Any]) -> str:
    return str(lead.get("category") or lead.get("sector") or "işletme").strip()


def _first_name(value: str | None) -> str:
    text = str(value or "").strip()
    return text.split()[0] if text else "Zeplin Media"


def build_sales_playbook(
    lead: dict[str, Any],
    *,
    sender_name: str | None = None,
) -> dict[str, Any]:
    name = str(lead.get("name") or "İşletme").strip()
    city = str(lead.get("city") or "").strip()
    findings = _verified_findings(lead)
    gap_findings = [
        finding for finding in findings if finding.get("finding_type", "gap") != "opportunity"
    ]
    services, discovery_only = _services(lead)
    primary_service = services[0] if services else {}
    sender = _first_name(sender_name)

    evidence_points = [
        {
            "title": finding.get("title"),
            "evidence": finding.get("evidence"),
            "impact": finding.get("impact"),
            "confidence": int(finding.get("confidence") or 0),
            "source_url": finding.get("source_url"),
            "finding_type": finding.get("finding_type") or "gap",
        }
        for finding in findings[:3]
    ]

    service_rows = [
        {
            "slug": service.get("slug"),
            "name": service.get("name"),
            "why": (
                "; ".join(service.get("evidence") or [])[:280]
                if service.get("evidence")
                else "İşletme tipine uygun olabilir; ihtiyaç görüşmede doğrulanmalı."
            ),
            "deliverables": (service.get("deliverables") or [])[:3],
            "requires_discovery": bool(service.get("requires_discovery", discovery_only)),
        }
        for service in services
    ]

    if gap_findings:
        first = gap_findings[0]
        observation = str(first.get("title") or "").strip()
        impact = str(first.get("impact") or "müşteri deneyimini etkileyebilir").strip()
        summary = (
            f"{name} için {len(gap_findings)} doğrulanmış dijital açık bulundu. "
            f"İlk görüşmede “{observation}” başlığı ve bunun {impact.lower()} etkisi üzerinden ilerle."
        )
        opener = (
            f"Merhaba, ben {sender}, Zeplin Media'dan arıyorum. {name} için kısa bir dijital "
            f"ön inceleme yaptık ve {observation.lower()} başlığını fark ettik. "
            "Bunun mevcut müşteri akışınıza etkisini iki dakikada teyit edebilir miyim?"
        )
        message_core = (
            f"{name} için yaptığımız kısa ön incelemede “{observation}” başlığını not ettik. "
            "Uygunsa tespiti ve çözüm yönünü 10 dakikalık kısa bir görüşmede paylaşmak isteriz."
        )
    else:
        service_name = primary_service.get("name") or "dijital görünürlük"
        summary = (
            f"{name} için kesin satış iddiası oluşturacak bir açık henüz doğrulanmadı. "
            f"{service_name} ihtiyacını keşif sorularıyla teyit et; bunu tespit gibi sunma."
        )
        opener = (
            f"Merhaba, ben {sender}, Zeplin Media'dan arıyorum. {name} gibi {_business_type(lead)} "
            "işletmelerinin dijital müşteri kazanım süreçleri üzerine çalışıyoruz. "
            "Şu anda geliştirmek istediğiniz kanalın hangisi olduğunu kısaca öğrenebilir miyim?"
        )
        message_core = (
            f"{name} için dijital görünürlük ve içerik tarafında kısa bir ön inceleme yaptık. "
            "Kesin bir öneri sunmadan önce hedeflerinizi öğrenip size uygun alanları birlikte "
            "netleştirmek isteriz."
        )

    discovery_questions = []
    for service in services:
        for question in service.get("discovery_questions") or []:
            if question and question not in discovery_questions:
                discovery_questions.append(question)
    discovery_questions = discovery_questions[:6] or [
        "Önümüzdeki üç ayda dijital tarafta en çok hangi sonucu büyütmek istiyorsunuz?",
        "Şu anda içerik, reklam ve müşteri dönüşlerini kim yönetiyor?",
        "Daha önce dışarıdan hizmet aldınız mı; ne işe yaradı, ne yaramadı?",
    ]

    primary_name = primary_service.get("name") or "ihtiyaç görüşmesi"
    location_text = f" · {city}" if city else ""
    whatsapp = (
        f"Merhaba, ben {sender} / Zeplin Media. {message_core} "
        "Bu hafta size uygun kısa bir zaman var mı?"
    )
    instagram_dm = (
        f"Merhaba, {message_core} Detayı burada paylaşabilir veya kısa bir görüşme planlayabiliriz."
    )
    email_subject = f"{name} için kısa dijital ön inceleme"
    email_body = (
        f"Merhaba,\n\n{message_core}\n\n"
        f"İlk değerlendirmemizde görüşülebilecek hizmet yönü: {primary_name}. "
        "Bunu ihtiyaçlarınızı dinlemeden kesin bir teklif olarak sunmuyoruz.\n\n"
        "Bu hafta 10-15 dakikalık kısa bir görüşme için uygun olduğunuz bir zaman var mı?\n\n"
        f"{sender}\nZeplin Media"
    )

    return {
        "version": 1,
        "lead_name": name,
        "context": f"{_business_type(lead)}{location_text}",
        "discovery_only": discovery_only or not bool(gap_findings),
        "summary": summary,
        "evidence_points": evidence_points,
        "services": service_rows,
        "call_opener": opener,
        "whatsapp_message": whatsapp,
        "instagram_dm": instagram_dm,
        "email_subject": email_subject,
        "email_body": email_body,
        "discovery_questions": discovery_questions,
        "objection_responses": [
            {
                "objection": "Şu an ihtiyacımız yok.",
                "response": (
                    "Anlıyorum. Size bir paket anlatmak yerine yalnızca ön incelemede gördüğümüz "
                    "başlığı paylaşayım; önceliğiniz değilse dosyayı kapatırım."
                ),
            },
            {
                "objection": "Ajansla çalışıyoruz.",
                "response": (
                    "Harika, mevcut ekibinizin yerine geçmek zorunda değiliz. Tespit ettiğimiz alan "
                    "onların kapsamında mı, yoksa tamamlayıcı bir ihtiyaç mı birlikte netleştirebiliriz."
                ),
            },
            {
                "objection": "Fiyat nedir?",
                "response": (
                    "Kapsamı görmeden rastgele fiyat vermek istemeyiz. Hedefi, mevcut materyalleri "
                    "ve iş yükünü netleştirip yalnızca gereken kalemler için teklif çıkarıyoruz."
                ),
            },
        ],
        "guardrails": [
            "Kanıtı olmayan bir metriği veya açığı kesin bilgi gibi söyleme.",
            "Keşif hizmetini tespit edilmiş sorun gibi sunma.",
            "Fiyat ve sonuç garantisi verme; kapsamı görüşmede netleştir.",
        ],
    }
