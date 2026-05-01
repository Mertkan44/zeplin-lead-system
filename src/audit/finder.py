import asyncio
import json
import re
import httpx
import time
from playwright.async_api import async_playwright
from rich.console import Console

console = Console()

# ── Google Maps ────────────────────────────────────────
async def find_from_google_maps(page, maps_url: str, business_name: str) -> dict:
    result = {"website_url": None, "phone": None, "address": None}
    try:
        await page.goto(maps_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Web sitesi
        for sel in [
            'a[data-item-id="authority"]',
            'a[aria-label*="web"]',
            'a[href*="http"][data-tooltip="Web sitesini aç"]',
        ]:
            btn = await page.query_selector(sel)
            if btn:
                href = await btn.get_attribute("href")
                if href and "google" not in href:
                    result["website_url"] = href
                    break

        # Telefon — aria-label "Telefon: +90 xxx" formatında geliyor
        for sel in [
            'button[data-item-id*="phone:"]',
            'button[data-item-id*="phone"]',
        ]:
            phone_el = await page.query_selector(sel)
            if phone_el:
                label = await phone_el.get_attribute("aria-label") or ""
                # "Telefon: +90 212 327 28 29" → "+90 212 327 28 29"
                phone = re.sub(r'^[^:]+:\s*', '', label).strip()
                if phone:
                    result["phone"] = phone
                break

        # Adres — aria-label "Adres: Beşiktaş, İstanbul" formatı
        for sel in [
            'button[data-item-id="address"]',
            'button[aria-label*="Adres"]',
            '[data-item-id="address"]',
        ]:
            addr_el = await page.query_selector(sel)
            if addr_el:
                label = await addr_el.get_attribute("aria-label") or ""
                addr = re.sub(r'^[^:]+:\s*', '', label).strip()
                if addr:
                    result["address"] = addr
                break

        # Fallback: adres metnini doğrudan içerikten çek
        if not result["address"]:
            content = await page.content()
            m = re.search(r'"address"\s*:\s*"([^"]{10,100})"', content)
            if m:
                result["address"] = m.group(1)

    except Exception as e:
        console.print(f"[red]Maps hata: {e}[/red]")

    return result

# ── Web sitesi kontrol ─────────────────────────────────
async def check_website(url: str) -> dict:
    empty = {"has_website": False, "website_url": None, "has_ssl": False,
             "is_mobile_friendly": False, "load_time_ms": None, "website_loads": False}
    if not url:
        return empty
    r = {"has_website": True, "website_url": url, "has_ssl": url.startswith("https"),
         "is_mobile_friendly": False, "load_time_ms": None, "website_loads": False}
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            t0 = time.time()
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
            })
            r["load_time_ms"] = int((time.time() - t0) * 1000)
            r["website_loads"] = resp.status_code == 200
            r["is_mobile_friendly"] = "viewport" in resp.text.lower()
    except:
        pass
    return r

