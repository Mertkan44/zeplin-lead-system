"""Read-only aggregate monitoring; never claims a job or invokes an AI provider."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from src.storage.supabase import schema_status, supabase_config


def collect(client, config, version, now):
    headers = {"apikey": config.key, "Authorization": "Bearer " + config.key}

    def count(table, query):
        response = client.get(config.url + "/rest/v1/" + table,
                              params={"select": "id", "limit": "1", **query},
                              headers={**headers, "Prefer": "count=exact"})
        response.raise_for_status()
        return int(response.headers["content-range"].rsplit("/", 1)[-1])

    since = (now - timedelta(hours=1)).isoformat()
    totals = {
        "failed_jobs_1h": count("admin_search_jobs", {"status": "in.(failed,partial_success)", "updated_at": "gte." + since}),
        "failed_generations_1h": count("ai_generations", {"status": "eq.failed", "updated_at": "gte." + since}),
        "provider_errors_1h": count("ai_token_ledger", {"kind": "eq.usage", "outcome": "in.(error,empty)", "created_at": "gte." + since}),
    }
    if str(version) >= "012":
        response = client.post(config.url + "/rest/v1/rpc/search_worker_summary", headers=headers, json={})
        response.raise_for_status()
        summary = response.json()
        totals.update({key: summary[key] for key in ("queued", "running", "retry_wait", "stalled", "oldest_queue_seconds")})
    else:
        # Compatibility with 011 while WP12's migration is pending.
        response = client.get(config.url + "/rest/v1/admin_search_jobs", headers=headers,
                              params={"select": "created_at", "status": "eq.queued", "order": "created_at.asc", "limit": "1"})
        response.raise_for_status()
        rows = response.json()
        age = (now - datetime.fromisoformat(rows[0]["created_at"].replace("Z", "+00:00"))).total_seconds() if rows else 0
        totals.update(queued=count("admin_search_jobs", {"status": "eq.queued"}),
                      running=count("admin_search_jobs", {"status": "eq.running"}), retry_wait=0,
                      stalled=count("admin_search_jobs", {"status": "eq.running", "updated_at": "lt." + (now - timedelta(hours=1)).isoformat()}),
                      oldest_queue_seconds=max(0, age))
    return totals


def alerts(totals, *, queue_age=3600, provider_errors=5):
    problems = []
    if totals["oldest_queue_seconds"] > queue_age:
        problems.append("Tarama kuyruğu bekleme sınırını aştı.")
    if totals["stalled"]:
        problems.append("Kalp atışı/kilit süresi dolan tarama var.")
    if totals["failed_jobs_1h"]:
        problems.append("Son bir saatte başarısız veya kısmen tamamlanan tarama var.")
    if totals["failed_generations_1h"]:
        problems.append("Son bir saatte başarısız AI üretimi var.")
    if totals["provider_errors_1h"] >= provider_errors:
        problems.append("Son bir saatte AI sağlayıcı hata sınırı aşıldı.")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-queue-seconds", type=int, default=3600)
    parser.add_argument("--max-provider-errors", type=int, default=5)
    args = parser.parse_args()
    try:
        if args.max_queue_seconds <= 0 or args.max_provider_errors <= 0:
            raise ValueError("positive thresholds required")
        status = schema_status()
        config = supabase_config()
        if not config or not status["ready"]:
            print("Operasyon kontrolü: veritabanı hazır değil.")
            return 1
        with httpx.Client(timeout=20) as client:
            totals = collect(client, config, status["version"], datetime.now(timezone.utc))
        # Numeric counters only: no names, contacts, prompts, content or credentials.
        for key, value in totals.items():
            print(f"{key}={round(float(value), 1)}")
        problems = alerts(totals, queue_age=args.max_queue_seconds, provider_errors=args.max_provider_errors)
        for problem in problems:
            print("ALARM: " + problem)
        return 1 if problems else 0
    except Exception as exc:
        print("Operasyon kontrolü başarısız: " + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
