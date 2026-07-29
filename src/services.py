"""
Zeplin Media hizmet katalogu ve kanita dayali otomatik esleme motoru.

Katalogdaki fiyatlar yonetim tarafindan onaylanana kadar sifir tutulur. Panel
uydurma paket veya ciro tahmini gostermek yerine tespit, kanit ve teslimati
gosterir.
"""

from __future__ import annotations

from typing import Any


def _service(
    *,
    slug: str,
    name: str,
    category: str,
    desc: str,
    service_type: str,
    recommendation_mode: str,
    triggers: list[str],
    deliverables: list[str],
    discovery_questions: list[str],
    exclusions: list[str] | None = None,
    sectors: list[str] | None = None,
    owner: str = "Sales",
) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": name,
        "category": category,
        "desc": desc,
        "service_type": service_type,
        "recommendation_mode": recommendation_mode,
        "triggers": triggers,
        "deliverables": deliverables,
        "discovery_questions": discovery_questions,
        "exclusions": exclusions or [],
        "sectors": sectors,
        "owner": owner,
        # Compatibility fields used by the current dashboard.
        "offer": name,
        "sales_angle": desc,
        "detects": "",
        "price_min": 0,
        "price_max": 0,
        "pricing_status": "approval_required",
        "monthly": service_type == "monthly",
    }


