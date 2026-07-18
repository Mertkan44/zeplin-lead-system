import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from besiktas import run as run_scan
from src.storage.supabase import fetch_search_jobs, update_search_job


async def process_job(job: dict) -> None:
    job_id = int(job["id"])
    update_search_job(job_id, status="running")
    try:
        await run_scan(
            query=job["query"],
            city=job["city"],
            max_results=int(job["max_results"]),
            push=False,
            sync_supabase=True,
            resume=True,
            deep_research=bool(job.get("deep_research")),
            force_ai=False,
        )
    except Exception as exc:
        update_search_job(job_id, status="failed", result={"error": str(exc)})
        raise
    update_search_job(
        job_id,
        status="success",
        result={
            "query": job["query"],
            "city": job["city"],
            "max_results": job["max_results"],
        },
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued admin search jobs from Supabase.")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    jobs = fetch_search_jobs(limit=args.limit, status="queued")
    if not jobs:
        print("queued job yok")
        return
    for job in jobs:
        print(f"job #{job['id']}: {job['query']} / {job['city']} / {job['max_results']}")
        await process_job(job)
        print(f"job #{job['id']} tamam")


if __name__ == "__main__":
    asyncio.run(main())
