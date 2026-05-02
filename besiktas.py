"""
Belirtilen ilçeden işletme tara, audit et, AI raporu üret, dashboard'a ekle.
"""
import argparse
import asyncio
import json
import subprocess
from playwright.async_api import async_playwright
from datetime import datetime

from src.config import groq_client
from src.audit.finder import (
    find_from_google_maps, check_website, detect_sector,
    find_instagram, get_instagram_stats,
    find_tiktok, check_delivery, compute_score
)
from src.dashboard.build import build_dashboard
from src.services import match_services, estimate_value

client = None

QUERY = "restoran"
CITY = "Istanbul Besiktas"
MAX_RESULTS = 5

# ── Sektör bazlı sistem sesi ───────────────────────────
SECTOR_VOICE = {
    "restaurant": (
        "Restoran sahibine yaziyorsun. Musteri deneyimi, online siparis (Yemeksepeti/Getir), "
        "rezervasyon sistemi ve Google yorumlari uzerinden analiz yap. "
        "Rakiplerle karsilastirmali dusun."
    ),
    "salon": (
        "Kuafor/guzellik salonu sahibine yaziyorsun. Online randevu, Instagram/TikTok icerigi, "
        "musteri sadakati ve kampanya firsatlari uzerinden analiz yap."
    ),
    "auto": (
        "Oto galeri veya servis sahibine yaziyorsun. Web sitesi guvenilirligi, Google Maps varligi, "
        "ikinci el arac ilanlari ve musteri yorumlari uzerinden analiz yap."
    ),
    "retail": (
        "Magaza/butik sahibine yaziyorsun. E-ticaret kanallari, sosyal medya vitrin kullanimi, "
        "kampanya yurutme ve musteri bagliligi uzerinden analiz yap."
    ),
    "default": (
        "Yerel isletme sahibine yaziyorsun. Genel dijital varlik, web sitesi kalitesi, "
        "sosyal medya ve musteri yorumlari uzerinden analiz yap."
    ),
}

# ── Scraper ────────────────────────────────────────────
async def scrape(query, city, max_results):
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        search = f"{query} {city}".replace(' ', '+')
        print(f"🔍 {search}")
        await page.goto(f"https://www.google.com/maps/search/{search}")
        await page.wait_for_timeout(3500)
        for _ in range(4):
            await page.keyboard.press("End")
            await page.wait_for_timeout(900)
        listings = await page.query_selector_all('a[href*="/maps/place/"]')
        print(f"  → {len(listings)} sonuç")
        for listing in listings[:max_results + 3]:
            try:
                name = await listing.get_attribute("aria-label")
                href = await listing.get_attribute("href")
                if name and href:
                    results.append({"name": name, "maps_url": href, "query": query, "city": city})
            except:
                continue
        await browser.close()
    return results[:max_results]

# ── AI ─────────────────────────────────────────────────
def ask(system_extra: str, prompt: str) -> str:
    global client
    if client is None:
        client = groq_client()
    system = f"Sen Zeplin Media'dan Mertkan'sin. Sadece Turkce yaziyorsun. {system_extra}"
    return client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt}
        ],
        max_tokens=500
    ).choices[0].message.content

