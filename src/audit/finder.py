import asyncio
import json
import re
import httpx
import time
from urllib.parse import quote_plus
from playwright.async_api import async_playwright
from rich.console import Console

console = Console()

# ── Sektör tespiti ─────────────────────────────────────
_SECTOR_MAP = {
    "restaurant": ["restoran","restaurant","pizza","kebap","pide","döner","börek","ocakbaşı",
                   "cafe","kafeterya","kahve","kafe","coffee","bistro","meyhane","balık",
                   "çiğköfte","burger","sushi","waffle","pastane","fırın","bakery"],
    "salon":      ["kuaför","güzellik","beauty","spa","nail","berber","brow","lash","wax",
                   "estetik","pilates","yoga","masaj","massage"],
    "auto":       ["oto","araba","araç","servis","kaporta","lastik","galeri","garaj","yedek"],
    "retail":     ["butik","giyim","mağaza","market","shop","aksesuar","çiçek","florist",
                   "kitap","optik","eczane","pharmacy","jewel","mücevher"],
    "health":     ["hastane","klinik","doktor","diş","dental","poliklinik","eczane","optik"],
}

def detect_sector(category: str | None) -> str:
    if not category:
        return "default"
    cat = category.lower()
    for sector, kws in _SECTOR_MAP.items():
        if any(k in cat for k in kws):
            return sector
    return "default"


def _normalize_maps_card_text(text: str) -> str:
    return re.sub(r"\s+", "\n", text or "").strip()


def _parse_maps_search_card(text: str) -> dict:
    normalized = _normalize_maps_card_text(text)
    result = {"rating": None, "review_count": None, "category": None, "phone": None, "address": None}
    if not normalized:
        return result

    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    saw_no_reviews = False
    for line in lines:
        if result["rating"] is None and re.fullmatch(r"[\d][,.][\d]", line):
            try:
                result["rating"] = float(line.replace(",", "."))
            except Exception:
                pass
        if re.search(r"yorum yok|no reviews", line, re.I):
            saw_no_reviews = True
        if result["phone"] is None:
            phone_match = re.search(r"(\+?\d[\d\s()]{8,})", line)
            if phone_match:
                result["phone"] = phone_match.group(1).strip()
        if result["category"] is None and "·" in line:
            category = line.split("·", 1)[0].strip()
            if category and len(category) < 60 and not re.search(r"kapalı|açık|yorum|reviews?", category, re.I):
                result["category"] = category
            maybe_address = line.rsplit("·", 1)[-1].strip()
            if (
                result["address"] is None
                and maybe_address
                and len(maybe_address) > 4
                and not re.search(r"kapalı|açık|yorum|reviews?", maybe_address, re.I)
                and not re.search(r"^\+?\d", maybe_address)
            ):
                result["address"] = maybe_address

    if saw_no_reviews and result["rating"] is None:
        result["review_count"] = 0

    return result


async def _find_maps_search_fallback(page, business_name: str, city: str | None = None) -> dict:
    fallback = {"rating": None, "review_count": None, "category": None, "phone": None, "address": None}
    query = " ".join(part for part in [business_name, city] if part).strip()
    if not query:
        return fallback
    try:
        await page.goto(f"https://www.google.com/maps/search/{quote_plus(query)}", wait_until="domcontentloaded")
        await page.wait_for_timeout(4500)
        cards = await page.query_selector_all("div.Nv2PK")
        for card in cards[:12]:
            try:
                title_el = await card.query_selector("div.qBF1Pd")
                title = (await title_el.inner_text()).strip() if title_el else ""
                if title and title.lower() != business_name.lower():
                    continue
                html = await card.inner_html()
                if business_name.lower() not in html.lower():
                    continue
                parsed = _parse_maps_search_card(await card.inner_text())
                for key, value in parsed.items():
                    if fallback.get(key) is None and value is not None:
                        fallback[key] = value
                if any(value is not None for value in fallback.values()):
                    return fallback
            except Exception:
                continue
    except Exception:
        pass
    return fallback

