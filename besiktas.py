"""
Belirtilen ilçeden işletme tara, audit et, AI raporu üret, dashboard'a ekle.
Kullanım: python3 besiktas.py  (veya query/city değiştir)
"""
import asyncio, json, base64, os, subprocess
from playwright.async_api import async_playwright
from groq import Groq
from datetime import datetime

from src.audit.finder import (
    find_from_google_maps, check_website,
    find_instagram, get_instagram_stats, compute_score
)

os.environ["GROQ_API_KEY"] = open('.env').read().split('=')[1].strip()
client = Groq(api_key=os.environ["GROQ_API_KEY"])

QUERY = "restoran"
CITY  = "Istanbul Besiktas"
MAX   = 5

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
def ask(prompt):
    return client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Sen Zeplin Media'dan Mertkan'sin. Sadece Turkce yaziyorsun."},
            {"role": "user",   "content": prompt}
        ],
        max_tokens=450
    ).choices[0].message.content

def generate_report(lead):
    s = lead["scoring"]
    ig = lead["social"]
    ig_stats = ig.get("stats", {})
    followers = ig_stats.get("followers")
    er = ig_stats.get("engagement_rate")
    ig_line = f"Instagram: {ig.get('instagram_url','YOK')}"
    if followers: ig_line += f" ({followers} takipçi"
    if er is not None: ig_line += f", %{er} etkileşim"
    if followers or er is not None: ig_line += ")"

    return ask(
        f"Su isletmenin dijital varlik analizini yap.\n\n"
        f"Isletme: {lead['name']}\n"
        f"Sehir: {lead.get('city','')}\n"
        f"Telefon: {lead.get('phone','YOK')}\n"
        f"Adres: {lead.get('address','YOK')}\n"
        f"Puan: {s['score']}/100 (Grade {s['grade']})\n"
        f"Web: {lead['website'].get('website_url','YOK')}\n"
        f"{ig_line}\n"
        f"Sorunlar: {', '.join(s['issues']) or 'Yok'}\n"
        f"Firsatlar: {', '.join(s['opportunities']) or 'Yok'}\n\n"
        f"Maddeler halinde, max 130 kelime Turkce rapor yaz."
    )

def generate_email(lead):
    s = lead["scoring"]
    return ask(
        f"Sana bir ornek satis maili gosterecegim. Ayni tarz, bu isletmeye ozel yaz.\n\n"
        f"ORNEK:\nKonu: Shubra icin kucuk bir gozlem\n\nMerhaba,\n\n"
        f"Shubra'yi incelerken SSL eksikligini gorduk. Bu kucuk detay musteri guvenini etkiliyor.\n"
        f"Zeplin Media olarak SSL, hiz optimizasyonu ve sosyal medya yonetiminde uzmaniz.\n"
        f"15 dakikaniz var mi?\n\nMertkan | Zeplin Media\n\n"
        f"SIMDI BU ISLETME ICIN YAZ:\n"
        f"Ad: {lead['name']}\nSehir: {lead.get('city','')}\n"
        f"Web: {lead['website'].get('website_url','YOK')}\n"
        f"Instagram: {lead['social'].get('instagram_url','YOK')}\n"
        f"Sorunlar: {', '.join(s['issues'])}\n\n"
        f"Konu satirini mutlaka yaz. Ayni format, max 120 kelime."
    )

# ── Dashboard ──────────────────────────────────────────
def update_dashboard(data):
    b64 = base64.b64encode(json.dumps(data, ensure_ascii=True).encode()).decode('ascii')
    html = open('src/dashboard/template.html', encoding='utf-8').read().replace('__DATA__', b64)
    os.makedirs('public', exist_ok=True)
    open('public/index.html', 'w', encoding='utf-8').write(html)
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
async def main():
    # 1. Scrape
    raw = await scrape(QUERY, CITY, MAX)
    print(f"\n📋 {len(raw)} işletme bulundu:")
    for r in raw: print(f"  • {r['name']}")

    # 2. Audit (yeni finder ile)
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

            website  = await check_website(maps_data.get("website_url"))
            instagram = await find_instagram(page, name, maps_data.get("website_url"))

            ig_stats = {}
            if instagram["has_instagram"] and instagram.get("instagram_username"):
                print(f"  📊 Instagram istatistikleri alınıyor...")
                ig_stats = await get_instagram_stats(page, instagram["instagram_username"])

            scoring = compute_score(website, instagram, ig_stats)

            audited.append({
                **lead,
                "phone":   maps_data.get("phone"),
                "address": maps_data.get("address"),
                "website": website,
                "social":  {**instagram, "stats": ig_stats},
                "scoring": scoring,
            })
            await asyncio.sleep(1)

        await browser.close()

    # 3. AI
    print("\n🤖 AI raporlar üretiliyor...")
    for lead in audited:
        print(f"  → {lead['name']}")
        lead["ai_report"] = generate_report(lead)
        lead["ai_email"]  = generate_email(lead)
        lead["last_analyzed"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 4. Birleştir
    existing = json.load(open('leads_final.json', encoding='utf-8'))
    existing_names = {l['name'] for l in existing}
    new_ones = [l for l in audited if l['name'] not in existing_names]
    merged = existing + new_ones
    print(f"\n📊 {len(existing)} mevcut + {len(new_ones)} yeni = {len(merged)} toplam")

    json.dump(merged, open('leads_final.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)

    # 5. Dashboard & push
    update_dashboard(merged)
    git_push(f"add {len(new_ones)} {CITY} leads — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"\n🎉 Tamamlandı!")

asyncio.run(main())
