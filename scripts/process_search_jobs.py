import argparse
import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.search_worker import process_job
from src.storage.supabase import claim_search_jobs


async def main() -> None:
    parser = argparse.ArgumentParser(description='Process durable admin search jobs.')
    parser.add_argument('--limit', type=int, default=1)
    args = parser.parse_args()
    owner = str(uuid.uuid4())
    for _ in range(min(max(args.limit, 1), 10)):
        jobs = await asyncio.to_thread(claim_search_jobs, owner=owner)
        if not jobs:
            print('İş kuyruğu boş.')
            break
        job = jobs[0]
        # Only this job is leased. The next job stays queued until we are ready.
        status = await process_job(job)
        print(f"job #{job['id']}: {status}")
        if status in {'failed', 'partial_success', 'lease_lost'}:
            raise SystemExit(f"job #{job['id']}: {status}")


if __name__ == '__main__':
    asyncio.run(main())
