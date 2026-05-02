"""
Zeplin Media hizmet kataloğu ve otomatik eşleme motoru.
"""

# ── Hizmet kataloğu ────────────────────────────────────
ZEPLIN_SERVICES = [
    {
        "slug": "web_design",
        "name": "Web Sitesi Tasarımı",
        "category": "Web & Teknik",
        "desc": "Kurumsal, mobil uyumlu, hızlı web sitesi",
        "offer": "Vitrin site yenileme paketi",
        "owner": "Web",
        "sales_angle": "Müşteri ilk temasında güven veren hızlı ve mobil uyumlu bir vitrin.",
        "detects": "Web sitesi yok, mobil uyum zayıf veya site çok yavaş.",
        "price_min": 15000,
        "price_max": 35000,
        "monthly": False,
        "triggers": ["no_website", "not_mobile", "slow_site"],
        "sectors": None,  # None = tüm sektörler
    },
    {
        "slug": "ssl_security",
        "name": "SSL & Güvenlik Kurulumu",
        "category": "Web & Teknik",
        "desc": "HTTPS, güvenli bağlantı, tarayıcı uyarıları",
        "offer": "Güvenli site hızlı müdahale",
        "owner": "Web",
        "sales_angle": "Tarayıcı uyarılarını kaldırıp müşteri güvenini hızlıca toparlar.",
        "detects": "HTTPS/SSL eksikliği.",
        "price_min": 1500,
        "price_max": 3500,
        "monthly": False,
        "triggers": ["no_ssl"],
        "sectors": None,
    },
    {
        "slug": "seo_schema",
        "name": "SEO & Teknik Optimizasyon",
        "category": "Web & Teknik",
        "desc": "Schema.org, meta etiketler, site hızı, Core Web Vitals",
        "offer": "Teknik SEO ve görünürlük paketi",
        "owner": "SEO",
        "sales_angle": "Google'ın işletmeyi ve sayfaları daha doğru anlamasını sağlar.",
        "detects": "Schema.org, Open Graph, hız veya teknik görünürlük eksiği.",
        "price_min": 8000,
        "price_max": 20000,
        "monthly": True,
        "triggers": ["no_schema", "no_og", "slow_site"],
        "sectors": None,
    },
    {
        "slug": "social_management",
        "name": "Sosyal Medya Yönetimi",
        "category": "İçerik & Sosyal",
        "desc": "Instagram & TikTok içerik üretimi, planlama, etkileşim yönetimi",
        "offer": "Aylık sosyal medya yönetimi",
        "owner": "Sosyal",
        "sales_angle": "Düzenli içerik ve etkileşimle yerel talebi sıcak tutar.",
        "detects": "Instagram yok, düşük takipçi, düşük etkileşim veya TikTok yok.",
        "price_min": 8000,
        "price_max": 18000,
        "monthly": True,
        "triggers": ["no_instagram", "low_engagement", "no_tiktok", "low_followers"],
        "sectors": None,
    },
    {
        "slug": "google_ads",
        "name": "Google Ads Yönetimi",
        "category": "Büyüme & Reklam",
        "desc": "Arama reklamları, yerel kampanyalar, dönüşüm optimizasyonu",
        "offer": "Yerel talep kampanyası",
        "owner": "Performance",
        "sales_angle": "Hazır talebi telefon, rota ve rezervasyon aksiyonuna çevirir.",
        "detects": "Düşük yorum, zayıf puan veya teknik SEO eksiği.",
        "price_min": 5000,
        "price_max": 15000,
        "monthly": True,
        "triggers": ["low_reviews", "no_schema", "low_rating"],
        "sectors": None,
    },
    {
        "slug": "reputation_management",
        "name": "Google Yorum & İtibar Yönetimi",
        "category": "Yerel SEO",
        "desc": "Yorum artırma, müşteri geri bildirim sistemi, Maps optimizasyonu",
        "offer": "Maps itibar büyütme paketi",
        "owner": "SEO",
        "sales_angle": "Google Maps karar anında daha güçlü sosyal kanıt üretir.",
        "detects": "Düşük Google puanı veya az yorum.",
        "price_min": 3000,
        "price_max": 8000,
        "monthly": True,
        "triggers": ["low_rating", "low_reviews"],
        "sectors": None,
    },
    {
        "slug": "whatsapp_business",
        "name": "WhatsApp Business Kurulumu",
        "category": "İletişim & CRM",
        "desc": "WhatsApp Business API, otomatik yanıtlar, müşteri iletişim hattı",
        "offer": "WhatsApp dönüşüm hattı",
        "owner": "CRM",
        "sales_angle": "Siteden veya profilden gelen ilgiyi hızlı mesaja dönüştürür.",
        "detects": "Web sitesinde WhatsApp veya hızlı iletişim butonu yok.",
        "price_min": 2000,
        "price_max": 5000,
        "monthly": False,
        "triggers": ["no_whatsapp"],
        "sectors": None,
    },
    {
        "slug": "email_marketing",
        "name": "E-posta Pazarlama Kurulumu",
        "category": "İletişim & CRM",
        "desc": "E-posta listesi oluşturma, otomasyon, kampanya yönetimi",
        "offer": "Müşteri listesi ve kampanya otomasyonu",
        "owner": "CRM",
        "sales_angle": "Ziyaretçiyi tek seferlik trafik olmaktan çıkarıp tekrar pazarlanabilir kitleye çevirir.",
        "detects": "Web sitesinde e-posta toplama formu yok.",
        "price_min": 4000,
        "price_max": 10000,
        "monthly": True,
        "triggers": ["no_email_capture"],
        "sectors": None,
    },
    {
        "slug": "delivery_setup",
        "name": "Yemeksepeti / Getir Profil Yönetimi",
        "category": "Yerel Platformlar",
        "desc": "Platform kaydı, menü optimizasyonu, fotoğraf çekimi",
        "offer": "Online sipariş kanal kurulumu",
        "owner": "Operasyon",
        "sales_angle": "Restoran için ek sipariş kanalı ve keşif yüzeyi açar.",
        "detects": "Restoran/kafe için Yemeksepeti ve Getir sinyali yok.",
        "price_min": 3000,
        "price_max": 7000,
        "monthly": False,
        "triggers": ["no_delivery"],
        "sectors": ["restaurant", "cafe"],
    },
    {
        "slug": "reservation_system",
        "name": "Online Rezervasyon Sistemi",
        "category": "İletişim & CRM",
        "desc": "Restoran/salon için online randevu ve rezervasyon entegrasyonu",
        "offer": "Rezervasyon ve randevu akışı",
        "owner": "CRM",
        "sales_angle": "Telefon trafiğini düzenler, masaya veya randevuya dönüşen talebi ölçülebilir yapar.",
        "detects": "Restoran/salon için online sipariş/rezervasyon sinyali yok.",
        "price_min": 4000,
        "price_max": 10000,
        "monthly": False,
        "triggers": ["no_delivery"],  # delivery yoksa rezervasyon da muhtemelen yok
        "sectors": ["restaurant", "salon"],
    },
    {
        "slug": "content_creation",
        "name": "İçerik & Fotoğraf Prodüksiyonu",
        "category": "İçerik & Sosyal",
        "desc": "Profesyonel fotoğraf, reels, story ve feed içeriği",
        "offer": "Mekan içerik üretim günü",
        "owner": "Creative",
        "sales_angle": "Ürünü, mekanı ve deneyimi satışa uygun görsel dile taşır.",
        "detects": "Düşük etkileşim, TikTok yokluğu veya sosyal içerik boşluğu.",
        "price_min": 5000,
        "price_max": 12000,
        "monthly": True,
        "triggers": ["low_engagement", "no_tiktok"],
        "sectors": ["restaurant", "cafe", "salon", "retail"],
    },
    {
        "slug": "tiktok_management",
        "name": "TikTok Hesap Yönetimi",
        "category": "İçerik & Sosyal",
        "desc": "TikTok içerik stratejisi, video prodüksiyonu, büyüme yönetimi",
        "offer": "Kısa video büyüme paketi",
        "owner": "Creative",
        "sales_angle": "Keşif odaklı kısa video ile yeni kitleye ulaşır.",
        "detects": "TikTok hesabı veya TikTok URL sinyali yok.",
        "price_min": 6000,
        "price_max": 14000,
        "monthly": True,
        "triggers": ["no_tiktok"],
        "sectors": ["restaurant", "cafe", "salon", "retail"],
    },
    {
        "slug": "local_seo_gbp",
        "name": "Google Business Profil Optimizasyonu",
        "category": "Yerel SEO",
        "desc": "Maps profil düzeni, kategori, açıklama, fotoğraf ve rota aksiyonları",
        "offer": "Google Maps görünürlük paketi",
        "owner": "SEO",
        "sales_angle": "Yakındaki müşterinin karar ekranında işletmeyi daha güçlü gösterir.",
        "detects": "Az yorum, düşük puan veya zayıf yerel profil sinyali.",
        "price_min": 4000,
        "price_max": 9000,
        "monthly": True,
        "triggers": ["low_reviews", "low_rating"],
        "sectors": None,
    },
    {
        "slug": "analytics_tracking",
        "name": "Analytics & Dönüşüm Takibi",
        "category": "Büyüme & Reklam",
        "desc": "GA4, dönüşüm eventleri, reklam pikseli ve raporlama kurulumu",
        "offer": "Ölçüm altyapısı kurulumu",
        "owner": "Performance",
        "sales_angle": "Reklam ve web çalışmalarının ne kadar lead ürettiğini görünür yapar.",
        "detects": "Analytics veya dönüşüm takip sinyali yoksa.",
        "price_min": 5000,
        "price_max": 12000,
        "monthly": False,
        "triggers": ["no_analytics"],
        "sectors": None,
    },
    {
        "slug": "ai_whatsapp_assistant",
        "name": "AI WhatsApp Asistanı",
        "category": "İletişim & CRM",
        "desc": "Sık sorular, rezervasyon/sipariş yönlendirme ve otomatik karşılama",
        "offer": "AI müşteri karşılama hattı",
        "owner": "CRM",
        "sales_angle": "Yoğun saatlerde kaçan soruları ve rezervasyon niyetini yakalar.",
        "detects": "WhatsApp butonu veya hızlı iletişim akışı yoksa.",
        "price_min": 7000,
        "price_max": 18000,
        "monthly": True,
        "triggers": ["no_whatsapp"],
        "sectors": ["restaurant", "cafe", "salon", "retail"],
    },
]