# ── Google Maps ────────────────────────────────────────
async def find_from_google_maps(page, maps_url: str, business_name: str, city: str | None = None) -> dict:
    result = {
        "website_url": None, "phone": None, "address": None,
        "rating": None, "review_count": None, "category": None,
    }
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

        # Telefon
        for sel in ['button[data-item-id*="phone:"]', 'button[data-item-id*="phone"]']:
            phone_el = await page.query_selector(sel)
            if phone_el:
                label = await phone_el.get_attribute("aria-label") or ""
                phone = re.sub(r'^[^:]+:\s*', '', label).strip()
                if phone:
                    result["phone"] = phone
                break

        # Adres
        for sel in ['button[data-item-id="address"]', 'button[aria-label*="Adres"]', '[data-item-id="address"]']:
            addr_el = await page.query_selector(sel)
            if addr_el:
                label = await addr_el.get_attribute("aria-label") or ""
                addr = re.sub(r'^[^:]+:\s*', '', label).strip()
                if addr:
                    result["address"] = addr
                break

        content = await page.content()
        body_text = await page.locator("body").inner_text()

        # Adres fallback
        if not result["address"]:
            m = re.search(r'"address"\s*:\s*"([^"]{10,100})"', content)
            if m:
                result["address"] = m.group(1)
        if not result["address"]:
            m = re.search(rf'{re.escape(business_name)}.*?\n(?:[\d][,.][\d]\n)?(?:.+?·.+?\n)?([^\n]+/(?:İstanbul|Istanbul))', body_text, re.S)
            if m:
                result["address"] = m.group(1).strip()

        # Rating — aria-label "4,5 yıldız" veya "4.5 stars" formatı
        for sel in ['span[aria-label*="yıldız"]', 'span[aria-label*="star"]', 'div[aria-label*="yıldız"]']:
            el = await page.query_selector(sel)
            if el:
                label = await el.get_attribute("aria-label") or ""
                m = re.search(r'([\d][,.][\d])', label)
                if m:
                    result["rating"] = float(m.group(1).replace(',', '.'))
                    break

        # Rating fallback — JSON embedded
        if not result["rating"]:
            m = re.search(r'"ratingValue"\s*:\s*"?([\d.]+)"?', content)
            if not m:
                m = re.search(r'"stars"\s*:\s*([\d.]+)', content)
            if m:
                result["rating"] = float(m.group(1))
        if result["rating"] is None:
            m = re.search(rf'{re.escape(business_name)}\n([\d][,.][\d])\n', body_text)
            if m:
                result["rating"] = float(m.group(1).replace(',', '.'))

        # Review count — "(1.234 yorum)" veya "(1,234 reviews)"
        for pattern in [
            r'\(([\d\.]+)\s*yorum',
            r'\(([\d,\.]+)\s*review',
            r'"reviewCount"\s*:\s*"?(\d+)"?',
            r'"userRatingCount"\s*:\s*(\d+)',
        ]:
            m = re.search(pattern, content, re.I)
            if m:
                raw = m.group(1).replace('.','').replace(',','')
                try:
                    result["review_count"] = int(raw)
                    break
                except:
                    pass
        if result["review_count"] is None:
            if re.search(r'\bYorum yok\b', body_text, re.I) or re.search(r'\bNo reviews\b', body_text, re.I):
                result["review_count"] = 0

        # Kategori (business type)
        for sel in ['button[jsaction*="category"]', 'span[jsaction*="category"]',
                    'a[jsaction*="category"]', '[data-item-id*="category"]']:
            el = await page.query_selector(sel)
            if el:
                txt = (await el.inner_text()).strip()
                if txt and len(txt) < 60:
                    result["category"] = txt
                    break

        # Kategori fallback — JSON
        if not result["category"]:
            m = re.search(r'"category"\s*:\s*"([^"]{3,50})"', content)
            if m:
                result["category"] = m.group(1)
        if not result["category"]:
            m = re.search(rf'{re.escape(business_name)}\n(?:[\d][,.][\d]\n)?([^\n·]+)', body_text)
            if m:
                candidate = m.group(1).strip()
                if candidate and len(candidate) < 60 and candidate.lower() not in {"genel bakış", "overview"}:
                    result["category"] = candidate

    except Exception as e:
        console.print(f"[red]Maps hata: {e}[/red]")

    if (
        result["rating"] is None
        or result["review_count"] is None
        or result["category"] is None
        or result["phone"] is None
    ):
        fallback = await _find_maps_search_fallback(page, business_name, city)
        for key, value in fallback.items():
            if result.get(key) is None and value is not None:
                result[key] = value

    if result["rating"] is not None and result["review_count"] == 0:
        result["review_count"] = None

    return result

