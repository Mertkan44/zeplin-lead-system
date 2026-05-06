import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.migrate_leads import normalize_lead
from src.audit.finder import find_from_google_maps, get_instagram_stats, compute_score


async def refresh_metrics(path: Path) -> list[dict]:
    leads = json.loads(path.read_text(encoding="utf-8"))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="tr-TR",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = await ctx.new_page()

        refreshed: list[dict] = []
        for idx, lead in enumerate(leads, start=1):
            name = lead.get("name") or f"lead-{idx}"
            print(f"[{idx}/{len(leads)}] {name}")
            merged = dict(lead)

            if lead.get("maps_url"):
                maps_data = await find_from_google_maps(page, lead["maps_url"], name)
                for key in ("phone", "address", "rating", "review_count", "category"):
                    if maps_data.get(key) is not None:
                        merged[key] = maps_data.get(key)
                if maps_data.get("website_url"):
                    website = dict(merged.get("website") or {})
                    website["website_url"] = maps_data["website_url"]
                    website["has_website"] = True
                    merged["website"] = website

            social = dict(merged.get("social") or {})
            username = social.get("instagram_username")
            if username:
                ig_stats = await get_instagram_stats(page, username)
                social["stats"] = {**(social.get("stats") or {}), **ig_stats}
                merged["social"] = social

            merged["scoring"] = compute_score(
                merged.get("website") or {},
                merged.get("social") or {},
                (merged.get("social") or {}).get("stats") or {},
                (merged.get("social") or {}).get("tiktok") or {},
                {
                    "rating": merged.get("rating"),
                    "review_count": merged.get("review_count"),
                    "delivery": merged.get("delivery"),
                },
                merged.get("sector", "default"),
            )
            refreshed.append(normalize_lead(merged))

        await browser.close()

    return refreshed


def main() -> None:
    path = ROOT / "leads_final.json"
    refreshed = asyncio.run(refresh_metrics(path))
    path.write_text(json.dumps(refreshed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
