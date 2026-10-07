from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.migrate_leads import SOCIAL_DEFAULTS, deep_merge, normalize_lead
from src.audit.finder import find_from_google_maps, get_instagram_stats
from src.audit.website import audit_website
from src.dashboard.build import build_dashboard
from src.storage.supabase import fetch_all_leads, upsert_leads


def _instagram_username(url: str | None) -> str | None:
    if not url:
        return None
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    username = path.split("/", 1)[0]
    if username.casefold() in {
        "p",
        "reel",
        "explore",
        "stories",
        "accounts",
        "about",
        "legal",
        "help",
    }:
        return None
    return username


def _identity_tokens(value: str | None) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    normalized = normalized.casefold().replace("ı", "i")
    ignored = {
        "istanbul",
        "restaurant",
        "restoran",
        "clinic",
        "klinik",
        "dental",
        "dukkan",
        "magaza",
        "sube",
        "official",
        "turkey",
        "turkiye",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 4 and token not in ignored
    }


def _official_instagram_matches(lead: dict, url: str) -> bool:
    username = _instagram_username(url)
    if not username:
        return False
    username_compact = re.sub(r"[^a-z0-9]", "", username.casefold())
    website_host = (
        urlparse((lead.get("website") or {}).get("website_url") or "").hostname or ""
    ).removeprefix("www.")
    domain_compact = re.sub(r"[^a-z0-9]", "", website_host.split(".", 1)[0].casefold())
    identity_tokens = _identity_tokens(lead.get("name")) | _identity_tokens(domain_compact)
    return any(
        token in username_compact or username_compact in token
        for token in identity_tokens
    )


def _archive_unverified_social(lead: dict) -> None:
    social = lead.get("social") or {}
    if not social.get("instagram_url") and not any(
        (social.get("stats") or {}).get(key) is not None
        for key in ("followers", "post_count", "avg_likes", "avg_comments", "engagement_rate")
    ):
        return
    if social.get("unverified_snapshot"):
        return
    social["unverified_snapshot"] = {
        "instagram_url": social.get("instagram_url"),
        "instagram_username": social.get("instagram_username"),
        "stats": deepcopy(social.get("stats") or {}),
        "reason": "Eski taramada profil kimliği kaynakla doğrulanmamış.",
    }


def _reconcile_social(lead: dict) -> None:
    website = lead.get("website") or {}
    social = deep_merge(SOCIAL_DEFAULTS, lead.get("social"))
    official_links = [
        link
        for link in (website.get("instagram_links") or [])
        if _official_instagram_matches(lead, link)
    ]
    existing_username = social.get("instagram_username")

    if official_links:
        official_url = official_links[0]
        official_username = _instagram_username(official_url)
        if existing_username and existing_username.casefold() != (official_username or "").casefold():
            _archive_unverified_social({"social": social})
            social["stats"] = deepcopy(SOCIAL_DEFAULTS["stats"])
        social.update(
            {
                "has_instagram": True,
                "instagram_url": official_url,
                "instagram_username": official_username,
                "lookup_status": "found",
                "identity_confidence": 98,
                "identity_evidence": (
                    "Instagram linki işletmenin websitesinde bulundu ve kullanıcı adı "
                    "işletme/alan adı kimliğiyle eşleşti."
                ),
                "checked_at": website.get("checked_at"),
            }
        )
        if social["stats"].get("lookup_status") in {None, "not_checked"}:
            social["stats"]["lookup_status"] = "legacy_unverified"
    else:
        _archive_unverified_social({"social": social})
        social["lookup_status"] = "legacy_unverified"
        social["has_instagram"] = None
        social["instagram_url"] = None
        social["instagram_username"] = None
        social["identity_confidence"] = 0
        social["identity_evidence"] = "Website üzerinde resmi Instagram linki doğrulanamadı."
        social["stats"] = deepcopy(SOCIAL_DEFAULTS["stats"])
        social["stats"]["lookup_status"] = "legacy_unverified"
    lead["social"] = social


def _archive_unverified_maps_values(lead: dict) -> None:
    maps = lead.setdefault("maps", {})
    if maps.get("review_count_lookup_status") != "found" and lead.get("review_count") is not None:
        maps["legacy_review_count"] = lead.get("review_count")
        lead["review_count"] = None
        maps["review_count_lookup_status"] = "legacy_unverified"