# ── Instagram bul ──────────────────────────────────────
async def find_instagram(page, business_name: str, website_url: str = None) -> dict:
    result = {"has_instagram": False, "instagram_url": None, "instagram_username": None}
    bl = {"p","reel","explore","stories","accounts","about","legal","help","press","api","sharer"}

    if website_url:
        try:
            await page.goto(website_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            for m in re.findall(r'instagram\.com/([a-zA-Z0-9_.]{2,30})/?', await page.content()):
                if m not in bl:
                    result.update(has_instagram=True,
                                  instagram_url=f"https://www.instagram.com/{m}/",
                                  instagram_username=m)
                    return result
        except:
            pass

    clean = re.sub(r'[^a-z0-9\s]', '',
        business_name.lower()
        .replace('ı','i').replace('ğ','g').replace('ü','u')
        .replace('ş','s').replace('ö','o').replace('ç','c'))
    words = clean.split()
    candidates = [''.join(words), '.'.join(words), '_'.join(words),
                  words[0] if words else '',
                  ''.join(words[:2]) if len(words) >= 2 else '']
    candidates = [c for c in candidates if len(c) >= 3]

    async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
        hdrs = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)"}
        for u in candidates:
            try:
                resp = await client.get(f"https://www.instagram.com/{u}/", headers=hdrs)
                if resp.status_code == 200 and '"@type":"ProfilePage"' in resp.text:
                    result.update(has_instagram=True,
                                  instagram_url=f"https://www.instagram.com/{u}/",
                                  instagram_username=u)
                    console.print(f"    [green]✓ Instagram: @{u}[/green]")
                    return result
                await asyncio.sleep(0.4)
            except:
                continue

    try:
        await page.goto(
            f"https://www.google.com/search?q={business_name.replace(' ','+')}+instagram",
            wait_until="domcontentloaded")
        await page.wait_for_timeout(2200)
        for m in re.findall(r'instagram\.com/([a-zA-Z0-9_.]{2,30})/?', await page.content()):
            if m not in bl:
                async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                    try:
                        resp = await client.get(f"https://www.instagram.com/{m}/",
                                                headers={"User-Agent": "Mozilla/5.0 (iPhone)"})
                        if resp.status_code == 200:
                            result.update(has_instagram=True,
                                          instagram_url=f"https://www.instagram.com/{m}/",
                                          instagram_username=m)
                            return result
                    except:
                        pass
    except:
        pass

    return result

# ── Instagram istatistikleri ───────────────────────────
def _parse_ig_num(s: str) -> int | None:
    """'1,234' veya '12.5K' veya '1.2M' → int"""
    s = s.strip().replace(',', '').replace('.', '')
    try:
        if s.upper().endswith('M'):
            return int(float(s[:-1]) * 1_000_000)
        if s.upper().endswith('K'):
            return int(float(s[:-1]) * 1_000)
        return int(s)
    except:
        return None