TRIGGER_LABELS = {
    "no_website": "Web sitesi yok",
    "no_ssl": "SSL yok",
    "not_mobile": "Mobil uyum zayıf",
    "slow_site": "Site yavaş",
    "no_schema": "Schema.org yok",
    "no_og": "Open Graph yok",
    "no_email_capture": "E-posta formu yok",
    "no_whatsapp": "WhatsApp butonu yok",
    "no_instagram": "Instagram yok",
    "low_engagement": "Instagram etkileşimi düşük",
    "low_followers": "Takipçi tabanı zayıf",
    "no_tiktok": "TikTok yok",
    "low_rating": "Google puanı düşük",
    "low_reviews": "Google yorumu az",
    "no_delivery": "Online sipariş kanalı yok",
    "no_analytics": "Dönüşüm takibi yok",
}

# ── Trigger çıkarımı ───────────────────────────────────
def lead_triggers(lead: dict) -> set:
    triggers = set()
    w = lead.get("website") or {}
    ig = lead.get("social") or {}
    ig_stats = ig.get("stats") or {}
    tiktok = ig.get("tiktok") or {}
    delivery = lead.get("delivery") or {}
    sector = lead.get("sector", "default")

    # Web
    if w.get("has_website") is False:   triggers.add("no_website")
    if w.get("has_ssl") is False:       triggers.add("no_ssl")
    if w.get("is_mobile_friendly") is False: triggers.add("not_mobile")
    if w.get("load_time_ms") and w["load_time_ms"] > 3000: triggers.add("slow_site")
    if w.get("has_schema") is False:    triggers.add("no_schema")
    if w.get("has_og") is False:        triggers.add("no_og")
    if w.get("has_email_capture") is False: triggers.add("no_email_capture")
    if w.get("has_whatsapp") is False:  triggers.add("no_whatsapp")
    if w.get("has_analytics") is False: triggers.add("no_analytics")

    # Instagram
    if ig.get("has_instagram") is False:
        triggers.add("no_instagram")
    elif ig.get("has_instagram") is True:
        er = ig_stats.get("engagement_rate")
        followers = ig_stats.get("followers")
        if er is not None and er < 1:   triggers.add("low_engagement")
        if followers is not None and followers < 500: triggers.add("low_followers")

    # TikTok
    if tiktok.get("has_tiktok") is False: triggers.add("no_tiktok")

    # Maps
    rating = lead.get("rating")
    review_count = lead.get("review_count")
    if rating is not None and rating < 3.5: triggers.add("low_rating")
    if review_count is not None and review_count < 20: triggers.add("low_reviews")

    # Delivery (restoran/cafe)
    if sector in ("restaurant", "cafe"):
        if delivery.get("has_yemeksepeti") is False and delivery.get("has_getir") is False:
            triggers.add("no_delivery")

    return triggers


