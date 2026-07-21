import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.storage.supabase import reset_sales_activity


def main() -> int:
    result = reset_sales_activity()
    print("Sales activity reset completed.")
    print(f"Lead statuses reset: {result['lead_statuses_reset']}")
    print(f"Outreach events deleted: {result['outreach_events_deleted']}")
    if result["assignments_table_available"]:
        print(f"Active assignments archived: {result['assignments_archived']}")
    else:
        print("Assignments table not available; skipped assignment archive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
