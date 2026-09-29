from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from src.net_security import assert_safe_public_url


def _text(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def _same_domain(base: str, href: str) -> bool:
    try:
        return urlparse(base).netloc == urlparse(urljoin(base, href)).netloc
    except Exception:
        return False


def research_website(url: str | None, *, max_links: int = 8) -> dict:
    empty = {
        "status": "missing",
        "url": url,
        "title": None,
        "meta_description": None,
        "headings": [],
        "internal_links": [],
        "contact_signals": [],
        "emails": [],
        "content_sample": None,
    }
    if not url:
        return empty

    try:
        url = assert_safe_public_url(url)
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            for _ in range(7):
                safe_url = assert_safe_public_url(url)
                with client.stream(
                    "GET",
                    safe_url,
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("redirect without location")
                        url = urljoin(safe_url, location)
                        continue
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        if len(content) + len(chunk) > 2_000_000:
                            raise ValueError("website content is too large")
                        content.extend(chunk)
                    encoding = response.charset_encoding or "utf-8"
                    html = bytes(content).decode(encoding, errors="replace")
                    final_url = str(response.url)
                    break
            else:
                raise ValueError("too many redirects")
    except Exception as exc:
        return {**empty, "status": "error", "error": str(exc)[:160]}

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = _text(soup.title) if soup.title else None
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    meta_description = meta.get("content", "").strip() if meta else None
    headings = [_text(h) for h in soup.find_all(["h1", "h2"])[:8]]
    links = []
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        label = _text(a)
        if not href or not label or not _same_domain(url, href):
            continue
        full = urljoin(url, href)
        if full not in [item["url"] for item in links]:
            links.append({"label": label[:80], "url": full})
        if len(links) >= max_links:
            break

    raw_text = _text(soup)
    lower = raw_text.lower()
    contact_signals = []
    emails = sorted(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", raw_text, re.I)))[:5]
    for label, pattern in {
        "phone": r"(\+90|0)\s?\d{3}[\s)-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}",
        "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
        "reservation": r"rezervasyon|reservation|randevu",
        "delivery": r"yemeksepeti|getir|paket servis|online sipariş",
        "whatsapp": r"whatsapp|wa\.me",
    }.items():
        if re.search(pattern, lower, re.I):
            contact_signals.append(label)

    return {
        "status": "ok",
        "url": final_url,
        "title": title,
        "meta_description": meta_description,
        "headings": [h for h in headings if h][:8],
        "internal_links": links,
        "contact_signals": contact_signals,
        "emails": emails,
        "content_sample": raw_text[:1200] if raw_text else None,
    }


def enrich_research(lead: dict) -> dict:
    enriched = dict(lead)
    website = lead.get("website") or {}
    enriched["research"] = {
        "website": research_website(website.get("website_url")),
    }
    return enriched