# ── Hizmet eşleme ──────────────────────────────────────
def match_services(lead: dict) -> list[dict]:
    triggers = lead_triggers(lead)
    sector = lead.get("sector", "default")
    matched = []
    for svc in ZEPLIN_SERVICES:
        # Sektör filtresi
        if svc["sectors"] and sector not in svc["sectors"]:
            continue
        # Trigger eşleşmesi
        matched_triggers = [t for t in svc["triggers"] if t in triggers]
        if matched_triggers:
            confidence = min(95, 55 + len(matched_triggers) * 15)
            matched.append({
                "slug":      svc["slug"],
                "name":      svc["name"],
                "category":  svc.get("category", "Genel"),
                "desc":      svc["desc"],
                "offer":     svc.get("offer", svc["name"]),
                "owner":     svc.get("owner", "Sales"),
                "sales_angle": svc.get("sales_angle", ""),
                "detects":   svc.get("detects", ""),
                "price_min": svc["price_min"],
                "price_max": svc["price_max"],
                "monthly":   svc["monthly"],
                "matched_triggers": matched_triggers,
                "evidence": [TRIGGER_LABELS.get(t, t) for t in matched_triggers],
                "confidence": confidence,
            })
    return sorted(matched, key=lambda s: (s["monthly"], s["confidence"], s["price_max"]), reverse=True)


