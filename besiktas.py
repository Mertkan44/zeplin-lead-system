"""
Belirtilen ilçeden işletme tara, audit et, AI raporu üret, dashboard'a ekle.
"""
import argparse
import asyncio
import json
import os
from playwright.async_api import async_playwright
from datetime import datetime, timezone

from src.ai.generator import AI_PROMPT_VERSION, ai_input_fingerprint, generate_email, generate_report, generate_research_brief
from src.audit.finder import (
    find_from_google_maps, check_website, detect_sector,
    find_instagram, get_instagram_stats,
    find_tiktok, check_delivery
)
from src.pipeline_state import get_stage, put_stage
from src.research import enrich_research
from src.storage.supabase import insert_run_log, is_enabled as supabase_enabled, upsert_leads
from scripts.migrate_leads import normalize_lead

QUERY = "restoran"
CITY = "Istanbul Besiktas"
MAX_RESULTS = 5

# ── Scraper ────────────────────────────────────────────
async def scrape(query, city, max_results):
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
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

# ── Dashboard ──────────────────────────────────────────
def update_dashboard(data):
    # Local working copy only (ignored by Git). The dashboard reads leads from
    # the API, so nothing is rebuilt or pushed after a scan.
    json.dump(data, open('leads_final.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print("✅ leads_final.json güncellendi (yalnızca yerel kopya).")

# ── ANA AKIŞ ───────────────────────────────────────────
async def run(
    query: str,
    city: str,
    max_results: int,
    push: bool,
    sync_supabase: bool,
    resume: bool,
    deep_research: bool,
    force_ai: bool,
    ai_mode: str = "smart",
):
    failures = []
    show_browser = os.getenv("ZEPLIN_SHOW_BROWSER") == "1"
    # 1. Scrape
    raw = await scrape(query, city, max_results)
    print(f"\n📋 {len(raw)} işletme bulundu:")
    for r in raw: print(f"  • {r['name']}")

    # 2. Audit
    audited = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not show_browser, args=["--no-sandbox"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="tr-TR"
        )
        page = await ctx.new_page()

        for lead in raw:
            name = lead["name"]
            print(f"\n► {name}")
            cached = get_stage(name, "audited", city=city, query=query) if resume else None
            if cached:
                print("  ↩️  resume: audit cache kullanıldı")
                audited.append(cached)
                continue

            maps_data = await find_from_google_maps(page, lead["maps_url"], name, lead.get("city"))
            print(f"  🌐 {maps_data.get('website_url') or '—'}")
            print(f"  📞 {maps_data.get('phone') or '—'}")
            print(f"  📍 {maps_data.get('address') or '—'}")
            print(f"  ⭐ {maps_data.get('rating','—')} puan · {maps_data.get('review_count','?')} yorum")
            print(f"  🏷️  {maps_data.get('category') or '—'}")

            sector  = detect_sector(maps_data.get("category"))
            website = await check_website(
                maps_data.get("website_url"),
                lookup_status=maps_data.get("website_lookup_status") or "unknown",
            )
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

            lead_obj = normalize_lead({
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
                "maps":         maps_data,
                "scoring":      {},
            })
            print(f"  💰 Tahmini değer: {lead_obj['estimated_value_tl']:,} TL/ay · {len(lead_obj['matched_services'])} hizmet eşleşti")
            audited.append(lead_obj)
            put_stage(name, "audited", lead_obj, city=city, query=query)
            await asyncio.sleep(1)

        await browser.close()

    # 3. AI raporlar
    print("\n🤖 AI raporlar üretiliyor...")
    for idx, lead in enumerate(audited):
        print(f"  → {lead['name']} [{lead['sector']}]")
        cached_ai = get_stage(lead["name"], "ai", city=city, query=query) if resume and not force_ai else None
        if cached_ai:
            audited[idx] = cached_ai
            print("    ↩️  resume: AI cache kullanıldı")
            continue
        try:
            lead["_ai_mode"] = ai_mode
            if deep_research:
                lead = enrich_research(lead)
            ai_input_hash = ai_input_fingerprint(lead)  # what the model sees
            lead["research_brief"] = generate_research_brief(lead, force=force_ai)
            lead["ai_report"] = generate_report(lead, force=force_ai)
            lead["ai_email"] = generate_email(lead, force=force_ai)
            lead["ai_prompt_version"] = AI_PROMPT_VERSION
            lead["ai_input_hash"] = ai_input_hash
            lead["ai_generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            lead["last_analyzed"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            lead.pop("_ai_mode", None)
            lead = normalize_lead(lead)
            audited[idx] = lead
            put_stage(lead["name"], "ai", lead, city=city, query=query)
        except Exception as exc:
            lead.pop("_ai_mode", None)
            lead = normalize_lead(lead)
            lead["last_analyzed"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            audited[idx] = lead
            failures.append({"name": lead["name"], "stage": "ai", "error": str(exc)})
            print(f"    ⚠️ AI fallback ile devam: {exc}")
            put_stage(lead["name"], "ai", lead, city=city, query=query)

    # 4. Birleştir
    existing = json.load(open('leads_final.json', encoding='utf-8'))
    existing_map = {lead["name"]: lead for lead in existing}
    new_count = 0
    updated_count = 0
    for lead in audited:
        normalized = normalize_lead(lead)
        if normalized["name"] in existing_map:
            prior = existing_map[normalized["name"]]
            normalized["status"] = prior.get("status") or "yeni"
            updated_count += 1
        else:
            new_count += 1
        existing_map[normalized["name"]] = normalized
    merged = list(existing_map.values())
    print(f"\n📊 {len(existing)} mevcut + {new_count} yeni / {updated_count} güncel = {len(merged)} toplam")

    # 5. Dashboard & push
    update_dashboard(merged)
    if sync_supabase:
        if supabase_enabled():
            synced = upsert_leads(audited)
            insert_run_log(
                kind="scan",
                status="partial_success" if failures else "success",
                message=f"{city} scan synced {synced} leads",
                meta={
                    "query": query,
                    "city": city,
                    "max_results": max_results,
                    "synced": synced,
                    "new_count": new_count,
                    "updated_count": updated_count,
                    "failures": failures,
                },
            )
            print(f"🟢 Supabase sync tamamlandı: {synced} lead")
        else:
            print("⚠️ Supabase sync istendi ama SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY eksik.")
    if push:
        print("ℹ️ --push artık gerekmiyor: panel leadleri API'den okur; Supabase için --sync-supabase kullan.")
    else:
        print("ℹ️ Push atlanıldı. Commit/push için --push kullan.")
    if failures:
        print(f"⚠️ {len(failures)} lead AI fallback ile tamamlandı.")
    print(f"\n🎉 Tamamlandı!")
    return {
        "query": query,
        "city": city,
        "requested": max_results,
        "audited": len(audited),
        "new_count": new_count,
        "updated_count": updated_count,
        "failures": failures,
    }

def parse_args():
    parser = argparse.ArgumentParser(description="Scan, audit, and publish Zeplin leads.")
    parser.add_argument("--query", default=QUERY)
    parser.add_argument("--city", default=CITY)
    parser.add_argument("--max", type=int, default=MAX_RESULTS, dest="max_results")
    parser.add_argument("--push", action="store_true", help="obsolete; the dashboard reads leads from the API")
    parser.add_argument("--sync-supabase", action="store_true", help="Sync merged leads to Supabase.")
    parser.add_argument("--resume", action="store_true", help="Reuse cached audit/AI stages from .cache.")
    parser.add_argument("--deep-research", action="store_true", help="Fetch extra website research before AI.")
    parser.add_argument("--force-ai", action="store_true", help="Ignore AI generation cache.")
    parser.add_argument("--ai-mode", choices=["flash", "smart", "pro"], default="smart")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        run(
            args.query,
            args.city,
            args.max_results,
            args.push,
            args.sync_supabase,
            args.resume,
            args.deep_research,
            args.force_ai,
            args.ai_mode,
        )
    )
