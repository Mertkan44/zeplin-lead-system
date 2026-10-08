"""Export every lead from Supabase to a local JSON file (default leads_final.json).

Supabase is the source of truth for lead data; the repository is public and no
longer carries it. Use this to get a local working copy for the CLI tools
(besiktas.py, migrate_leads.py, reaudit_leads.py, ...). The output path is
ignored by Git; scripts/security_check.py fails if lead data gets tracked.
Reads only; writes nothing to Supabase.

    python scripts/export_leads.py
    python scripts/export_leads.py --output /tmp/leads.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.storage.supabase import fetch_all_leads, is_enabled  # noqa: E402

# Attached on read from database columns; not part of the stored lead document.
_DATABASE_FIELDS = {"lead_id", "revision", "supabase_updated_at"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=ROOT / "leads_final.json")
    args = parser.parse_args()
    if not is_enabled():
        print("Supabase is not configured (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY).", file=sys.stderr)
        return 2
    leads = [
        {key: value for key, value in lead.items() if key not in _DATABASE_FIELDS}
        for lead in fetch_all_leads()
    ]
    args.output.write_text(json.dumps(leads, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(leads)} leads to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