ZEPLIN_SERVICES = [
    _service(
        slug="corporate_website",
        name="Kurumsal Web Sitesi",
        category="Web ve Donusum",
        desc="Isletmeyi guvenilir anlatan, mobil uyumlu ve iletisim odakli web sitesi.",
        service_type="project",
        recommendation_mode="direct",
        triggers=["no_website"],
        deliverables=[
            "Sayfa ve bilgi mimarisi",
            "Mobil uyumlu tasarim ve gelistirme",
            "Form, telefon, WhatsApp ve harita aksiyonlari",
            "Temel teknik SEO ve yayinlama",
        ],
        discovery_questions=[
            "Yeni sitenin oncelikli amaci nedir?",
            "Hangi hizmetler ve lokasyonlar one cikacak?",
            "Alan adi, hosting ve mevcut icerikler kimin kontrolunde?",
        ],
        exclusions=["Alan adi ve hosting", "Fotograf/video cekimi", "Surekli icerik girisi"],
        owner="Web",
    ),
    _service(
        slug="landing_page",
        name="Landing Page ve Donusum Sayfasi",
        category="Web ve Donusum",
        desc="Tek bir kampanya veya hizmet icin olculebilir donusum sayfasi.",
        service_type="project",
        recommendation_mode="discovery_only",
        triggers=[],
        deliverables=[
            "Tek hedefli sayfa yapisi",
            "Form, telefon veya WhatsApp donusum akisi",
            "Mobil hiz optimizasyonu",
            "Donusum olcumleme kurulumu",
        ],
        discovery_questions=[
            "Aktif veya planlanan bir reklam kampanyasi var mi?",
            "Hedeflenen hizmet ve donusum aksiyonu nedir?",
            "Mevcut sayfada hangi sonuc olculebiliyor?",
        ],
        exclusions=["Reklam butcesi", "Kampanya yonetimi", "Buyuk olcekli produksiyon"],
        owner="Web",
    ),
    _service(
        slug="web_technical",
        name="Web Teknik Iyilestirme ve Bakim",
        category="Web ve Donusum",
        desc="Mevcut sitenin guvenlik, hiz, mobil kullanim ve teknik yapisinin iyilestirilmesi.",
        service_type="project_or_monthly",
        recommendation_mode="direct",
        triggers=["no_ssl", "not_mobile", "slow_site", "no_schema", "no_og"],
        deliverables=[
            "SSL ve guvenli yonlendirme kontrolu",
            "Mobil kullanim ve hiz iyilestirmeleri",
            "Kirik form, baglanti ve CTA kontrolleri",
            "Schema.org ve Open Graph temel duzenlemeleri",
        ],
        discovery_questions=[
            "Site hangi altyapiyla yonetiliyor?",
            "Teknik erisim ve yedek mevcut mu?",
            "En cok sorun yasanan sayfa veya akis hangisi?",
        ],
        exclusions=["Yeni site tasarimi", "Surekli SEO icerigi", "Ucuncu taraf lisanslari"],
        owner="Web",
    ),
    _service(
        slug="analytics_tracking",
        name="Olcumleme ve Donusum Takibi",
        category="Olcumleme",
        desc="Web, reklam, form, telefon ve WhatsApp aksiyonlarinin olculebilir hale getirilmesi.",
        service_type="project",
        recommendation_mode="conditional",
        triggers=["no_analytics"],
        deliverables=[
            "GA4 ve Google Tag Manager kurulumu veya duzenlemesi",
            "Form, telefon ve WhatsApp eventleri",
            "Reklam platformlari icin donusum altyapisi",
            "Test ve teslim dokumani",
        ],
        discovery_questions=[
            "Su anda hangi raporlar takip ediliyor?",
            "Basarili bir donusum olarak hangi aksiyon kabul ediliyor?",
            "GA4, Tag Manager veya reklam hesaplarina erisim var mi?",
        ],
        exclusions=["Reklam yonetimi", "Ozel BI gelistirmesi"],
        owner="Performance",
    ),
    _service(
        slug="google_business_local",
        name="Google Business Profile ve Yerel Gorunurluk",
        category="Yerel Gorunurluk",
        desc="Google Maps profilinin eksiksiz, guvenilir ve aksiyon odakli yonetilmesi.",
        service_type="project_or_monthly",
        recommendation_mode="direct",
        triggers=["low_rating", "low_reviews"],
        deliverables=[
            "Kategori, aciklama, hizmet ve iletisim alanlari",
            "Fotograf ve profil alanlarinin duzenlenmesi",
            "Yorum isteme ve cevaplama akisi",
            "Profil aksiyonlarinin olcumlenmesi",
        ],
        discovery_questions=[
            "Profilin sahiplik erisimi kimde?",
            "Musterilerden yorum istemek icin mevcut bir akis var mi?",
            "Yanlis veya eksik sube bilgisi bulunuyor mu?",
        ],
        exclusions=["Sahte veya satin alinmis yorum", "Sonuc ya da sira garantisi"],
        owner="SEO",
    ),
    _service(
        slug="seo_organic",
        name="SEO ve Organik Gorunurluk",
        category="Organik Buyume",
        desc="Teknik, icerik ve arama niyeti calismalariyla nitelikli organik talep kazanimi.",
        service_type="monthly",
        recommendation_mode="discovery_only",
        triggers=[],
        deliverables=[
            "Teknik SEO denetimi ve oncelik plani",
            "Anahtar kelime ve arama niyeti calismasi",
            "Sayfa ve icerik optimizasyonu",
            "Search Console takibi ve aylik rapor",
        ],
        discovery_questions=[
            "Organik aramadan hangi hizmetler icin talep bekleniyor?",
            "Search Console ve mevcut trafik verisi var mi?",
            "Icerik uretimi icin kim onay verecek?",
        ],
        exclusions=["Siralama garantisi", "Backlink satin alma", "Kapsam disi icerik produksiyonu"],
        owner="SEO",
    ),
    _service(
        slug="social_media",
        name="Sosyal Medya Yonetimi",
        category="Icerik ve Sosyal",
        desc="Markanin sosyal kanallarda duzenli ve amacli iletisim yurutmesi.",
        service_type="monthly",
        recommendation_mode="conditional",
        triggers=["no_instagram", "low_engagement"],
        deliverables=[
            "Aylik strateji ve icerik takvimi",
            "Kapsam dahilinde metin, tasarim ve yayinlama",
            "Temel topluluk yonetimi",
            "Aylik performans ozeti",
        ],
        discovery_questions=[
            "Hangi kanallar oncelikli ve hedef kitle kim?",
            "Aylik icerik onayini kim verecek?",
            "Mevcut cekim arsivi veya duzenli produksiyon imkani var mi?",
        ],
        exclusions=["Cekim gunu", "Influencer butcesi", "Reklam butcesi ve yonetimi"],
        owner="Social",
    ),
    _service(
        slug="content_production",
        name="Fotograf ve Video Icerik Produksiyonu",
        category="Icerik ve Sosyal",
        desc="Urun, mekan, ekip veya hizmet icin platforma uygun fotograf ve video uretimi.",
        service_type="project",
        recommendation_mode="discovery_only",
        triggers=[],
        deliverables=[
            "Cekim plani ve shot list",
            "Kapsam dahilinde fotograf ve video cekimi",
            "Secim, kurgu ve renk duzenleme",
            "Platform formatlarinda dosya teslimi",
        ],
        discovery_questions=[
            "Hangi urun, mekan veya hizmetler cekilecek?",
            "Istenen formatlar ve aylik kullanim plani nedir?",
            "Mekan, ekip ve urunler hangi tarihte hazir olabilir?",
        ],
        exclusions=["Oyuncu ve mekan giderleri", "Kapsam disi revizyon", "Reklam yayini"],
        owner="Creative",
    ),
    _service(
        slug="performance_ads",
        name="Performans Reklamlari Yonetimi",
        category="Reklam",
        desc="Google Ads veya Meta Ads uzerinden olculebilir talep ve donusum yonetimi.",
        service_type="monthly",
        recommendation_mode="discovery_only",
        triggers=[],
        deliverables=[
            "Hesap ve olcumleme kontrolu",
            "Kampanya plani, kurulum ve hedefleme",
            "Metin ve kapsam dahilindeki kreatif uyarlamalar",
            "Donusum, butce ve maliyet raporu",
        ],
        discovery_questions=[
            "Aylik medya butcesi ve hedef sonuc nedir?",
            "Talebi karsilayacak ekip ve operasyon kapasitesi var mi?",
            "Gecmis kampanya ve donusum verileri mevcut mu?",
        ],
        exclusions=["Medya butcesi", "Landing page yapimi", "Buyuk olcekli kreatif produksiyon"],
        owner="Performance",
    ),
    _service(
        slug="crm_lead_tracking",
        name="CRM ve Lead Takip Kurulumu",
        category="Satis Operasyonu",
        desc="Farkli kanallardan gelen taleplerin atanmasi, takibi ve raporlanmasi.",
        service_type="project",
        recommendation_mode="discovery_only",
        triggers=[],
        deliverables=[
            "Satis asamalari ve veri alanlari",
            "Lead kaynaklari ve atama akislari",
            "Gorev, hatirlatma ve takip sistemi",
            "Temel raporlama ve ekip egitimi",
        ],
        discovery_questions=[
            "Talepler su anda nerede tutuluyor?",
            "Bir lead'i kim, hangi adimlarla takip ediyor?",
            "Kac kullanici ve hangi entegrasyonlar gerekli?",
        ],
        exclusions=["Ucuncu taraf lisanslari", "Kapsam disi ozel entegrasyonlar"],
        owner="CRM",
    ),
    _service(
        slug="whatsapp_business",
        name="WhatsApp Business ve Mesaj Akislari",
        category="Satis Operasyonu",
        desc="Musteri mesajlarinin hizli, tutarli ve olculebilir bir akista yonetilmesi.",
        service_type="project_or_monthly",
        recommendation_mode="conditional",
        triggers=["no_whatsapp"],
        deliverables=[
            "Business profil ve temel ayarlar",
            "Karsilama, sik soru ve yonlendirme akislari",
            "Site ve kampanya baglantilari",
            "Uygunsa API/BSP entegrasyonu ve egitim",
        ],
        discovery_questions=[
            "Mesajlari kac kisi ve hangi cihazlardan yonetiyor?",
            "En cok gelen sorular ve kacirilan talepler neler?",
            "API, otomasyon veya sadece hizli iletisim butonu mu gerekli?",
        ],
        exclusions=["Meta/BSP kullanim bedelleri", "Ozel yazilim entegrasyonlari", "AI asistan"],
        owner="CRM",
    ),
]