async def _refresh_maps(leads: list[dict]) -> list[dict]:
    refreshed: list[dict] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="tr-TR",
        )
        page = await context.new_page()
        for position, source in enumerate(leads, start=1):
            lead = deepcopy(source)
            maps_url = lead.get("maps_url")
            if not maps_url:
                refreshed.append(lead)
                continue
            result = await find_from_google_maps(
                page,
                maps_url,
                lead.get("name") or "",
                lead.get("city"),
            )
            result["maps_url"] = maps_url
            identity_confidence = int(result.get("identity_confidence") or 0)
            if result.get("source_status") == "ok" and identity_confidence >= 70:
                lead["maps"] = result
                for field in ("phone", "address", "rating", "review_count", "category"):
                    lead[field] = result.get(field)
                website_status = result.get("website_lookup_status")
                website_url = result.get("website_url")
                current_website = deepcopy(lead.get("website") or {})
                if website_status == "found" and website_url:
                    current_website["website_url"] = website_url
                    current_website["final_url"] = website_url
                elif website_status == "not_found":
                    current_website["website_url"] = None
                    current_website["final_url"] = None
                current_website["lookup_status"] = website_status or "unknown"
                lead["website"] = current_website
                print(
                    f"[Maps {position}/{len(leads)}] {lead.get('name')}: "
                    f"kimlik=%{identity_confidence} web={website_status} "
                    f"tel={result.get('phone_lookup_status')} "
                    f"yorum={result.get('review_count_lookup_status')}"
                )
            else:
                lead.setdefault("maps", {})["refresh_error"] = (
                    "Maps paneli işletmeyle güvenilir biçimde eşleştirilemedi."
                )
                print(
                    f"[Maps {position}/{len(leads)}] {lead.get('name')}: "
                    f"atlanıyor (durum={result.get('source_status')}, kimlik=%{identity_confidence})"
                )
            refreshed.append(lead)
        await browser.close()
    return refreshed


async def _refresh_instagram_stats(leads: list[dict]) -> list[dict]:
    refreshed: list[dict] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 Version/16.0 Mobile/15E148 Safari/604.1"
            ),
            viewport={"width": 390, "height": 844},
            locale="tr-TR",
        )
        page = await context.new_page()
        eligible = [
            lead
            for lead in leads
            if (lead.get("social") or {}).get("lookup_status") == "found"
            and int((lead.get("social") or {}).get("identity_confidence") or 0) >= 70
            and (lead.get("social") or {}).get("instagram_username")
        ]
        completed = 0
        for source in leads:
            lead = deepcopy(source)
            social = lead.get("social") or {}
            username = social.get("instagram_username")
            if (
                social.get("lookup_status") == "found"
                and int(social.get("identity_confidence") or 0) >= 70
                and username
            ):
                stats = await get_instagram_stats(page, username)
                social["stats"] = stats
                lead["social"] = social
                completed += 1
                print(
                    f"[Instagram {completed}/{len(eligible)}] @{username}: "
                    f"durum={stats.get('lookup_status')} "
                    f"takipçi={stats.get('followers')} gönderi={stats.get('post_count')}"
                )
                await page.wait_for_timeout(700)
            refreshed.append(normalize_lead(lead))
        await browser.close()
    return refreshed


async def _reaudit_one(lead: dict, semaphore: asyncio.Semaphore, check_links: bool) -> dict:
    updated = deepcopy(lead)
    current_website = updated.get("website") or {}
    maps = updated.get("maps") or {}
    lookup_status = (
        maps.get("website_lookup_status")
        or current_website.get("lookup_status")
        or "unknown"
    )
    candidate_url = (
        None
        if lookup_status == "not_found"
        else current_website.get("website_url") or current_website.get("final_url")
    )
    if lookup_status == "unknown" and candidate_url:
        lookup_status = "found"
    if candidate_url:
        lookup_status = "found"
    async with semaphore:
        updated["website"] = await audit_website(
            candidate_url,
            lookup_status=lookup_status,
            check_links=check_links,
        )
    updated.setdefault("maps", {})["website_lookup_status"] = lookup_status
    _archive_unverified_maps_values(updated)
    _reconcile_social(updated)
    normalized = normalize_lead(updated)
    print(
        f"{normalized['name']}: "
        f"web={normalized['website'].get('audit_status')} "
        f"kapsam=%{normalized['scoring'].get('coverage')} "
        f"bulgu={len(normalized.get('audit_findings') or [])} "
        f"hizmet={len(normalized.get('matched_services') or [])}"
    )
    return normalized


async def run(args: argparse.Namespace) -> list[dict]:
    if args.source == "supabase":
        leads = fetch_all_leads()
    else:
        leads = json.loads((ROOT / args.input).read_text(encoding="utf-8"))
    if args.limit:
        selected = leads[: args.limit]
        untouched = leads[args.limit :]
    else:
        selected = leads
        untouched = []

    if args.refresh_maps:
        selected = await _refresh_maps(selected)

    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    refreshed = await asyncio.gather(
        *(
            _reaudit_one(lead, semaphore, not args.skip_link_checks)
            for lead in selected
        )
    )
    if args.refresh_instagram:
        refreshed = await _refresh_instagram_stats(refreshed)
    merged = refreshed + [normalize_lead(lead) for lead in untouched]
    output = ROOT / args.output
    output.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"yazıldı: {output} ({len(merged)} lead)")
    if args.build:
        build_dashboard(output)
        print("dashboard build tamam")
    if args.sync:
        print(f"Supabase eşitlendi: {upsert_leads(merged)} lead")
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-audit existing leads with evidence-based website checks."
    )
    parser.add_argument("--source", choices=["supabase", "local"], default="supabase")
    parser.add_argument("--input", default="leads_final.json")
    parser.add_argument("--output", default="leads_final.json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--skip-link-checks", action="store_true")
    parser.add_argument(
        "--refresh-maps",
        action="store_true",
        help="Refresh exact Maps panels before auditing websites.",
    )
    parser.add_argument(
        "--refresh-instagram",
        action="store_true",
        help="Refresh public stats only for website-verified Instagram profiles.",
    )
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
