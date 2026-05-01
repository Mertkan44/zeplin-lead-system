"""
Zeplin Media hizmet kataloğu ve otomatik eşleme motoru.
"""

# ── Hizmet kataloğu ────────────────────────────────────
ZEPLIN_SERVICES = [
    {
        "slug": "web_design",
        "name": "Web Sitesi Tasarımı",
        "desc": "Kurumsal, mobil uyumlu, hızlı web sitesi",
        "price_min": 15000,
        "price_max": 35000,
        "monthly": False,
        "triggers": ["no_website", "not_mobile", "slow_site"],
        "sectors": None,  # None = tüm sektörler
    },
    {
        "slug": "ssl_security",
        "name": "SSL & Güvenlik Kurulumu",
        "desc": "HTTPS, güvenli bağlantı, tarayıcı uyarıları",
        "price_min": 1500,
        "price_max": 3500,
        "monthly": False,
        "triggers": ["no_ssl"],
        "sectors": None,
    },
    {
        "slug": "seo_schema",
        "name": "SEO & Teknik Optimizasyon",
        "desc": "Schema.org, meta etiketler, site hızı, Core Web Vitals",
        "price_min": 8000,
        "price_max": 20000,
        "monthly": True,
        "triggers": ["no_schema", "no_og", "slow_site"],
        "sectors": None,
    },
    {
        "slug": "social_management",
        "name": "Sosyal Medya Yönetimi",
        "desc": "Instagram & TikTok içerik üretimi, planlama, etkileşim yönetimi",
        "price_min": 8000,
        "price_max": 18000,
        "monthly": True,
        "triggers": ["no_instagram", "low_engagement", "no_tiktok", "low_followers"],
        "sectors": None,
    },
    {
        "slug": "google_ads",
        "name": "Google Ads Yönetimi",
        "desc": "Arama reklamları, yerel kampanyalar, dönüşüm optimizasyonu",
        "price_min": 5000,
        "price_max": 15000,
        "monthly": True,
        "triggers": ["low_reviews", "no_schema", "low_rating"],
        "sectors": None,
    },
    {
        "slug": "reputation_management",
        "name": "Google Yorum & İtibar Yönetimi",
        "desc": "Yorum artırma, müşteri geri bildirim sistemi, Maps optimizasyonu",
        "price_min": 3000,
        "price_max": 8000,
        "monthly": True,
        "triggers": ["low_rating", "low_reviews"],
        "sectors": None,
    },
    {
        "slug": "whatsapp_business",
        "name": "WhatsApp Business Kurulumu",
        "desc": "WhatsApp Business API, otomatik yanıtlar, müşteri iletişim hattı",
        "price_min": 2000,
        "price_max": 5000,
        "monthly": False,
        "triggers": ["no_whatsapp"],
        "sectors": None,
    },
    {
        "slug": "email_marketing",
        "name": "E-posta Pazarlama Kurulumu",
        "desc": "E-posta listesi oluşturma, otomasyon, kampanya yönetimi",
        "price_min": 4000,
        "price_max": 10000,
        "monthly": True,
        "triggers": ["no_email_capture"],
        "sectors": None,
    },
    {
        "slug": "delivery_setup",
        "name": "Yemeksepeti / Getir Profil Yönetimi",
        "desc": "Platform kaydı, menü optimizasyonu, fotoğraf çekimi",
        "price_min": 3000,
        "price_max": 7000,
        "monthly": False,
        "triggers": ["no_delivery"],
        "sectors": ["restaurant", "cafe"],
    },
    {
        "slug": "reservation_system",
        "name": "Online Rezervasyon Sistemi",
        "desc": "Restoran/salon için online randevu ve rezervasyon entegrasyonu",
        "price_min": 4000,
        "price_max": 10000,
        "monthly": False,
        "triggers": ["no_delivery"],  # delivery yoksa rezervasyon da muhtemelen yok
        "sectors": ["restaurant", "salon"],
    },
    {
        "slug": "content_creation",
        "name": "İçerik & Fotoğraf Prodüksiyonu",
        "desc": "Profesyonel fotoğraf, reels, story ve feed içeriği",
        "price_min": 5000,
        "price_max": 12000,
        "monthly": True,
        "triggers": ["low_engagement", "no_tiktok"],
        "sectors": ["restaurant", "cafe", "salon", "retail"],
    },
    {
        "slug": "tiktok_management",
        "name": "TikTok Hesap Yönetimi",
        "desc": "TikTok içerik stratejisi, video prodüksiyonu, büyüme yönetimi",
        "price_min": 6000,
        "price_max": 14000,
        "monthly": True,
        "triggers": ["no_tiktok"],
        "sectors": ["restaurant", "cafe", "salon", "retail"],
    },
]

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
    if not w.get("has_website"):        triggers.add("no_website")
    if not w.get("has_ssl"):            triggers.add("no_ssl")
    if not w.get("is_mobile_friendly"): triggers.add("not_mobile")
    if w.get("load_time_ms") and w["load_time_ms"] > 3000: triggers.add("slow_site")
    if not w.get("has_schema"):         triggers.add("no_schema")
    if not w.get("has_og"):             triggers.add("no_og")
    if not w.get("has_email_capture"):  triggers.add("no_email_capture")
    if not w.get("has_whatsapp"):       triggers.add("no_whatsapp")

    # Instagram
    if not ig.get("has_instagram"):
        triggers.add("no_instagram")
    else:
        er = ig_stats.get("engagement_rate")
        followers = ig_stats.get("followers") or 0
        if er is not None and er < 1:   triggers.add("low_engagement")
        if followers < 500:             triggers.add("low_followers")

    # TikTok
    if not tiktok.get("has_tiktok"):    triggers.add("no_tiktok")

    # Maps
    rating = lead.get("rating")
    review_count = lead.get("review_count") or 0
    if rating is not None and rating < 3.5: triggers.add("low_rating")
    if review_count < 20:               triggers.add("low_reviews")

    # Delivery (restoran/cafe)
    if sector in ("restaurant", "cafe"):
        if not delivery.get("has_yemeksepeti") and not delivery.get("has_getir"):
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
        if any(t in triggers for t in svc["triggers"]):
            matched.append({
                "slug":      svc["slug"],
                "name":      svc["name"],
                "desc":      svc["desc"],
                "price_min": svc["price_min"],
                "price_max": svc["price_max"],
                "monthly":   svc["monthly"],
            })
    return matched


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