TRIGGER_LABELS = {
    "no_website": "Web sitesi bulunamadi",
    "no_ssl": "Guvenli HTTPS baglantisi dogrulanamadi",
    "not_mobile": "Mobil uyum sorunu tespit edildi",
    "slow_site": "Sayfa acilis suresi yuksek olculdu",
    "no_schema": "Yapilandirilmis veri bulunamadi",
    "no_og": "Sosyal paylasim meta etiketleri bulunamadi",
    "no_email_capture": "E-posta toplama alani bulunamadi",
    "no_whatsapp": "Web sitesinde WhatsApp aksiyonu bulunamadi",
    "no_instagram": "Instagram hesabi bulunamadi",
    "low_engagement": "Dogrulanan Instagram etkilesimi dusuk",
    "low_followers": "Dogrulanan takipci sayisi dusuk",
    "no_tiktok": "TikTok hesabi bulunamadi",
    "low_rating": "Dogrulanan Google puani dusuk",
    "low_reviews": "Dogrulanan Google yorum sayisi az",
    "no_delivery": "Online siparis kanali bulunamadi",
    "no_analytics": "Gorunur analytics etiketi bulunamadi",
}


def lead_triggers(lead: dict) -> set[str]:
    triggers: set[str] = set()
    website = lead.get("website") or {}
    social = lead.get("social") or {}
    instagram_stats = social.get("stats") or {}

    if website.get("has_website") is False:
        triggers.add("no_website")
    if website.get("has_ssl") is False:
        triggers.add("no_ssl")
    if website.get("is_mobile_friendly") is False:
        triggers.add("not_mobile")
    if website.get("load_time_ms") and website["load_time_ms"] > 3000:
        triggers.add("slow_site")
    if website.get("has_schema") is False:
        triggers.add("no_schema")
    if website.get("has_og") is False:
        triggers.add("no_og")
    if website.get("has_email_capture") is False:
        triggers.add("no_email_capture")
    if website.get("has_whatsapp") is False:
        triggers.add("no_whatsapp")
    if website.get("has_analytics") is False:
        triggers.add("no_analytics")

    if social.get("has_instagram") is False:
        triggers.add("no_instagram")
    elif social.get("has_instagram") is True:
        engagement = instagram_stats.get("engagement_rate")
        followers = instagram_stats.get("followers")
        if engagement is not None and engagement < 1:
            triggers.add("low_engagement")
        if followers is not None and followers < 500:
            triggers.add("low_followers")

    tiktok = social.get("tiktok") or {}
    if tiktok.get("has_tiktok") is False:
        triggers.add("no_tiktok")

    rating = lead.get("rating")
    review_count = lead.get("review_count")
    if rating is not None and rating < 3.5:
        triggers.add("low_rating")
    if review_count is not None and review_count < 20:
        triggers.add("low_reviews")

    return triggers