def generate_report(lead):
    s     = lead["scoring"]
    ig    = lead["social"]
    ig_stats = ig.get("stats", {})
    tiktok = ig.get("tiktok", {}) or {}
    delivery = lead.get("delivery", {}) or {}
    sector = lead.get("sector", "default")

    followers = ig_stats.get("followers")
    er = ig_stats.get("engagement_rate")
    ig_line = f"Instagram: {ig.get('instagram_url','YOK')}"
    if followers: ig_line += f" ({followers} takipçi"
    if er is not None: ig_line += f", %{er} etkileşim"
    if followers or er is not None: ig_line += ")"

    tiktok_line = f"TikTok: {tiktok.get('tiktok_url','YOK')}"
    delivery_line = ""
    if sector in ("restaurant", "cafe"):
        ys = "VAR" if delivery.get("has_yemeksepeti") else "YOK"
        gt = "VAR" if delivery.get("has_getir") else "YOK"
        delivery_line = f"Yemeksepeti: {ys} | Getir: {gt}\n"

    extra_signals = (
        f"Schema.org: {'VAR' if lead['website'].get('has_schema') else 'YOK'}\n"
        f"Open Graph: {'VAR' if lead['website'].get('has_og') else 'YOK'}\n"
        f"WhatsApp: {'VAR' if lead['website'].get('has_whatsapp') else 'YOK'}\n"
        f"Google Puanı: {lead.get('rating','?')} ({lead.get('review_count','?')} yorum)\n"
        f"{delivery_line}"
    )

    return ask(
        SECTOR_VOICE.get(sector, SECTOR_VOICE["default"]),
        f"Su isletmenin dijital varlik analizini yap.\n\n"
        f"Isletme: {lead['name']}\n"
        f"Sektor: {sector}\n"
        f"Sehir: {lead.get('city','')}\n"
        f"Telefon: {lead.get('phone','YOK')}\n"
        f"Adres: {lead.get('address','YOK')}\n"
        f"Puan: {s['score']}/100 (Grade {s['grade']})\n"
        f"Web: {lead['website'].get('website_url','YOK')}\n"
        f"{ig_line}\n"
        f"{tiktok_line}\n"
        f"{extra_signals}"
        f"Sorunlar: {', '.join(s['issues']) or 'Yok'}\n"
        f"Firsatlar: {', '.join(s['opportunities']) or 'Yok'}\n\n"
        f"Maddeler halinde, max 140 kelime Turkce rapor yaz. Sektore ozel tavsiyeler ver."
    )

def generate_email(lead):
    s = lead["scoring"]
    sector = lead.get("sector", "default")

    return ask(
        SECTOR_VOICE.get(sector, SECTOR_VOICE["default"]),
        f"Sana bir ornek satis maili gosterecegim. Ayni tarz, bu isletmeye ozel yaz.\n\n"
        f"ORNEK:\nKonu: Shubra icin kucuk bir gozlem\n\nMerhaba,\n\n"
        f"Shubra'yi incelerken SSL eksikligini gorduk. Bu kucuk detay musteri guvenini etkiliyor.\n"
        f"Zeplin Media olarak SSL, hiz optimizasyonu ve sosyal medya yonetiminde uzmaniz.\n"
        f"15 dakikaniz var mi?\n\nMertkan | Zeplin Media\n\n"
        f"SIMDI BU ISLETME ICIN YAZ:\n"
        f"Ad: {lead['name']}\nSektor: {sector}\nSehir: {lead.get('city','')}\n"
        f"Google Puanı: {lead.get('rating','?')} ({lead.get('review_count','?')} yorum)\n"
        f"Web: {lead['website'].get('website_url','YOK')}\n"
        f"Instagram: {lead['social'].get('instagram_url','YOK')}\n"
        f"TikTok: {(lead['social'].get('tiktok') or {}).get('tiktok_url','YOK')}\n"
        f"Sorunlar: {', '.join(s['issues'])}\n\n"
        f"Konu satirini mutlaka yaz. Sektore ozel, kisisel, max 120 kelime."
    )

