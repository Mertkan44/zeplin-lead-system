import asyncio
import html
import json
import re
import httpx
import unicodedata
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse
from playwright.async_api import async_playwright
from rich.console import Console
from src.audit.website import _fetch_public, audit_website

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


def _entity_tokens(value: str | None) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold().replace("ı", "i")
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) > 1 and token not in {"ve", "the", "at", "istanbul"}
    }


def _entity_similarity(expected: str | None, observed: str | None) -> int:
    expected_tokens = _entity_tokens(expected)
    observed_tokens = _entity_tokens(observed)
    if not expected_tokens or not observed_tokens:
        return 0
    intersection = len(expected_tokens & observed_tokens)
    union = len(expected_tokens | observed_tokens)
    containment = intersection / max(1, min(len(expected_tokens), len(observed_tokens)))
    jaccard = intersection / max(1, union)
    return round(max(containment * 90, jaccard * 100))


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
        if result["review_count"] is None:
            review_match = re.search(r"\(([\d.,\s]+)\)|([\d.,\s]+)\s*(?:yorum|reviews?)", line, re.I)
            if review_match:
                raw_reviews = (review_match.group(1) or review_match.group(2) or "").replace(".", "").replace(",", "").replace(" ", "")
                if raw_reviews.isdigit():
                    result["review_count"] = int(raw_reviews)
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
        "source_status": "unknown",
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "identity_name": None,
        "identity_confidence": 0,
        "website_lookup_status": "unknown",
        "phone_lookup_status": "unknown",
        "address_lookup_status": "unknown",
        "rating_lookup_status": "unknown",
        "review_count_lookup_status": "unknown",
    }
    try:
        await page.goto(maps_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        result["source_status"] = "ok"

        for sel in ["h1.DUwDvf", "h1", '[role="main"] h1']:
            heading = await page.query_selector(sel)
            if heading:
                identity_name = (await heading.inner_text()).strip()
                if identity_name:
                    result["identity_name"] = identity_name
                    result["identity_confidence"] = _entity_similarity(business_name, identity_name)
                    break

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
                    result["website_lookup_status"] = "found"
                    break
        if result["website_lookup_status"] != "found" and result["identity_confidence"] >= 70:
            result["website_lookup_status"] = "not_found"

        # Telefon
        for sel in ['button[data-item-id*="phone:"]', 'button[data-item-id*="phone"]']:
            phone_el = await page.query_selector(sel)
            if phone_el:
                label = await phone_el.get_attribute("aria-label") or ""
                phone = re.sub(r'^[^:]+:\s*', '', label).strip()
                if phone:
                    result["phone"] = phone
                    result["phone_lookup_status"] = "found"
                break
        if result["phone_lookup_status"] != "found" and result["identity_confidence"] >= 70:
            result["phone_lookup_status"] = "not_found"

        # Adres
        for sel in ['button[data-item-id="address"]', 'button[aria-label*="Adres"]', '[data-item-id="address"]']:
            addr_el = await page.query_selector(sel)
            if addr_el:
                label = await addr_el.get_attribute("aria-label") or ""
                addr = re.sub(r'^[^:]+:\s*', '', label).strip()
                if addr:
                    result["address"] = addr
                    result["address_lookup_status"] = "found"
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
        if result["address"]:
            result["address_lookup_status"] = "found"
        elif result["identity_confidence"] >= 70:
            result["address_lookup_status"] = "not_found"

        # Rating — aria-label "4,5 yıldız" veya "4.5 stars" formatı
        for sel in ['span[aria-label*="yıldız"]', 'span[aria-label*="star"]', 'div[aria-label*="yıldız"]']:
            el = await page.query_selector(sel)
            if el:
                label = await el.get_attribute("aria-label") or ""
                m = re.search(r'([\d][,.][\d])', label)
                if m:
                    result["rating"] = float(m.group(1).replace(',', '.'))
                    result["rating_lookup_status"] = "found"
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
        if result["rating"] is not None:
            result["rating_lookup_status"] = "found"

        # Yorum sayısı yalnızca seçili işletme panelindeki etiketlerden okunur.
        # Sayfanın tamamındaki "yorum yok" metni başka kartlara ait olabilir.
        for selector in [
            'button[jsaction*="pane.reviewChart.moreReviews"]',
            'button[aria-label*="yorum"]',
            'button[aria-label*="review"]',
        ]:
            for element in await page.query_selector_all(selector):
                label = " ".join(
                    part
                    for part in [
                        await element.get_attribute("aria-label") or "",
                        (await element.inner_text()).strip(),
                    ]
                    if part
                )
                match = re.search(r"([\d.,\s]+)\s*(?:yorum|reviews?)", label, re.I)
                if not match:
                    continue
                raw = re.sub(r"\D", "", match.group(1))
                if raw:
                    result["review_count"] = int(raw)
                    result["review_count_lookup_status"] = "found"
                    break
            if result["review_count"] is not None:
                break
        if result["review_count"] is None and result["identity_confidence"] >= 70:
            result["review_count_lookup_status"] = "not_parsed"

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
        result["source_status"] = "error"
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
    if result.get("review_count") is not None:
        result["review_count_lookup_status"] = "found"
    if result.get("rating") is not None:
        result["rating_lookup_status"] = "found"
    if result.get("phone"):
        result["phone_lookup_status"] = "found"
    if result.get("address"):
        result["address_lookup_status"] = "found"

    return result

# ── Web sitesi kontrol ─────────────────────────────────
async def check_website(
    url: str | None,
    *,
    lookup_status: str = "unknown",
    check_links: bool = True,
) -> dict:
    return await audit_website(
        url,
        lookup_status=lookup_status,
        check_links=check_links,
    )

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

    async with httpx.AsyncClient(timeout=6, follow_redirects=False, trust_env=False) as client:
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
def _instagram_identity_score(
    business_name: str,
    username: str,
    profile_content: str,
    website_url: str | None,
) -> tuple[int, str]:
    snippets = []
    for pattern in [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
        r'"full_name"\s*:\s*"([^"]+)"',
        r'"biography"\s*:\s*"([^"]+)"',
    ]:
        snippets.extend(re.findall(pattern, profile_content, re.I))
    observed = html.unescape(" ".join(snippets))
    expected_tokens = _entity_tokens(business_name)
    observed_tokens = _entity_tokens(f"{username} {observed}")
    if not expected_tokens or not observed_tokens:
        return 0, "profile metadata could not be matched"
    overlap = expected_tokens & observed_tokens
    coverage = len(overlap) / len(expected_tokens)
    precision = len(overlap) / max(1, min(len(observed_tokens), len(expected_tokens) + 2))
    score = round((coverage * 0.75 + precision * 0.25) * 100)

    if website_url:
        website_host = (urlparse(website_url).hostname or "").removeprefix("www.")
        if website_host and website_host in profile_content:
            return max(score, 95), f"profile links to {website_host}"
    return score, f"profile metadata matched {len(overlap)}/{len(expected_tokens)} business-name tokens"


async def find_instagram(page, business_name: str, website_url: str = None) -> dict:
    result = {
        "has_instagram": None,
        "instagram_url": None,
        "instagram_username": None,
        "lookup_status": "unknown",
        "identity_confidence": 0,
        "identity_evidence": None,
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    bl = {"p","reel","explore","stories","accounts","about","legal","help","press","api","sharer"}

    if website_url:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as website_client:
                website_content = (await _fetch_public(website_client, website_url))["text"]
            for m in re.findall(r'instagram\.com/([a-zA-Z0-9_.]{2,30})/?', website_content):
                if m not in bl:
                    result.update(has_instagram=True,
                                  instagram_url=f"https://www.instagram.com/{m}/",
                                  instagram_username=m,
                                  lookup_status="found",
                                  identity_confidence=98,
                                  identity_evidence="Instagram linki işletmenin websitesinde bulundu.")
                    return result
        except:
            pass

    clean = re.sub(r'[^a-z0-9\s]', '',
        business_name.lower()
        .replace('ı','i').replace('ğ','g').replace('ü','u')
        .replace('ş','s').replace('ö','o').replace('ç','c'))
    words = clean.split()
    guessed_candidates = [''.join(words), '.'.join(words), '_'.join(words),
                          words[0] if words else '',
                          ''.join(words[:2]) if len(words) >= 2 else '']
    guessed_candidates = list(dict.fromkeys(c for c in guessed_candidates if len(c) >= 3))

    async with httpx.AsyncClient(timeout=6, follow_redirects=False, trust_env=False) as client:
        hdrs = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)"}
        searched_candidates: list[tuple[str, str]] = []
        try:
            await page.goto(
                f"https://www.google.com/search?q={quote_plus(business_name + ' instagram')}",
                wait_until="domcontentloaded")
            await page.wait_for_timeout(2200)
            search_content = await page.content()
            for username in re.findall(r'instagram\.com/([a-zA-Z0-9_.]{2,30})/?', search_content):
                if username not in bl and username not in [item[0] for item in searched_candidates]:
                    searched_candidates.append((username, "Google arama sonucu"))
        except Exception:
            search_content = ""

        for username in guessed_candidates:
            if username not in [item[0] for item in searched_candidates]:
                searched_candidates.append((username, "İşletme adından türetilen aday"))

        checked = 0
        blocked = 0
        for u, candidate_source in searched_candidates[:8]:
            try:
                resp = await client.get(f"https://www.instagram.com/{u}/", headers=hdrs)
                checked += 1
                if resp.status_code in {401, 403, 429}:
                    blocked += 1
                    continue
                if resp.status_code == 200 and (
                    '"@type":"ProfilePage"' in resp.text or 'property="og:title"' in resp.text
                ):
                    identity_score, identity_evidence = _instagram_identity_score(
                        business_name,
                        u,
                        resp.text,
                        website_url,
                    )
                    if identity_score < 70:
                        continue
                    result.update(has_instagram=True,
                                  instagram_url=f"https://www.instagram.com/{u}/",
                                  instagram_username=u,
                                  lookup_status="found",
                                  identity_confidence=identity_score,
                                  identity_evidence=f"{candidate_source}; {identity_evidence}.")
                    console.print(f"    [green]✓ Instagram: @{u}[/green]")
                    return result
                await asyncio.sleep(0.4)
            except:
                continue
        if checked and blocked == checked:
            result["lookup_status"] = "blocked"
        elif checked:
            result["lookup_status"] = "not_found"
            result["has_instagram"] = False

    return result

# ── Instagram istatistikleri ───────────────────────────
def _parse_ig_num(s: str) -> int | None:
    s = s.strip().upper().replace(" ", "")
    try:
        if s.endswith("M"):
            return int(float(s[:-1].replace(",", ".")) * 1_000_000)
        if s.endswith("K"):
            return int(float(s[:-1].replace(",", ".")) * 1_000)
        return int(s.replace(".", "").replace(",", ""))
    except:
        return None

async def get_instagram_stats(page, username: str) -> dict:
    stats = {"followers": None, "following": None, "post_count": None,
             "avg_likes": None, "avg_comments": None, "engagement_rate": None,
             "lookup_status": "not_checked", "engagement_sample_size": 0,
             "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    if not username:
        return stats
    try:
        content = ""
        body_text = ""

        async with httpx.AsyncClient(
            timeout=8,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Version/16.0 Mobile/15E148 Safari/604.1"},
        ) as client:
            resp = await client.get(f"https://www.instagram.com/{username}/")
            if resp.status_code == 200:
                content = resp.text
            elif resp.status_code in {401, 403, 429}:
                stats["lookup_status"] = "blocked"

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
        stats["engagement_sample_size"] = max(len(likes), len(comments))

        if likes:
            stats["avg_likes"] = round(sum(likes) / len(likes))
        if comments:
            stats["avg_comments"] = round(sum(comments) / len(comments))

        followers = stats["followers"]
        if followers and followers > 0 and stats["avg_likes"] is not None:
            avg_l = stats["avg_likes"] or 0
            avg_c = stats["avg_comments"] or 0
            stats["engagement_rate"] = round((avg_l + avg_c) / followers * 100, 2)
        if any(stats.get(key) is not None for key in ("followers", "post_count", "avg_likes")):
            stats["lookup_status"] = "found"
        elif stats["lookup_status"] == "not_checked":
            stats["lookup_status"] = "unavailable"

        console.print(
            f"    📊 {followers or '?'} takipçi | "
            f"ort. {stats['avg_likes'] or '?'} beğeni | "
            f"%{stats['engagement_rate'] or '?'} etkileşim"
        )
    except Exception as e:
        stats["lookup_status"] = "error"
        console.print(f"[red]Instagram stats hata: {e}[/red]")

    return stats

# ── Skor (genişletilmiş) ───────────────────────────────
def compute_score(website, instagram, ig_stats=None, tiktok=None, maps_data=None, sector="default"):
    from src.audit.findings import analyze_lead

    maps_data = maps_data or {}
    lead = {
        "sector": sector,
        "rating": maps_data.get("rating"),
        "review_count": maps_data.get("review_count"),
        "maps_url": maps_data.get("maps_url"),
        "maps": maps_data,
        "website": website or {},
        "social": {
            **(instagram or {}),
            "stats": ig_stats or {},
            "tiktok": tiktok or {},
        },
    }
    return analyze_lead(lead)["scoring"]

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
            website = await check_website(
                maps_data.get("website_url"),
                lookup_status=maps_data.get("website_lookup_status") or "unknown",
            )

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

            from scripts.migrate_leads import normalize_lead

            results.append(normalize_lead({
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
                "maps": maps_data,
                "scoring": {},
            }))
            await asyncio.sleep(1)

        await browser.close()

    with open("leads_audited.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    console.print(f"\n[bold green]✅ {len(results)} lead audit edildi → leads_audited.json[/bold green]")

if __name__ == "__main__":
    asyncio.run(audit_all())