def match_services(lead: dict) -> list[dict]:
    triggers = lead_triggers(lead)
    sector = lead.get("sector", "default")
    matched = []

    for service in ZEPLIN_SERVICES:
        if service["sectors"] and sector not in service["sectors"]:
            continue
        matched_triggers = [trigger for trigger in service["triggers"] if trigger in triggers]
        if not matched_triggers:
            continue

        mode = service["recommendation_mode"]
        confidence_base = 80 if mode == "direct" else 60
        confidence = min(95, confidence_base + max(0, len(matched_triggers) - 1) * 5)
        matched.append(
            {
                **service,
                "matched_triggers": matched_triggers,
                "evidence": [TRIGGER_LABELS.get(trigger, trigger) for trigger in matched_triggers],
                "confidence": confidence,
                "requires_discovery": mode != "direct",
            }
        )

    return sorted(
        matched,
        key=lambda service: (
            service["requires_discovery"],
            -service["confidence"],
            service["name"],
        ),
    )


def recommended_package(lead: dict) -> dict:
    """
    Eski veri semasi icin alan adi korunur; donen deger artik paket degil, kanita
    dayali birincil hizmet onerisisidir.
    """
    services = match_services(lead)
    if not services:
        return {
            "kind": "verification",
            "name": "Once ihtiyaci dogrula",
            "summary": "Otomatik hizmet onermek icin yeterli ve guvenilir kanit yok.",
            "primary_service": None,
            "included_services": [],
            "owner": "Sales",
            "stage": "Kesif",
            "confidence": 0,
            "evidence": [],
            "discovery_questions": [],
        }

    primary = services[0]
    evidence = list(
        dict.fromkeys(
            item
            for service in services[:3]
            for item in service.get("evidence", [])
        )
    )[:5]
    selected_services = [
        service for service in services if not service.get("requires_discovery")
    ][:3]
    if not selected_services:
        selected_services = services[:1]

    return {
        "kind": "service_recommendation",
        "name": primary["name"],
        "summary": (
            f"{primary['name']} icin {len(primary['matched_triggers'])} dogrulanmis sinyal bulundu."
            if not primary["requires_discovery"]
            else f"{primary['name']} ihtiyaci gorusmede dogrulanmali."
        ),
        "primary_service": primary["name"],
        "included_services": [service["name"] for service in selected_services],
        "owner": primary["owner"],
        "stage": "Kesif gerekli" if primary["requires_discovery"] else "Dogrulanmis acik",
        "confidence": primary["confidence"],
        "evidence": evidence,
        "deliverables": primary["deliverables"][:3],
        "discovery_questions": primary["discovery_questions"][:3],
        "exclusions": primary["exclusions"],
        "requires_discovery": primary["requires_discovery"],
    }


def estimate_value(lead: dict) -> int:
    """
    Yonetim onayli fiyat olmadan ciro tahmini uretme.

    Katalog fiyatlari onaylandiginda sadece pricing_status=approved hizmetler
    hesaba katilacak.
    """
    total = 0
    for service in match_services(lead):
        if service.get("pricing_status") != "approved":
            continue
        midpoint = (service["price_min"] + service["price_max"]) // 2
        total += midpoint if service["monthly"] else midpoint // 12
    return total
