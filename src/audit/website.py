from __future__ import annotations

import asyncio
import json
import re
import statistics
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.net_security import assert_safe_public_url


AUDIT_VERSION = 4
MAX_HTML_BYTES = 2_000_000
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
NON_WEBSITE_HOSTS = {
    "wa.me",
    "api.whatsapp.com",
    "web.whatsapp.com",
    "instagram.com",
    "www.instagram.com",
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "tiktok.com",
    "www.tiktok.com",
    "linktr.ee",
}
LOCAL_SCHEMA_TYPES = {
    "LocalBusiness",
    "Organization",
    "Restaurant",
    "CafeOrCoffeeShop",
    "Store",
    "MedicalBusiness",
    "Dentist",
    "HealthAndBeautyBusiness",
    "AutomotiveBusiness",
    "ProfessionalService",
}


def _checked_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _empty_website(
    url: str | None,
    *,
    lookup_status: str = "unknown",
    status: str = "missing",
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "audit_version": AUDIT_VERSION,
        "audit_status": status,
        "lookup_status": lookup_status,
        "checked_at": _checked_at(),
        "has_website": False if status in {"missing", "invalid_candidate"} else None,
        "website_url": url,
        "final_url": None,
        "candidate_kind": "unknown",
        "placeholder_detected": None,
        "placeholder_reason": None,
        "website_loads": None,
        "http_status": None,
        "content_type": None,
        "redirect_count": 0,
        "redirect_chain": [],
        "has_ssl": None,
        "is_mobile_friendly": None,
        "load_time_ms": None,
        "response_time_samples_ms": [],
        "performance_status": "not_checked",
        "html_bytes": None,
        "title": None,
        "title_length": None,
        "meta_description": None,
        "meta_description_length": None,
        "h1_count": None,
        "h1_texts": [],
        "word_count": None,
        "language": None,
        "canonical_url": None,
        "has_canonical": None,
        "is_indexable": None,
        "noindex_reason": None,
        "has_schema": None,
        "schema_status": "not_checked",
        "schema_types": [],
        "schema_names": [],
        "schema_fields": [],
        "schema_block_count": 0,
        "schema_invalid_count": 0,
        "has_local_business_schema": None,
        "has_og": None,
        "og_fields": [],
        "og_missing_fields": [],
        "has_robots": None,
        "robots_status": "not_checked",
        "robots_blocks_site": None,
        "has_sitemap": None,
        "sitemap_status": "not_checked",
        "has_email_capture": None,
        "has_contact_form": None,
        "has_phone_link": None,
        "has_whatsapp": None,
        "has_reservation_signal": None,
        "has_order_signal": None,
        "has_analytics": None,
        "has_google_tracking": None,
        "has_meta_pixel": None,
        "has_google_ads_tag": None,
        "has_conversion_tracking": None,
        "has_chat_widget": None,
        "has_bot_signal": None,
        "chat_providers": [],
        "has_video_content": None,
        "video_embed_count": None,
        "video_platforms": [],
        "phone_numbers": [],
        "emails": [],
        "contact_page_urls": [],
        "menu_page_urls": [],
        "booking_urls": [],
        "instagram_links": [],
        "facebook_links": [],
        "tiktok_url": None,
        "image_count": None,
        "images_with_alt": None,
        "image_alt_coverage": None,
        "form_control_count": None,
        "labeled_form_control_count": None,
        "form_label_coverage": None,
        "internal_links_checked": 0,
        "broken_internal_links": [],
        "error": error,
    }


def _candidate_kind(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in NON_WEBSITE_HOSTS:
        return "social_or_messaging"
    if parsed.path.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".webp")):
        return "document_or_media"
    return "website"


