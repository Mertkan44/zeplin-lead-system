import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from besiktas import run as run_scan
from src.ai.usage import usage_context
from src.storage.supabase import claim_search_jobs, record_reservation_release, update_search_job


async def process_job(job: dict) -> None:
    """Run one search job. Every AI call inside records its own usage row with
    this job's id; the job's reservation is released when it ends either way."""
    job_id = int(job["id"])
    status = "failed"
    try:
        with usage_context(job_id=job_id, actor_email=job.get("created_by")) as counters:
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
                update_search_job(job_id, status="failed", result={"error": str(exc), "ai_usage": dict(counters)})
                raise
        update_search_job(job_id, status="success", result={**(result or {}), "ai_usage": dict(counters)})
        status = "success"
    finally:
        try:
            record_reservation_release(job_id, status=status)
        except Exception as exc:
            print(f"job #{job_id}: reservation not released: {exc}")


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
