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
        slug="website_creation",
        name="Website Oluşturma",
        category="Web",
        desc="İşletmenin hedeflerine göre mobil uyumlu, güven veren ve iletişim odaklı website oluşturma.",
        service_type="project",
        recommendation_mode="direct",
        triggers=["no_website"],
        deliverables=[
            "İhtiyaç analizi, sayfa planı ve içerik mimarisi",
            "Mobil uyumlu arayüz tasarımı ve geliştirme",
            "Form, telefon, WhatsApp, harita ve sosyal medya bağlantıları",
            "Yayınlama, temel teknik kontroller ve kullanım teslimi",
        ],
        discovery_questions=[
            "Website hangi ana hedefe hizmet edecek: tanıtım, rezervasyon, satış veya lead toplama?",
            "Hangi hizmetler, ürünler ve lokasyonlar öne çıkarılacak?",
            "Alan adı, hosting, metinler ve görseller hazır mı?",
        ],
        exclusions=["Alan adı ve hosting bedeli", "Fotoğraf/video çekimi", "Sürekli içerik ve bakım"],
        owner="Web",
    ),
    _service(
        slug="seo_organic",
        name="SEO ve Organik Görünürlük",
        category="SEO",
        desc="İşletmenin arama motorlarında doğru sorgularda görünmesini ve organik talep kazanmasını geliştiren SEO çalışması.",
        service_type="monthly",
        recommendation_mode="discovery_only",
        triggers=[],
        deliverables=[
            "Teknik SEO denetimi ve öncelikli aksiyon planı",
            "Anahtar kelime, rakip ve arama niyeti araştırması",
            "Sayfa, içerik ve yerel görünürlük optimizasyonu",
            "Search Console takibi ve aylık çalışma raporu",
        ],
        discovery_questions=[
            "Hangi hizmetler ve bölgeler için Google'da görünmek istiyorsunuz?",
            "Mevcut website, Search Console ve trafik verilerine erişim var mı?",
            "İçerik üretimini ve website değişikliklerini kim onaylayacak?",
        ],
        exclusions=["Sıralama garantisi", "Reklam yönetimi ve bütçesi", "Ücretli backlink satın alımı"],
        owner="SEO",
    ),
    _service(
        slug="social_media",
        name="Sosyal Medya Yönetimi",
        category="Sosyal Medya",
        desc="Markanın sosyal medya hesaplarının strateji, içerik planı, yayın ve takip süreçleriyle düzenli yönetimi.",
        service_type="monthly",
        recommendation_mode="conditional",
        triggers=["no_instagram", "low_engagement", "low_followers"],
        deliverables=[
            "Aylık sosyal medya stratejisi ve içerik takvimi",
            "Paylaşım metinleri, yayın planı ve hesap düzeni",
            "Kapsam dahilinde yorum ve mesaj takibi",
            "Aylık performans değerlendirmesi",
        ],
        discovery_questions=[
            "Hangi sosyal medya kanalları yönetilecek ve hedef kitle kim?",
            "Aylık paylaşım sıklığı ve içerik onayını verecek kişi kim?",
            "Mevcut fotoğraf/video arşivi var mı, düzenli çekim gerekiyor mu?",
        ],
        exclusions=["Fotoğraf/video çekimi", "Reklam bütçesi ve yönetimi", "Influencer giderleri"],
        owner="Social",
    ),
    _service(
        slug="post_design",
        name="Post Tasarımları",
        category="Sosyal Medya",
        desc="Marka kimliğine uygun, sosyal medya formatlarında tekil veya seri post tasarımları.",
        service_type="project_or_monthly",
        recommendation_mode="discovery_only",
        triggers=[],
        deliverables=[
            "Görsel dil ve tasarım yönünün belirlenmesi",
            "Feed postu, carousel ve story uyarlamaları",
            "Kapsam dahilinde metin yerleşimi ve revizyon",
            "Yayına hazır platform formatlarında teslim",
        ],
        discovery_questions=[
            "Aylık veya proje bazlı kaç tasarım gerekiyor?",
            "Marka kılavuzu, logo ve kurumsal renkler hazır mı?",
            "Metinleri ve kampanya bilgilerini kim sağlayacak?",
        ],
        exclusions=["Fotoğraf/video üretimi", "Sosyal medya hesap yönetimi", "Sınırsız revizyon"],
        owner="Design",
    ),
    _service(
        slug="ad_management",
        name="Reklam Yönetimi",
        category="Reklam",
        desc="Meta Ads ve Google Ads kampanyalarının hedef, bütçe, kreatif ve performans takibiyle yönetimi.",
        service_type="monthly",
        recommendation_mode="discovery_only",
        triggers=[],
        deliverables=[
            "Reklam hesabı ve mevcut kampanyaların kontrolü",
            "Hedef kitle, bütçe ve kampanya planı",
            "Kampanya kurulumu, optimizasyonu ve takibi",
            "Performans ve harcama raporu",
        ],
        discovery_questions=[
            "Hangi platformlarda reklam verilecek ve ana hedef nedir?",
            "Aylık reklam bütçesi ne kadar?",
            "Kullanılacak kreatifler ve yönlendirilecek sayfa hazır mı?",
        ],
        exclusions=["Reklam platformu bütçesi", "Website oluşturma", "Çekim ve kapsam dışı kreatif üretimi"],
        owner="Performance",
    ),
    _service(
        slug="photo_video_shoot",
        name="Video ve Fotoğraf Çekimi",
        category="Prodüksiyon",
        desc="İşletme, mekan, ekip, ürün veya hizmet için profesyonel fotoğraf ve video içerik üretimi.",
        service_type="project",
        recommendation_mode="discovery_only",
        triggers=[],
        deliverables=[
            "Çekim öncesi brief, konsept ve çekim planı",
            "Kapsam dahilinde fotoğraf ve video çekimi",
            "Seçim, temel kurgu ve renk düzenleme",
            "Belirlenen formatlarda dijital teslim",
        ],
        discovery_questions=[
            "Neler çekilecek ve içerikler nerelerde kullanılacak?",
            "Çekim mekanı, süresi, ekip ve model ihtiyacı nedir?",
            "Kaç fotoğraf ve kaç video teslimi bekleniyor?",
        ],
        exclusions=["Mekan, model, oyuncu ve ulaşım giderleri", "Kapsam dışı ileri post-prodüksiyon", "Sınırsız revizyon"],
        owner="Production",
    ),
    _service(
        slug="menu_shoot",
        name="Menü Çekimi",
        category="Prodüksiyon",
        desc="Restoran ve kafeler için ürünleri iştah açıcı ve marka diline uygun gösteren menü fotoğraf/video çekimi.",
        service_type="project",
        recommendation_mode="discovery_only",
        triggers=[],
        sectors=["restaurant"],
        deliverables=[
            "Ürün listesi, çekim sırası ve görsel stil planı",
            "Yemek ve içecek fotoğraf/video çekimi",
            "Renk, ışık ve temel retouch düzenlemeleri",
            "Menü, sosyal medya ve teslimat platformlarına uygun çıktılar",
        ],
        discovery_questions=[
            "Kaç ürün çekilecek ve ürünler hangi kanallarda kullanılacak?",
            "Mekan çekime ne zaman hazırlanabilir; sunum/styling desteği var mı?",
            "Baskı menüsü, dijital menü veya sosyal medya için hangi formatlar gerekiyor?",
        ],
        exclusions=["Food styling malzemeleri ve özel dekor", "Baskı ve menü tasarımı", "Mekan/ulaşım giderleri"],
        owner="Production",
    ),
    _service(
        slug="reels_production",
        name="Reels Çekim ve Edit",
        category="Prodüksiyon",
        desc="Sosyal medya için kısa, dinamik ve markaya uygun Reels videolarının çekimi ve kurgusu.",
        service_type="project_or_monthly",
        recommendation_mode="conditional",
        triggers=["low_engagement"],
        deliverables=[
            "Konu, senaryo akışı ve çekim planı",
            "Dikey format Reels çekimi",
            "Dinamik kurgu, altyazı, müzik ve temel efektler",
            "Yayına hazır video teslimi",
        ],
        discovery_questions=[
            "Ayda kaç Reels gerekiyor ve ana içerik başlıkları neler?",
            "Kamera karşısına kim çıkacak; mekan ve ürünler hazır mı?",
            "Referans alınacak video tarzı veya marka dili var mı?",
        ],
        exclusions=["Oyuncu/influencer giderleri", "İleri seviye VFX ve 3D", "Sosyal medya yayın yönetimi"],
        owner="Production",
    ),
    _service(
        slug="chatbot_voicebot",
        name="Chatbot ve Seslibot Kurulumu",
        category="Yapay Zeka ve Otomasyon",
        desc="Müşteri sorularını karşılayan, bilgi toplayan ve uygun akışa yönlendiren chatbot veya seslibot kurulumu.",
        service_type="project_or_monthly",
        recommendation_mode="discovery_only",
        triggers=[],
        deliverables=[
            "İhtiyaç analizi ve konuşma akışlarının hazırlanması",
            "Chatbot veya seslibot kurulumu ve bilgi tabanı",
            "Uygun kanallara ve sistemlere bağlantı",
            "Test, yayına alma, eğitim ve izleme",
        ],
        discovery_questions=[
            "Bot hangi kanalda çalışacak ve hangi işleri yapacak?",
            "En sık gelen sorular, randevu veya satış akışları neler?",
            "Mevcut website, telefon, CRM veya takvim entegrasyonu var mı?",
        ],
        exclusions=["Üçüncü taraf platform, telefon ve kullanım ücretleri", "Kapsam dışı özel yazılım entegrasyonları", "İnsan operatör hizmeti"],
        owner="AI",
    ),
    _service(
        slug="ai_ad_videos",
        name="Reklamlar İçin Gelişmiş Yapay Zeka Videoları",
        category="Yapay Zeka ve Kreatif",
        desc="Reklam kampanyaları için yapay zeka destekli konsept, görsel, sahne, ses ve kurgu üretimi.",
        service_type="project",
        recommendation_mode="discovery_only",
        triggers=[],
        deliverables=[
            "Reklam hedefi, konsept ve senaryo geliştirme",
            "Yapay zeka ile sahne ve görsel üretimi",
            "Seslendirme, müzik, kurgu ve reklam formatları",
            "Farklı metin veya açılışlarla kreatif varyasyonları",
        ],
        discovery_questions=[
            "Reklamın hedefi, hedef kitlesi ve kullanılacağı platform nedir?",
            "Ürün görselleri, marka öğeleri ve zorunlu mesajlar hazır mı?",
            "Gerçekçi, sinematik, sunuculu veya ürün odaklı hangi stil isteniyor?",
        ],
        exclusions=["Reklam bütçesi ve kampanya yönetimi", "Lisansı ayrıca gereken stok/oyuncu kullanımı", "Sınırsız kreatif varyasyon"],
        owner="AI Creative",
    ),
]


