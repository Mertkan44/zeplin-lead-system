from __future__ import annotations

from typing import Any

from src.research_brief import build_research_brief
from src.services import ZEPLIN_SERVICES


def _verified_findings(lead: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        finding
        for finding in (lead.get("audit_findings") or [])
        if finding.get("status") in {"confirmed", "likely"}
        and finding.get("title")
        and finding.get("evidence")
    ]


def _services(
    lead: dict[str, Any], manual_gaps: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], bool]:
    catalog = {service["slug"]: service for service in ZEPLIN_SERVICES}
    manual_services = []
    for finding in manual_gaps:
        for slug in finding.get("service_slugs") or []:
            if slug not in catalog or any(item.get("slug") == slug for item in manual_services):
                continue
            manual_services.append(
                {
                    **catalog[slug],
                    "evidence": [finding.get("evidence")],
                    "matched_finding_codes": [finding.get("code")],
                    "confidence": 100,
                    "requires_discovery": False,
                }
            )
    matched = lead.get("matched_services") or []
    combined = manual_services + [
        item for item in matched if not any(row.get("slug") == item.get("slug") for row in manual_services)
    ]
    if combined:
        return combined[:3], False
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
    research_brief = build_research_brief(lead)
    findings = [*_verified_findings(lead), *(research_brief.get("manual_gaps") or [])]
    gap_findings = [
        finding for finding in findings if finding.get("finding_type", "gap") != "opportunity"
    ]
    services, discovery_only = _services(lead, research_brief.get("manual_gaps") or [])
    primary_service = services[0] if services else {}
    primary_finding_codes = set(primary_service.get("matched_finding_codes") or [])
    sender = _first_name(sender_name)

    evidence_points = [
        {
            "title": finding.get("title"),
            "evidence": finding.get("evidence"),
            "impact": finding.get("impact"),
            "confidence": int(finding.get("confidence") or 0),
            "source_url": finding.get("source_url"),
            "source_label": finding.get("source_label"),
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
        first = next(
            (
                finding
                for finding in gap_findings
                if finding.get("code") in primary_finding_codes
            ),
            gap_findings[0],
        )
        observation = str(first.get("title") or "").strip()
        impact = str(first.get("impact") or "müşteri deneyimini etkileyebilir").strip()
        evidence = str(first.get("evidence") or "").strip()
        verification = str(first.get("verification") or "").strip()
        summary = (
            f"{name} için {len(gap_findings)} doğrulanmış dijital açık bulundu. "
            f"İlk görüşmede “{observation}” başlığı ve bunun {impact.lower()} etkisi üzerinden ilerle."
        )
        opener = (
            f"Merhaba, ben {sender}, Zeplin Media'dan arıyorum. {name} için herkese açık "
            f"kanallarda kısa bir ön inceleme yaptık. “{observation}” başlığı öne çıktı. "
            "Mevcut durumu iki dakikada sizden teyit edip tespiti paylaşabilir miyim?"
        )
        message_core = (
            f"{name} için yaptığımız kısa ön incelemede {observation.lower()} başlığını not ettik. "
            f"Kontrolümüzde gördüğümüz sinyal: {evidence} "
            "Uygunsa mevcut durumu teyit edip çözüm yönünü 10 dakikada paylaşmak isteriz."
        )
        email_observation = f"{observation}. Kontrolümüzde gördüğümüz sinyal: {evidence}"
        review_note = verification or "Tespiti göndermeden önce kaynağı son kez açıp kontrol et."
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
        email_observation = (
            "Kesin bir dijital açık henüz doğrulanmadı. Bu nedenle önce hedeflerinizi ve "
            "mevcut çalışma düzeninizi öğrenmek istiyoruz."
        )
        review_note = "Kesin açık iddiası kullanma; işletmenin hedefini görüşmede öğren."

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
    deliverable = (primary_service.get("deliverables") or ["ihtiyaca uygun bir çalışma planı"])[0]
    whatsapp = (
        f"Merhaba, ben {sender}, Zeplin Media. {message_core} "
        f"Uygun olursa ilk adım olarak {deliverable.lower()} tarafını konuşabiliriz. "
        "Bu hafta 10 dakikalık uygun bir zamanınız var mı?"
    )
    instagram_dm = f"Merhaba, ben {sender} / Zeplin Media. {message_core} Uygunsanız detayı burada paylaşabilirim."
    email_subject = f"{name} için kısa dijital ön inceleme"
    email_body = (
        f"Merhaba,\n\n{name} için herkese açık dijital kanallarda kısa bir ön inceleme yaptık.\n\n"
        f"Gördüğümüz başlık:\n{email_observation}\n\n"
        f"Bu başlık doğrulanırsa {primary_name} kapsamında şu somut çıktıyla başlayabiliriz: "
        f"{deliverable}. İhtiyacınızı dinlemeden bunu kesin bir teklif "
        "olarak sunmuyoruz.\n\n"
        "Uygunsanız bu hafta 10-15 dakikalık kısa bir görüşme planlayabiliriz.\n\n"
        f"{sender}\nZeplin Media"
    )

    research_emails = ((lead.get("research") or {}).get("website") or {}).get("emails") or []
    email_address = lead.get("email") or (
        research_emails[0] if isinstance(research_emails, list) and research_emails else None
    )
    channel_drafts = [
        {
            "channel": "phone",
            "label": "Arama",
            "status": "ready" if lead.get("phone") else "blocked",
            "recipient_available": bool(lead.get("phone")),
            "body": opener,
            "review_note": review_note,
        },
        {
            "channel": "whatsapp",
            "label": "WhatsApp",
            "status": "review" if lead.get("phone") else "blocked",
            "recipient_available": bool(lead.get("phone")),
            "body": whatsapp,
            "review_note": review_note,
        },
        {
            "channel": "instagram",
            "label": "Instagram DM",
            "status": "review" if (lead.get("social") or {}).get("instagram_url") else "blocked",
            "recipient_available": bool((lead.get("social") or {}).get("instagram_url")),
            "body": instagram_dm,
            "review_note": review_note,
        },
        {
            "channel": "email",
            "label": "E-posta",
            "status": "review" if email_address else "blocked",
            "recipient_available": bool(email_address),
            "recipient": email_address,
            "subject": email_subject,
            "body": email_body,
            "review_note": review_note,
        },
    ]

    conversation_goal = (
        f"{primary_name} ihtiyacını doğrula ve uygun kişiden kısa bir keşif görüşmesi için zaman al."
        if services
        else "İşletmenin öncelikli dijital hedefini öğren ve doğru hizmet alanını keşfet."
    )
    call_steps = [
        {
            "key": "permission",
            "label": "İzin al",
            "instruction": "Kendini tanıt, ön incelemeyi söyle ve iki dakika konuşmak için izin iste.",
        },
        {
            "key": "verify",
            "label": "Tespiti doğrula",
            "instruction": (
                f"{evidence_points[0]['title']} başlığının güncel olup olmadığını sor."
                if evidence_points
                else "Mevcut dijital hedeflerini ve bugün nasıl çalıştıklarını sor."
            ),
        },
        {
            "key": "discover",
            "label": "İhtiyacı aç",
            "instruction": discovery_questions[0],
        },
        {
            "key": "next_step",
            "label": "Sonraki adımı al",
            "instruction": "İlgi varsa karar verici ve uygun takip zamanını netleştir.",
        },
    ]

    return {
        "version": 3,
        "lead_name": name,
        "context": f"{_business_type(lead)}{location_text}",
        "discovery_only": discovery_only or not bool(gap_findings),
        "research_status": research_brief["status"],
        "summary": summary,
        "call_brief": {
            "duration_label": "30 saniyede hazırlan",
            "business_summary": summary,
            "conversation_goal": conversation_goal,
            "evidence_count": len(evidence_points),
            "service_count": len(service_rows),
        },
        "call_steps": call_steps,
        "evidence_points": evidence_points,
        "services": service_rows,
        "call_opener": opener,
        "whatsapp_message": whatsapp,
        "instagram_dm": instagram_dm,
        "email_subject": email_subject,
        "email_body": email_body,
        "channel_drafts": channel_drafts,
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
