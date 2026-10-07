"""Generate tests/fixtures/leads_sample.json: synthetic leads for tests, CI and demos.

Every business here is invented: names are made up, domains end in .example,
phone numbers are all zeros and Google place ids say "synthetic". Real lead data
lives in Supabase (export it locally with scripts/export_leads.py) and is never
committed.

    python scripts/make_sample_leads.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.migrate_leads import normalize_lead  # noqa: E402
from src.lead_schema import format_issues, validate_leads  # noqa: E402

OUTPUT = ROOT / "tests" / "fixtures" / "leads_sample.json"

# (name, city, sector, category, rating, reviews, has_website, has_instagram)
BUSINESSES = [
    ("Örnek Kafe Nilüfer", "Bursa Nilüfer", "restaurant", "Kafe", 4.4, 87, True, True),
    ("Deneme Diş Kliniği", "İstanbul Kadıköy", "health", "Diş kliniği", 4.9, 32, True, False),
    ("Kurgu Kuaför Salonu", "İzmir Karşıyaka", "beauty", "Kuaför", 4.1, 140, False, True),
    ("Hayali Mobilya Atölyesi", "Ankara Çankaya", "retail", "Mobilya mağazası", 3.8, 12, False, False),
    ("Taslak Pastanesi", "İstanbul Beşiktaş", "restaurant", "Pastane", 4.6, 410, True, True),
    ("Model Spor Salonu", "Antalya Muratpaşa", "fitness", "Spor salonu", 4.2, 65, True, True),
    ("Prototip Veteriner", "Eskişehir Tepebaşı", "health", "Veteriner", None, None, False, False),
    ("Numune Kitabevi", "İstanbul Kadıköy", "retail", "Kitabevi", 4.8, 9, True, False),
    ("Örnek Meyhane", "İzmir Alsancak", "restaurant", "Meyhane", 4.3, 230, False, True),
    ("Deneme Oto Yıkama", "Bursa Osmangazi", "automotive", "Oto yıkama", 3.5, 44, False, False),
]

# The same invented clinic stored a second time under another name, so the
# identity report has a shared place id, phone and website to find.
DUPLICATE_OF = 1
DUPLICATE_NAME = "Deneme Dental Clinic"


def _lead(index: int, business: tuple, *, name: str | None = None) -> dict:
    title, city, sector, category, rating, reviews, has_website, has_instagram = business
    slug = f"sample-{index:02d}"
    raw = {
        "name": name or title,
        "city": city,
        "sector": sector,
        "category": category,
        "query": category.lower(),
        "phone": f"0000 000 00 {index:02d}",
        "address": f"Örnek Mah. Deneme Sk. No:{index}, {city}",
        "rating": rating,
        "review_count": reviews,
        "maps_url": f"https://www.google.com/maps/place/{slug}/data=!4m7!3m6!19sChIJsynthetic{index:06d}",
        "website": {"has_website": has_website, "website_url": f"https://{slug}.example" if has_website else None},
        "social": {"instagram_url": f"https://instagram.com/{slug}.example" if has_instagram else None},
        "last_analyzed": "2026-10-01 10:00",
    }
    return normalize_lead(raw)


def build() -> list[dict]:
    leads = [_lead(index, business) for index, business in enumerate(BUSINESSES, start=1)]
    leads.append(_lead(DUPLICATE_OF + 1, BUSINESSES[DUPLICATE_OF], name=DUPLICATE_NAME))
    return leads


def main() -> int:
    leads = build()
    issues = validate_leads(leads)
    if issues:
        print(format_issues(issues, limit=20))
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(leads, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(leads)} synthetic leads)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