async def get_instagram_stats(page, username: str) -> dict:
    stats = {
        "followers": None,
        "following": None,
        "post_count": None,
        "avg_likes": None,
        "avg_comments": None,
        "engagement_rate": None,
    }
    if not username:
        return stats

    try:
        await page.goto(f"https://www.instagram.com/{username}/",
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(3500)
        content = await page.content()

        # ── Takipçi / takip / post — meta description ──
        # Format: "1,234 Followers, 567 Following, 89 Posts – ..."
        for pattern, key in [
            (r'([\d,\.]+[KkMm]?)\s+[Ff]ollowers?', "followers"),
            (r'([\d,\.]+[KkMm]?)\s+[Ff]ollowing', "following"),
            (r'([\d,\.]+[KkMm]?)\s+[Pp]osts?', "post_count"),
        ]:
            m = re.search(pattern, content)
            if m:
                stats[key] = _parse_ig_num(m.group(1))

        # ── Beğeni / yorum — sayfa JSON'undan ──────────
        # Instagram zaman zaman "like_count" veya "likes" embedliyor
        likes_raw = re.findall(r'"like_count"\s*:\s*(\d+)', content)
        if not likes_raw:
            likes_raw = re.findall(r'"likeCount"\s*:\s*(\d+)', content)
        comments_raw = re.findall(r'"comment_count"\s*:\s*(\d+)', content)
        if not comments_raw:
            comments_raw = re.findall(r'"commentCount"\s*:\s*(\d+)', content)

        likes = [int(x) for x in likes_raw[:12] if int(x) > 0]
        comments = [int(x) for x in comments_raw[:12]]

        if likes:
            stats["avg_likes"] = round(sum(likes) / len(likes))
        if comments:
            stats["avg_comments"] = round(sum(comments) / len(comments))

        # ── Etkileşim oranı ────────────────────────────
        # (avg_likes + avg_comments) / followers × 100
        followers = stats["followers"]
        if followers and followers > 0 and stats["avg_likes"] is not None:
            avg_l = stats["avg_likes"] or 0
            avg_c = stats["avg_comments"] or 0
            stats["engagement_rate"] = round((avg_l + avg_c) / followers * 100, 2)

        console.print(
            f"    📊 {followers or '?'} takipçi | "
            f"ort. {stats['avg_likes'] or '?'} beğeni | "
            f"%{stats['engagement_rate'] or '?'} etkileşim"
        )

    except Exception as e:
        console.print(f"[red]Instagram stats hata: {e}[/red]")

    return stats

# ── Skor ───────────────────────────────────────────────
def compute_score(website, instagram, ig_stats=None):
    score, issues, opportunities = 0, [], []

    if website["has_website"]:
        score += 30
        if website["has_ssl"]:
            score += 10
        else:
            issues.append("SSL yok"); opportunities.append("SSL kurulumu")
        if website["is_mobile_friendly"]:
            score += 10
        else:
            issues.append("Mobil uyumsuz"); opportunities.append("Mobil tasarım")
        if website.get("load_time_ms") and website["load_time_ms"] > 3000:
            issues.append(f"Site yavaş ({website['load_time_ms']}ms)")
            opportunities.append("Site hız optimizasyonu")
        else:
            score += 5
    else:
        issues.append("Web sitesi yok"); opportunities.append("Web sitesi tasarımı")

    if instagram["has_instagram"]:
        score += 25
        if ig_stats:
            er = ig_stats.get("engagement_rate")
            followers = ig_stats.get("followers") or 0
            if er is not None:
                if er >= 3:
                    score += 10
                elif er >= 1:
                    score += 5
                else:
                    issues.append(f"Düşük etkileşim (%{er})")
                    opportunities.append("İçerik stratejisi & etkileşim artırma")
            if followers < 500:
                issues.append(f"Az takipçi ({followers})")
                opportunities.append("Takipçi büyüme kampanyası")
    else:
        issues.append("Instagram yok"); opportunities.append("Instagram yönetimi")

    grade = "A" if score >= 80 else "B" if score >= 55 else "C" if score >= 35 else "D"
    return {"score": score, "max_score": 100, "grade": grade,
            "issues": issues, "opportunities": opportunities}

# ── Ana audit akışı ────────────────────────────────────
async def audit_all(leads_file="leads_raw.json"):
    with open(leads_file, encoding="utf-8") as f:
        leads = json.load(f)

    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="tr-TR"
        )
        page = await ctx.new_page()

        for lead in leads:
            name = lead["name"]
            console.print(f"\n[bold cyan]► {name}[/bold cyan]")

            maps_data = {}
            if lead.get("maps_url"):
                console.print("  📍 Google Maps...")
                maps_data = await find_from_google_maps(page, lead["maps_url"], name)
                console.print(f"     Web: {maps_data.get('website_url','—')}")
                console.print(f"     Tel: {maps_data.get('phone','—')}")
                console.print(f"     Adres: {maps_data.get('address','—')}")

            website = await check_website(maps_data.get("website_url"))

            console.print("  📸 Instagram...")
            instagram = await find_instagram(page, name, maps_data.get("website_url"))

            ig_stats = {}
            if instagram["has_instagram"]:
                ig_stats = await get_instagram_stats(page, instagram["instagram_username"])

            scoring = compute_score(website, instagram, ig_stats)

            results.append({
                **lead,
                "phone": maps_data.get("phone"),
                "address": maps_data.get("address"),
                "website": website,
                "social": {**instagram, "stats": ig_stats},
                "scoring": scoring,
            })
            await asyncio.sleep(1)

        await browser.close()

    with open("leads_audited.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    console.print(f"\n[bold green]✅ {len(results)} lead audit edildi → leads_audited.json[/bold green]")

if __name__ == "__main__":
    asyncio.run(audit_all())