def recommended_package(lead: dict) -> dict:
    """Satış ekibinin ilk görüşmede hangi paketle gideceğini özetler."""
    services = match_services(lead)
    monthly = [svc for svc in services if svc["monthly"]]
    one_time = [svc for svc in services if not svc["monthly"]]
    primary = (monthly or services or [{}])[0]
    categories = []
    for svc in services:
        if svc.get("category") not in categories:
            categories.append(svc.get("category"))

    if not services:
        return {
            "name": "Veri tamamlama",
            "summary": "Satış paketi önermeden önce iletişim ve audit sinyalleri tamamlanmalı.",
            "primary_service": None,
            "included_services": [],
            "owner": "Sales",
            "stage": "Araştırma",
            "confidence": 0,
            "evidence": [],
        }

    if len(monthly) >= 2:
        package_name = "Growth Sprint"
        stage = "Teklif"
    elif primary.get("category") == "Web & Teknik":
        package_name = "Dijital Sağlık Onarımı"
        stage = "Teknik çözüm"
    elif primary.get("category") == "İçerik & Sosyal":
        package_name = "İçerik Büyüme Paketi"
        stage = "İçerik planı"
    elif primary.get("category") in ("İletişim & CRM", "Yerel Platformlar"):
        package_name = "Dönüşüm Altyapısı"
        stage = "Operasyon"
    else:
        package_name = "Yerel Görünürlük Paketi"
        stage = "Teklif"

    evidence = []
    for svc in services[:3]:
        evidence.extend(svc.get("evidence", []))
    evidence = list(dict.fromkeys(evidence))[:5]

    return {
        "name": package_name,
        "summary": f"{primary.get('offer', primary.get('name'))} ile başlanabilir; {len(services)} hizmet sinyali bulundu.",
        "primary_service": primary.get("name"),
        "included_services": [svc["name"] for svc in services[:4]],
        "owner": primary.get("owner", "Sales"),
        "stage": stage,
        "confidence": max(svc.get("confidence", 0) for svc in services),
        "evidence": evidence,
        "categories": categories[:4],
    }


# ── Tahmini değer ──────────────────────────────────────
def estimate_value(lead: dict) -> int:
    """Matched hizmetlere göre tahmini aylık TL potansiyeli döner."""
    svcs = match_services(lead)
    total = 0
    for svc in svcs:
        mid = (svc["price_min"] + svc["price_max"]) // 2
        if svc["monthly"]:
            total += mid          # zaten aylık
        else:
            total += mid // 12    # one-time → aylık amortismana böl
    return total