# ── Dashboard ──────────────────────────────────────────
def update_dashboard(data):
    json.dump(data, open('leads_final.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    build_dashboard()
    print("✅ Dashboard güncellendi!")

def git_push(msg):
    try:
        subprocess.run(['git','add','public/index.html','leads_final.json'], check=True)
        subprocess.run(['git','commit','-m', msg], check=True)
        subprocess.run(['git','push'], check=True)
        print("🚀 Push tamamlandı!")
    except Exception as e:
        print(f"Push hatası: {e}")

# ── ANA AKIŞ ───────────────────────────────────────────
async def run(query: str, city: str, max_results: int, push: bool):
    # 1. Scrape
    raw = await scrape(query, city, max_results)
    print(f"\n📋 {len(raw)} işletme bulundu:")
    for r in raw: print(f"  • {r['name']}")

    # 2. Audit
    audited = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="tr-TR"
        )
        page = await ctx.new_page()

        for lead in raw:
            name = lead["name"]
            print(f"\n► {name}")

            maps_data = await find_from_google_maps(page, lead["maps_url"], name)
            print(f"  🌐 {maps_data.get('website_url') or '—'}")
            print(f"  📞 {maps_data.get('phone') or '—'}")
            print(f"  📍 {maps_data.get('address') or '—'}")
            print(f"  ⭐ {maps_data.get('rating','—')} puan · {maps_data.get('review_count','?')} yorum")
            print(f"  🏷️  {maps_data.get('category') or '—'}")

            sector  = detect_sector(maps_data.get("category"))
            website = await check_website(maps_data.get("website_url"))
            print(f"  📊 Schema:{website['has_schema']} | OG:{website['has_og']} | WA:{website['has_whatsapp']}")

            instagram = await find_instagram(page, name, maps_data.get("website_url"))
            ig_stats = {}
            if instagram["has_instagram"] and instagram.get("instagram_username"):
                print(f"  📊 Instagram istatistikleri alınıyor...")
                ig_stats = await get_instagram_stats(page, instagram["instagram_username"])

            print(f"  🎵 TikTok kontrol ediliyor...")
            tiktok = await find_tiktok(page, name, website)

            delivery = {}
            if sector in ("restaurant", "cafe", "default"):
                print(f"  🛵 Delivery kontrol ediliyor...")
                delivery = await check_delivery(page, name, sector)

            maps_data["delivery"] = delivery
            scoring = compute_score(website, instagram, ig_stats, tiktok, maps_data, sector)

            lead_obj = {
                **lead,
                "sector":       sector,
                "phone":        maps_data.get("phone"),
                "address":      maps_data.get("address"),
                "rating":       maps_data.get("rating"),
                "review_count": maps_data.get("review_count"),
                "category":     maps_data.get("category"),
                "website":      website,
                "social":       {**instagram, "stats": ig_stats, "tiktok": tiktok},
                "delivery":     delivery,
                "scoring":      scoring,
            }
            lead_obj["matched_services"]   = match_services(lead_obj)
            lead_obj["estimated_value_tl"] = estimate_value(lead_obj)
            print(f"  💰 Tahmini değer: {lead_obj['estimated_value_tl']:,} TL/ay · {len(lead_obj['matched_services'])} hizmet eşleşti")
            audited.append(lead_obj)
            await asyncio.sleep(1)

        await browser.close()

    # 3. AI raporlar
    print("\n🤖 AI raporlar üretiliyor...")
    for lead in audited:
        print(f"  → {lead['name']} [{lead['sector']}]")
        lead["ai_report"] = generate_report(lead)
        lead["ai_email"]  = generate_email(lead)
        lead["last_analyzed"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 4. Birleştir
    existing = json.load(open('leads_final.json', encoding='utf-8'))
    existing_names = {l['name'] for l in existing}
    new_ones = [l for l in audited if l['name'] not in existing_names]
    merged = existing + new_ones
    print(f"\n📊 {len(existing)} mevcut + {len(new_ones)} yeni = {len(merged)} toplam")

    # 5. Dashboard & push
    update_dashboard(merged)
    if push:
        git_push(f"add {len(new_ones)} {city} leads — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    else:
        print("ℹ️ Push atlanıldı. Commit/push için --push kullan.")
    print(f"\n🎉 Tamamlandı!")

def parse_args():
    parser = argparse.ArgumentParser(description="Scan, audit, and publish Zeplin leads.")
    parser.add_argument("--query", default=QUERY)
    parser.add_argument("--city", default=CITY)
    parser.add_argument("--max", type=int, default=MAX_RESULTS, dest="max_results")
    parser.add_argument("--push", action="store_true", help="Commit and push generated files.")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args.query, args.city, args.max_results, args.push))
