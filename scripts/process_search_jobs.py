import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from besiktas import run as run_scan
from src.ai.cache import usage_totals
from src.storage.supabase import claim_search_jobs, record_token_usage, update_search_job


async def process_job(job: dict) -> None:
    job_id = int(job["id"])
    usage_before = usage_totals()
    try:
        result = await run_scan(
            query=job["query"],
            city=job["city"],
            max_results=int(job["max_results"]),
            push=False,
            sync_supabase=True,
            resume=False,
            deep_research=bool(job.get("deep_research")),
            force_ai=False,
            ai_mode=job.get("ai_mode") or "smart",
        )
    except Exception as exc:
        update_search_job(job_id, status="failed", result={"error": str(exc)})
        raise
    usage_after = usage_totals()
    usage = {key: max(usage_after.get(key, 0) - usage_before.get(key, 0), 0) for key in usage_after}
    if usage.get("total_tokens"):
        record_token_usage(job_id=job_id, model=job.get("ai_mode") or "smart", usage=usage)
    update_search_job(
        job_id,
        status="success",
        result=result,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued admin search jobs from Supabase.")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    jobs = claim_search_jobs(limit=args.limit)
    if not jobs:
        print("queued job yok")
        return
    failures = []
    for job in jobs:
        print(f"job #{job['id']}: {job['query']} / {job['city']} / {job['max_results']}")
        try:
            await process_job(job)
            print(f"job #{job['id']} tamam")
        except Exception as exc:
            failures.append((job["id"], str(exc)))
            print(f"job #{job['id']} başarısız: {exc}")
    if failures:
        raise SystemExit(f"{len(failures)} search job failed: {failures}")


if __name__ == "__main__":
    asyncio.run(main())