TRIGGER_LABELS = {
    "no_website": "Web sitesi bulunamadı",
    "no_ssl": "Güvenli HTTPS bağlantısı doğrulanamadı",
    "not_mobile": "Mobil uyum sorunu tespit edildi",
    "slow_site": "Sayfa açılış süresi yüksek ölçüldü",
    "no_schema": "Yapılandırılmış veri bulunamadı",
    "no_og": "Sosyal paylaşım meta etiketleri bulunamadı",
    "no_email_capture": "E-posta toplama alanı bulunamadı",
    "no_whatsapp": "Web sitesinde WhatsApp aksiyonu bulunamadı",
    "no_instagram": "Instagram hesabı bulunamadı",
    "low_engagement": "Doğrulanan Instagram etkileşimi düşük",
    "low_followers": "Doğrulanan takipçi sayısı düşük",
    "no_tiktok": "TikTok hesabı bulunamadı",
    "low_rating": "Doğrulanan Google puanı düşük",
    "low_reviews": "Doğrulanan Google yorum sayısı az",
    "no_delivery": "Online sipariş kanalı bulunamadı",
    "no_analytics": "Görünür analytics etiketi bulunamadı",
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
            "name": "Önce ihtiyacı doğrula",
            "summary": "Otomatik hizmet önermek için yeterli ve güvenilir kanıt yok.",
            "primary_service": None,
            "included_services": [],
            "owner": "Sales",
            "stage": "Keşif",
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
            f"{primary['name']} için {len(primary['matched_triggers'])} doğrulanmış sinyal bulundu."
            if not primary["requires_discovery"]
            else f"{primary['name']} ihtiyacı görüşmede doğrulanmalı."
        ),
        "primary_service": primary["name"],
        "included_services": [service["name"] for service in selected_services],
        "owner": primary["owner"],
        "stage": "Keşif gerekli" if primary["requires_discovery"] else "Doğrulanmış açık",
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