# ── Web sitesi kontrol ─────────────────────────────────
async def check_website(url: str) -> dict:
    empty = {
        "has_website": False, "website_url": None, "has_ssl": False,
        "is_mobile_friendly": False, "load_time_ms": None, "website_loads": False,
        "has_schema": False, "has_og": False, "meta_description": None,
        "has_robots": False, "has_sitemap": False,
        "has_email_capture": False, "has_whatsapp": False,
        "tiktok_url": None,   # tiktok link website'te varsa
    }
    if not url:
        return empty

    r = {
        "has_website": True, "website_url": url, "has_ssl": url.startswith("https"),
        "is_mobile_friendly": False, "load_time_ms": None, "website_loads": False,
        "has_schema": False, "has_og": False, "meta_description": None,
        "has_robots": False, "has_sitemap": False,
        "has_email_capture": False, "has_whatsapp": False,
        "tiktok_url": None,
    }

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            # Ana sayfa
            t0 = time.time()
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
            })
            r["load_time_ms"] = int((time.time() - t0) * 1000)
            r["website_loads"] = resp.status_code == 200

            html = resp.text
            html_lower = html.lower()

            r["is_mobile_friendly"] = "viewport" in html_lower

            # Schema.org / JSON-LD
            r["has_schema"] = 'application/ld+json' in html_lower

            # Open Graph
            r["has_og"] = bool(re.search(r'property=["\']og:', html, re.I))

            # Meta description
            m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{10,300})',
                          html, re.I)
            if not m:
                m = re.search(r'<meta[^>]+content=["\']([^"\']{10,300})["\'][^>]+name=["\']description["\']',
                              html, re.I)
            if m:
                r["meta_description"] = m.group(1).strip()[:200]

            # E-posta formu / mailto
            r["has_email_capture"] = bool(re.search(
                r'mailto:|input[^>]+type=["\']email["\']|<form[^>]+action[^>]*mail|contact.*form',
                html, re.I))

            # WhatsApp Business
            r["has_whatsapp"] = bool(re.search(
                r'wa\.me/|api\.whatsapp\.com|whatsapp\.com/send|whatsapp-chat',
                html, re.I))

            # TikTok linki
            m = re.search(r'tiktok\.com/@([a-zA-Z0-9_.]{2,30})', html)
            if m:
                r["tiktok_url"] = f"https://www.tiktok.com/@{m.group(1)}"

            # robots.txt
            try:
                base = re.match(r'https?://[^/]+', url).group(0)
                rb = await client.get(f"{base}/robots.txt", timeout=4)
                r["has_robots"] = rb.status_code == 200 and len(rb.text) > 10
            except:
                pass

            # sitemap.xml
            try:
                sm = await client.get(f"{base}/sitemap.xml", timeout=4)
                r["has_sitemap"] = sm.status_code == 200 and 'xml' in sm.headers.get('content-type','')
            except:
                pass

    except Exception:
        pass

    return r

# ── TikTok bul ─────────────────────────────────────────
async def find_tiktok(page, business_name: str, website_data: dict) -> dict:
    result = {"has_tiktok": False, "tiktok_url": None, "tiktok_username": None}

    # 1. Website'te link varsa al
    if website_data.get("tiktok_url"):
        m = re.search(r'tiktok\.com/@([a-zA-Z0-9_.]{2,30})', website_data["tiktok_url"])
        if m:
            result.update(has_tiktok=True, tiktok_url=website_data["tiktok_url"],
                          tiktok_username=m.group(1))
            console.print(f"    [green]✓ TikTok (site): @{m.group(1)}[/green]")
            return result

    # 2. Handle tahmin et
    clean = re.sub(r'[^a-z0-9\s]', '',
        business_name.lower()
        .replace('ı','i').replace('ğ','g').replace('ü','u')
        .replace('ş','s').replace('ö','o').replace('ç','c'))
    words = clean.split()
    candidates = [''.join(words), '_'.join(words), words[0] if words else '',
                  ''.join(words[:2]) if len(words) >= 2 else '']
    candidates = [c for c in set(candidates) if len(c) >= 3]

    async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
        hdrs = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)"}
        for u in candidates[:4]:
            try:
                resp = await client.get(f"https://www.tiktok.com/@{u}", headers=hdrs)
                # 200 ve profil sayfası
                if resp.status_code == 200 and '"uniqueId"' in resp.text:
                    result.update(has_tiktok=True,
                                  tiktok_url=f"https://www.tiktok.com/@{u}",
                                  tiktok_username=u)
                    console.print(f"    [green]✓ TikTok: @{u}[/green]")
                    return result
                await asyncio.sleep(0.3)
            except:
                continue

    return result

