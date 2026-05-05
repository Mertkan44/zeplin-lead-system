import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.lead_schema import format_issues, validate_leads
from src.storage.supabase import insert_run_log, upsert_leads


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync lead JSON data to Supabase.")
    parser.add_argument("path", nargs="?", default="leads_final.json")
    args = parser.parse_args()

    path = ROOT / args.path
    leads = json.loads(path.read_text(encoding="utf-8"))
    issues = validate_leads(leads)
    if issues:
        print("Refusing to sync invalid lead data:")
        print(format_issues(issues, limit=50))
        return 1

    count = upsert_leads(leads)
    insert_run_log(
        kind="sync",
        status="success",
        message=f"Synced {count} leads from {args.path}",
        meta={"path": args.path, "lead_count": count},
    )
    print(f"Synced {count} leads to Supabase.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