async def _fetch_public(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int = MAX_HTML_BYTES,
    max_redirects: int = 6,
) -> dict[str, Any]:
    current = assert_safe_public_url(url)
    redirects: list[str] = []
    started = time.perf_counter()

    for _ in range(max_redirects + 1):
        assert_safe_public_url(current)
        async with client.stream("GET", current, follow_redirects=False) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    break
                next_url = assert_safe_public_url(urljoin(current, location))
                redirects.append(next_url)
                current = next_url
                continue

            content = bytearray()
            async for chunk in response.aiter_bytes():
                remaining = max_bytes - len(content)
                if remaining <= 0:
                    break
                content.extend(chunk[:remaining])
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            encoding = response.charset_encoding or "utf-8"
            try:
                text = bytes(content).decode(encoding, errors="replace")
            except LookupError:
                text = bytes(content).decode("utf-8", errors="replace")
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content": bytes(content),
                "text": text,
                "elapsed_ms": elapsed_ms,
                "final_url": current,
                "redirects": redirects,
            }

    raise RuntimeError("too many redirects")


def _schema_details(
    soup: BeautifulSoup,
) -> tuple[list[str], list[str], list[str], int, int]:
    types: list[str] = []
    names: list[str] = []
    fields: list[str] = []
    blocks = soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)})
    invalid = 0

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        raw_type = value.get("@type")
        if isinstance(raw_type, str):
            types.append(raw_type)
        elif isinstance(raw_type, list):
            types.extend(str(item) for item in raw_type if item)
        if value.get("name"):
            names.append(str(value["name"]))
        for key in (
            "url",
            "telephone",
            "email",
            "address",
            "openingHours",
            "openingHoursSpecification",
            "priceRange",
            "sameAs",
            "image",
            "logo",
        ):
            if value.get(key) is not None:
                fields.append(key)
        graph = value.get("@graph")
        if graph is not None:
            walk(graph)

    for block in blocks:
        try:
            payload = json.loads(block.string or block.get_text() or "")
            walk(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            invalid += 1
    return (
        list(dict.fromkeys(types)),
        list(dict.fromkeys(names)),
        list(dict.fromkeys(fields)),
        len(blocks),
        invalid,
    )


def _normalize_phone(value: str) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("90") and len(digits) >= 12:
        digits = digits[-10:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def _robots_blocks_all(robots_text: str) -> bool:
    """Return true only when a universal user-agent group blocks the root path."""
    applies_to_all = False
    directives_started = False
    for raw_line in (robots_text or "").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.casefold()
        if key == "user-agent":
            if directives_started:
                applies_to_all = False
                directives_started = False
            applies_to_all = applies_to_all or value == "*"
            continue
        if key in {"allow", "disallow"}:
            directives_started = True
            if applies_to_all and key == "disallow" and value == "/":
                return True
    return False


def _same_host(base: str, candidate: str) -> bool:
    try:
        return (urlparse(base).hostname or "").removeprefix("www.") == (
            urlparse(candidate).hostname or ""
        ).removeprefix("www.")
    except Exception:
        return False


def _social_links(soup: BeautifulSoup, host: str) -> list[str]:
    values: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin("https://example.invalid", str(anchor.get("href") or ""))
        parsed = urlparse(href)
        normalized_host = (parsed.hostname or "").lower()
        if normalized_host == host or normalized_host == f"www.{host}":
            clean = href.split("?", 1)[0]
            if clean not in values:
                values.append(clean)
    return values[:6]


def _form_label_coverage(soup: BeautifulSoup) -> tuple[int, int, float | None]:
    controls = [
        control
        for control in soup.find_all(["input", "select", "textarea"])
        if str(control.get("type") or "").lower() not in {"hidden", "submit", "button", "reset"}
    ]
    if not controls:
        return 0, 0, None
    label_for = {
        str(label.get("for"))
        for label in soup.find_all("label", attrs={"for": True})
        if label.get("for")
    }
    labeled = 0
    for control in controls:
        control_id = str(control.get("id") or "")
        parent_label = control.find_parent("label")
        if (
            (control_id and control_id in label_for)
            or parent_label is not None
            or control.get("aria-label")
            or control.get("aria-labelledby")
        ):
            labeled += 1
    return len(controls), labeled, round(labeled / len(controls) * 100, 1)


async def _check_internal_links(
    client: httpx.AsyncClient,
    base_url: str,
    soup: BeautifulSoup,
    *,
    limit: int = 6,
) -> tuple[int, list[dict[str, Any]]]:
    urls: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        candidate = urljoin(base_url, href).split("#", 1)[0]
        candidate_path = (urlparse(candidate).path or "").casefold()
        if candidate_path.startswith("/cdn-cgi/"):
            # Cloudflare's email decoder is infrastructure, not a user-facing page.
            continue
        if not _same_host(base_url, candidate) or candidate in urls:
            continue
        urls.append(candidate)
        if len(urls) >= limit:
            break

    async def check(url: str) -> dict[str, Any] | None:
        try:
            response = await _fetch_public(client, url, max_bytes=1, max_redirects=4)
            status = int(response["status_code"])
            if status >= 400 and status not in {401, 403, 429}:
                return {"url": url, "status": status}
        except Exception as exc:
            return {"url": url, "status": None, "error": str(exc)[:100]}
        return None

    results = await asyncio.gather(*(check(url) for url in urls))
    return len(urls), [item for item in results if item is not None]


async def audit_website(
    url: str | None,
    *,
    lookup_status: str = "unknown",
    check_links: bool = True,
) -> dict[str, Any]:
    if not url:
        return _empty_website(url, lookup_status=lookup_status, status="missing")

    kind = _candidate_kind(url)
    if kind != "website":
        result = _empty_website(
            url,
            lookup_status=lookup_status,
            status="invalid_candidate",
            error="Maps website field points to a social, messaging, or media URL.",
        )
        result["candidate_kind"] = kind
        return result

    try:
        safe_url = assert_safe_public_url(url)
    except ValueError as exc:
        error = str(exc)[:160]
        status = "invalid_candidate" if "only public http/https" in error else "unreachable"
        result = _empty_website(
            url,
            lookup_status=lookup_status,
            status=status,
            error=error,
        )
        result["candidate_kind"] = _candidate_kind(url)
        return result

    result = _empty_website(
        safe_url,
        lookup_status=lookup_status,
        status="unknown",
    )
    result["candidate_kind"] = kind
    timeout = httpx.Timeout(20, connect=10)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}

    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers, trust_env=False) as client:
            page = await _fetch_public(client, safe_url)
            result["http_status"] = page["status_code"]
            result["content_type"] = page["headers"].get("content-type")
            result["redirect_chain"] = page["redirects"]
            result["redirect_count"] = len(page["redirects"])
            result["final_url"] = page["final_url"]
            result["website_url"] = page["final_url"]
            result["has_ssl"] = page["final_url"].startswith("https://")
            result["load_time_ms"] = page["elapsed_ms"]
            result["response_time_samples_ms"] = [page["elapsed_ms"]]
            result["html_bytes"] = len(page["content"])

            status_code = int(page["status_code"])
            if status_code in {401, 403, 429}:
                result["audit_status"] = "blocked"
                result["website_loads"] = None
                result["has_website"] = None
                result["performance_status"] = "not_checked"
                return result
            if status_code >= 500:
                result["audit_status"] = "server_error"
                result["website_loads"] = False
                result["has_website"] = None
                return result
            if status_code >= 400:
                result["audit_status"] = "http_error"
                result["website_loads"] = False
                result["has_website"] = None
                return result
            if "html" not in (result["content_type"] or "").lower() and "<html" not in page["text"][:1000].lower():
                result["audit_status"] = "non_html"
                result["website_loads"] = False
                result["has_website"] = None
                return result

            result["audit_status"] = "ok"
            result["website_loads"] = True
            result["has_website"] = True

            try:
                sample = await _fetch_public(client, page["final_url"], max_bytes=1)
                result["response_time_samples_ms"].append(sample["elapsed_ms"])
            except Exception:
                pass
            samples = result["response_time_samples_ms"]
            if len(samples) >= 2:
                result["load_time_ms"] = round(statistics.median(samples))
                result["performance_status"] = "origin_response_sample"

            soup = BeautifulSoup(page["text"], "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else None
            result["title"] = title or None
            result["title_length"] = len(title) if title else 0
            viewport = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
            viewport_content = str(viewport.get("content") or "").lower() if viewport else ""
            result["is_mobile_friendly"] = bool(
                viewport and ("width=device-width" in viewport_content or "initial-scale" in viewport_content)
            )

            placeholder_patterns = {
                "Default nginx page": r"\bwelcome to nginx\b",
                "Default Apache page": r"\bapache2? (?:ubuntu )?default page\b|\bit works!\b",
                "Domain parking page": r"\bdomain (?:is )?(?:parked|for sale)\b|buy this domain",
                "Coming soon page": r"\bcoming soon\b|\byapım aşamasında\b|\byakında\b",
                "Hosting setup page": r"\bwebsite is under construction\b|\bsite is being configured\b",
            }
            early_text = BeautifulSoup(page["text"][:120_000], "html.parser").get_text(" ", strip=True)
            provisional_word_count = len(
                re.findall(r"\b[\wÇĞİÖŞÜçğıöşü'-]+\b", early_text)
            )
            for reason, pattern in placeholder_patterns.items():
                title_match = re.search(pattern, title or "", re.I)
                body_match = provisional_word_count < 80 and re.search(pattern, early_text[:12000], re.I)
                if title_match or body_match:
                    result["placeholder_detected"] = True
                    result["placeholder_reason"] = reason
                    break
            if result["placeholder_detected"] is None:
                result["placeholder_detected"] = False

            meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
            description = str(meta.get("content") or "").strip() if meta else None
            result["meta_description"] = description or None
            result["meta_description_length"] = len(description) if description else 0

            h1_values = [
                " ".join(tag.get_text(" ", strip=True).split())
                for tag in soup.find_all("h1")
                if tag.get_text(" ", strip=True)
            ]
            result["h1_count"] = len(h1_values)
            result["h1_texts"] = h1_values[:4]
            result["language"] = (soup.html.get("lang") if soup.html else None) or None

            canonical = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
            canonical_url = urljoin(page["final_url"], str(canonical.get("href"))) if canonical and canonical.get("href") else None
            result["canonical_url"] = canonical_url
            result["has_canonical"] = bool(canonical_url)

            robots_meta = " ".join(
                str(tag.get("content") or "")
                for tag in soup.find_all("meta", attrs={"name": re.compile(r"robots|googlebot", re.I)})
            ).lower()
            x_robots = str(page["headers"].get("x-robots-tag") or "").lower()
            noindex = "noindex" in robots_meta or "noindex" in x_robots
            result["is_indexable"] = not noindex
            result["noindex_reason"] = "meta/x-robots noindex" if noindex else None

            (
                schema_types,
                schema_names,
                schema_fields,
                schema_blocks,
                invalid_schema,
            ) = _schema_details(soup)
            result["schema_types"] = schema_types
            result["schema_names"] = schema_names
            result["schema_fields"] = schema_fields
            result["schema_block_count"] = schema_blocks
            result["schema_invalid_count"] = invalid_schema
            result["has_schema"] = schema_blocks > 0 and invalid_schema < schema_blocks
            result["schema_status"] = (
                "missing"
                if schema_blocks == 0
                else "invalid"
                if invalid_schema == schema_blocks
                else "partial"
                if invalid_schema
                else "valid"
            )
            result["has_local_business_schema"] = bool(LOCAL_SCHEMA_TYPES.intersection(schema_types))

            og_fields = sorted(
                {
                    str(tag.get("property")).lower()
                    for tag in soup.find_all("meta", attrs={"property": re.compile(r"^og:", re.I)})
                    if tag.get("content")
                }
            )
            required_og = {"og:title", "og:description", "og:image", "og:url"}
            result["og_fields"] = og_fields
            result["og_missing_fields"] = sorted(required_og - set(og_fields))
            result["has_og"] = required_og.issubset(og_fields)

            raw_html = page["text"]
            lower_html = raw_html.lower()
            result["has_email_capture"] = bool(
                soup.find("input", attrs={"type": re.compile(r"email", re.I)})
            )
            result["has_contact_form"] = bool(soup.find("form")) and bool(
                re.search(r"iletişim|contact|mesaj|message|randevu|rezervasyon", soup.get_text(" ", strip=True), re.I)
            )
            result["has_phone_link"] = bool(soup.find("a", href=re.compile(r"^tel:", re.I)))
            result["has_whatsapp"] = bool(
                re.search(r"wa\.me/|api\.whatsapp\.com|whatsapp\.com/send", lower_html)
            )
            visible_text = " ".join(soup.get_text(" ", strip=True).split())
            result["has_reservation_signal"] = bool(
                re.search(r"\brezervasyon\b|\brandevu\b|\bbook(?:ing)?\b|\bappointment\b", visible_text, re.I)
            )
            result["has_order_signal"] = bool(
                re.search(r"online sipariş|sipariş ver|yemeksepeti|getir|trendyol yemek|order online", visible_text, re.I)
            )
            result["has_google_tracking"] = bool(
                re.search(
                    r"googletagmanager\.com|google-analytics\.com|gtag\(|"
                    r"\bG-[A-Z0-9]{6,}\b|\bUA-\d+-\d+\b",
                    raw_html,
                    re.I,
                )
            )
            result["has_meta_pixel"] = bool(
                re.search(
                    r"connect\.facebook\.net/.+fbevents|fbq\s*\(|"
                    r"facebook\.com/tr\?id=",
                    raw_html,
                    re.I,
                )
            )
            result["has_google_ads_tag"] = bool(
                re.search(
                    r"\bAW-\d{6,}\b|googleadservices\.com/pagead/conversion|"
                    r"googleads\.g\.doubleclick\.net",
                    raw_html,
                    re.I,
                )
            )
            result["has_conversion_tracking"] = bool(
                result["has_meta_pixel"] or result["has_google_ads_tag"]
            )
            result["has_analytics"] = bool(
                result["has_google_tracking"]
                or result["has_conversion_tracking"]
                or re.search(r"clarity\.ms/tag|hotjar", raw_html, re.I)
            )

            chat_markers = {
                "Tawk.to": r"tawk\.to|embed\.tawk\.to",
                "Intercom": r"intercom(?:cdn|assets)?\.com|intercomSettings",
                "Crisp": r"client\.crisp\.chat|CRISP_WEBSITE_ID",
                "LiveChat": r"cdn\.livechatinc\.com|__lc\.license",
                "JivoChat": r"jivosite\.com|jivochat",
                "Tidio": r"code\.tidio\.co|tidiochat",
                "Zendesk": r"static\.zendesk\.com|zopim",
                "HubSpot Chat": r"js\.usemessages\.com|hubspot.*conversations",
                "Chatwoot": r"chatwoot",
                "Kommunicate": r"kommunicate",
                "Botpress": r"botpress",
                "Dialogflow": r"dialogflow",
                "ManyChat": r"manychat",
                "Landbot": r"landbot",
                "Voiceflow": r"voiceflow",
            }
            result["chat_providers"] = [
                provider
                for provider, pattern in chat_markers.items()
                if re.search(pattern, raw_html, re.I)
            ]
            result["has_chat_widget"] = bool(result["chat_providers"])
            result["has_bot_signal"] = any(
                provider in {"Kommunicate", "Botpress", "Dialogflow", "ManyChat", "Landbot", "Voiceflow"}
                for provider in result["chat_providers"]
            )

            video_platform_patterns = {
                "HTML5 video": r"<video\b|type=[\"']video/",
                "YouTube": r"youtube(?:-nocookie)?\.com/embed|youtu\.be/",
                "Vimeo": r"player\.vimeo\.com/video",
                "Wistia": r"fast\.wistia\.(?:net|com)|wistia_embed",
                "Vidyard": r"play\.vidyard\.com|vidyardEmbed",
            }
            result["video_platforms"] = [
                platform
                for platform, pattern in video_platform_patterns.items()
                if re.search(pattern, raw_html, re.I)
            ]
            result["video_embed_count"] = (
                len(soup.find_all("video"))
                + len(
                    soup.find_all(
                        "iframe",
                        src=re.compile(
                            r"youtube(?:-nocookie)?\.com/embed|player\.vimeo\.com/video|"
                            r"fast\.wistia\.(?:net|com)|play\.vidyard\.com",
                            re.I,
                        ),
                    )
                )
            )
            result["has_video_content"] = bool(result["video_platforms"])

            phone_values: list[str] = []
            for anchor in soup.find_all("a", href=re.compile(r"^tel:", re.I)):
                normalized_phone = _normalize_phone(str(anchor.get("href") or ""))
                if normalized_phone and normalized_phone not in phone_values:
                    phone_values.append(normalized_phone)
            result["phone_numbers"] = phone_values[:6]
            result["emails"] = list(
                dict.fromkeys(
                    match.casefold()
                    for match in re.findall(
                        r"[\w.+-]+@[\w-]+\.[\w.-]+",
                        visible_text,
                        re.I,
                    )
                )
            )[:6]

            contact_urls: list[str] = []
            menu_urls: list[str] = []
            booking_urls: list[str] = []
            for anchor in soup.find_all("a", href=True):
                label = " ".join(anchor.get_text(" ", strip=True).split())
                href = str(anchor.get("href") or "")
                combined = f"{label} {href}"
                full_url = urljoin(page["final_url"], href)
                if re.search(r"iletişim|contact|bize ulaş", combined, re.I):
                    contact_urls.append(full_url)
                if re.search(r"\bmenü\b|\bmenu\b", combined, re.I):
                    menu_urls.append(full_url)
                if re.search(r"rezervasyon|randevu|booking|appointment", combined, re.I):
                    booking_urls.append(full_url)
            result["contact_page_urls"] = list(dict.fromkeys(contact_urls))[:5]
            result["menu_page_urls"] = list(dict.fromkeys(menu_urls))[:5]
            result["booking_urls"] = list(dict.fromkeys(booking_urls))[:5]

            result["instagram_links"] = _social_links(soup, "instagram.com")
            result["facebook_links"] = _social_links(soup, "facebook.com")
            tiktok_links = _social_links(soup, "tiktok.com")
            result["tiktok_url"] = tiktok_links[0] if tiktok_links else None

            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            text = " ".join(soup.get_text(" ", strip=True).split())
            result["word_count"] = len(re.findall(r"\b[\wÇĞİÖŞÜçğıöşü'-]+\b", text))

            images = soup.find_all("img")
            images_with_alt = sum(1 for image in images if str(image.get("alt") or "").strip())
            result["image_count"] = len(images)
            result["images_with_alt"] = images_with_alt
            result["image_alt_coverage"] = (
                round(images_with_alt / len(images) * 100, 1) if images else None
            )
            controls, labeled, coverage = _form_label_coverage(soup)
            result["form_control_count"] = controls
            result["labeled_form_control_count"] = labeled
            result["form_label_coverage"] = coverage

            base = f"{urlparse(page['final_url']).scheme}://{urlparse(page['final_url']).netloc}"
            try:
                robots = await _fetch_public(client, f"{base}/robots.txt", max_bytes=300_000)
                robots_text = robots["text"]
                result["has_robots"] = robots["status_code"] == 200 and bool(robots_text.strip())
                result["robots_status"] = "found" if result["has_robots"] else "missing"
                result["robots_blocks_site"] = (
                    _robots_blocks_all(robots_text) if result["has_robots"] else None
                )
                sitemap_candidates = re.findall(r"^Sitemap:\s*(\S+)", robots_text, re.I | re.M)
            except Exception:
                result["has_robots"] = None
                result["robots_status"] = "unreachable"
                sitemap_candidates = []

            sitemap_candidates.append(f"{base}/sitemap.xml")
            for sitemap_url in list(dict.fromkeys(sitemap_candidates))[:3]:
                try:
                    sitemap = await _fetch_public(client, sitemap_url, max_bytes=500_000)
                    body_start = sitemap["text"][:500].lower()
                    if sitemap["status_code"] == 200 and (
                        "<urlset" in body_start or "<sitemapindex" in body_start
                    ):
                        result["has_sitemap"] = True
                        result["sitemap_status"] = "found"
                        break
                except Exception:
                    continue
            if result["has_sitemap"] is None:
                result["has_sitemap"] = False
                result["sitemap_status"] = "missing"

            if check_links:
                checked, broken = await _check_internal_links(client, page["final_url"], soup)
                result["internal_links_checked"] = checked
                result["broken_internal_links"] = broken
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        result["audit_status"] = "unreachable"
        result["website_loads"] = None
        result["has_website"] = None
        result["error"] = str(exc)[:160]

    return result