# ── Delivery platformları (restoran/cafe için) ─────────
async def check_delivery(page, business_name: str, sector: str) -> dict:
    result = {"has_yemeksepeti": False, "yemeksepeti_url": None,
              "has_getir": False, "getir_url": None}
    if sector not in ("restaurant", "cafe", "default"):
        return result

    q = business_name.replace(' ', '+')
    try:
        await page.goto(
            f"https://www.google.com/search?q={q}+yemeksepeti+getir",
            wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        content = await page.content()

        ys = re.findall(r'href="(https://www\.yemeksepeti\.com/[^"]+)"', content)
        if ys:
            result["has_yemeksepeti"] = True
            result["yemeksepeti_url"] = ys[0]
            console.print(f"    [green]✓ Yemeksepeti bulundu[/green]")

        gt = re.findall(r'href="(https://getir\.com/[^"]+)"', content)
        if not gt:
            gt = re.findall(r'(https://getir\.com/yemek/[^\s"\'<]+)', content)
        if gt:
            result["has_getir"] = True
            result["getir_url"] = gt[0]
            console.print(f"    [green]✓ Getir bulundu[/green]")

    except Exception as e:
        console.print(f"[yellow]Delivery kontrol hata: {e}[/yellow]")

    return result

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
    stats = {"followers": None, "following": None, "post_count": None,
             "avg_likes": None, "avg_comments": None, "engagement_rate": None}
    if not username:
        return stats
    try:
        content = ""
        body_text = ""

        async with httpx.AsyncClient(
            timeout=8,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Version/16.0 Mobile/15E148 Safari/604.1"},
        ) as client:
            resp = await client.get(f"https://www.instagram.com/{username}/")
            if resp.status_code == 200:
                content = resp.text

        await page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3500)
        if not content:
            content = await page.content()
        body_text = await page.locator("body").inner_text()

        for pattern, key in [
            (r'([\d,\.]+[KkMm]?)\s+[Ff]ollowers?', "followers"),
            (r'([\d,\.]+[KkMm]?)\s+[Ff]ollowing', "following"),
            (r'([\d,\.]+[KkMm]?)\s+[Pp]osts?', "post_count"),
        ]:
            m = re.search(pattern, content)
            if m:
                stats[key] = _parse_ig_num(m.group(1))
        if stats["followers"] is None:
            m = re.search(r'content="([\d,\.]+)\s+Followers,\s+([\d,\.]+)\s+Following,\s+([\d,\.]+)\s+Posts', content, re.I)
            if m:
                stats["followers"] = _parse_ig_num(m.group(1))
                stats["following"] = _parse_ig_num(m.group(2))
                stats["post_count"] = _parse_ig_num(m.group(3))
        if stats["followers"] is None:
            for pattern, key in [
                (r'([\d,\.]+[KkMm]?)\s+followers', "followers"),
                (r'([\d,\.]+[KkMm]?)\s+following', "following"),
                (r'([\d,\.]+[KkMm]?)\s+posts', "post_count"),
            ]:
                m = re.search(pattern, body_text, re.I)
                if m and stats[key] is None:
                    stats[key] = _parse_ig_num(m.group(1))

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

# ── Skor (genişletilmiş) ───────────────────────────────
def compute_score(website, instagram, ig_stats=None, tiktok=None, maps_data=None, sector="default"):
    score, issues, opportunities = 0, [], []

    # ── Web varlığı (maks 55) ──────────────────────────
    if website["has_website"]:
        score += 20
        if website["has_ssl"]:
            score += 8
        else:
            issues.append("SSL yok")
            opportunities.append("SSL kurulumu")
        if website["is_mobile_friendly"]:
            score += 7
        else:
            issues.append("Mobil uyumsuz")
            opportunities.append("Mobil tasarım")
        if website.get("load_time_ms") and website["load_time_ms"] > 3000:
            issues.append(f"Site yavaş ({website['load_time_ms']}ms)")
            opportunities.append("Site hız optimizasyonu")
        else:
            score += 4
        if website.get("has_schema"):
            score += 4
        else:
            issues.append("Schema.org yok")
            opportunities.append("Google SEO yapılandırması")
        if website.get("has_og"):
            score += 3
        else:
            opportunities.append("Sosyal paylaşım meta etiketleri")
        if website.get("has_email_capture"):
            score += 4
        else:
            opportunities.append("E-posta toplama formu")
        if website.get("has_whatsapp"):
            score += 5
        else:
            issues.append("WhatsApp butonu yok")
            opportunities.append("WhatsApp Business entegrasyonu")
    else:
        issues.append("Web sitesi yok")
        opportunities.append("Web sitesi tasarımı")

    # ── Sosyal medya (maks 28) ─────────────────────────
    if instagram["has_instagram"]:
        score += 12
        if ig_stats:
            er = ig_stats.get("engagement_rate")
            followers = ig_stats.get("followers")
            if er is not None:
                if er >= 3:
                    score += 8
                elif er >= 1:
                    score += 4
                else:
                    issues.append(f"Düşük etkileşim (%{er})")
                    opportunities.append("İçerik stratejisi & etkileşim artırma")
            if followers is not None and followers >= 500:
                score += 4
            elif followers is not None:
                issues.append(f"Az takipçi ({followers})")
                opportunities.append("Takipçi büyüme kampanyası")
    else:
        issues.append("Instagram yok")
        opportunities.append("Instagram yönetimi")

    if tiktok and tiktok.get("has_tiktok"):
        score += 4
    else:
        opportunities.append("TikTok hesabı açılması")

    # ── Yerel güven (maks 12) ──────────────────────────
    if maps_data:
        rating = maps_data.get("rating")
        review_count = maps_data.get("review_count")
        if rating is not None:
            if rating >= 4.0:
                score += 6
            elif rating >= 3.5:
                score += 3
            else:
                issues.append(f"Google puanı düşük ({rating})")
                opportunities.append("Google yorumları yönetimi")
        if review_count is not None and review_count >= 100:
            score += 6
        elif review_count is not None and review_count >= 20:
            score += 3
        elif review_count is not None:
            issues.append(f"Az Google yorumu ({review_count})")
            opportunities.append("Yorum artırma kampanyası")

    # ── Delivery (restoran/cafe için maks 5) ───────────
    if sector in ("restaurant", "cafe"):
        delivery = maps_data.get("delivery") if maps_data else None
        has_ys = delivery and delivery.get("has_yemeksepeti") if delivery else False
        has_gt = delivery and delivery.get("has_getir") if delivery else False
        if has_ys or has_gt:
            score += 5
        else:
            issues.append("Online sipariş platformu yok")
            opportunities.append("Yemeksepeti / Getir entegrasyonu")

    score = min(score, 100)
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
                maps_data = await find_from_google_maps(page, lead["maps_url"], name, lead.get("city"))
                console.print(f"     Web: {maps_data.get('website_url','—')}")
                console.print(f"     Tel: {maps_data.get('phone','—')}")
                console.print(f"     Puan: {maps_data.get('rating','—')} ({maps_data.get('review_count','?')} yorum)")
                console.print(f"     Kategori: {maps_data.get('category','—')}")

            sector = detect_sector(maps_data.get("category"))
            website = await check_website(maps_data.get("website_url"))

            console.print(f"  🌐 Schema:{website['has_schema']} OG:{website['has_og']} WA:{website['has_whatsapp']}")

            console.print("  📸 Instagram...")
            instagram = await find_instagram(page, name, maps_data.get("website_url"))

            ig_stats = {}
            if instagram["has_instagram"] and instagram.get("instagram_username"):
                ig_stats = await get_instagram_stats(page, instagram["instagram_username"])

            console.print("  🎵 TikTok...")
            tiktok = await find_tiktok(page, name, website)

            delivery = {}
            if sector in ("restaurant", "cafe"):
                console.print("  🛵 Delivery...")
                delivery = await check_delivery(page, name, sector)

            maps_data["delivery"] = delivery

            scoring = compute_score(website, instagram, ig_stats, tiktok, maps_data, sector)

            results.append({
                **lead,
                "sector": sector,
                "phone":   maps_data.get("phone"),
                "address": maps_data.get("address"),
                "rating":  maps_data.get("rating"),
                "review_count": maps_data.get("review_count"),
                "category": maps_data.get("category"),
                "website": website,
                "social":  {**instagram, "stats": ig_stats, "tiktok": tiktok},
                "delivery": delivery,
                "scoring": scoring,
            })
            await asyncio.sleep(1)

        await browser.close()

    with open("leads_audited.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    console.print(f"\n[bold green]✅ {len(results)} lead audit edildi → leads_audited.json[/bold green]")

if __name__ == "__main__":
    asyncio.run(audit_all())
