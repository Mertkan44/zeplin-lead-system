"""Dry-run report for the lead identity migration. Reads only; never writes.

Lists what must be reviewed by a person before the name-based identity can be
retired: leads sharing a Google place id, phone or website, place ids recorded
for a different lead, rows still missing lead_id, and leads whose stored
external_id differs from what the sync writes.

    python scripts/lead_identity_report.py                  # live Supabase
    python scripts/lead_identity_report.py --file leads_final.json
    python scripts/lead_identity_report.py --json > report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.lead_identity import find_identity_conflicts  # noqa: E402


def _names(items: list[dict]) -> str:
    return " | ".join(f"{item.get('name')} ({item.get('city') or '-'})" for item in items)


def render_text(report: dict) -> str:
    lines = [f"Source: {report['source']}", f"Leads: {report['lead_count']}"]

    def section(title: str, rows: list[str]) -> None:
        lines.append("")
        lines.append(f"{title}: {len(rows)}")
        lines.extend(f"  - {row}" for row in rows[:50])
        if len(rows) > 50:
            lines.append(f"  ... {len(rows) - 50} more (use --json)")

    section(
        "Same Google place id on several leads (likely one business; review before merging)",
        [f"{group['key']}: {_names(group['leads'])}" for group in report["shared_place_id"]],
    )
    section(
        "Same phone number on several leads (possible duplicate or shared switchboard)",
        [f"{group['key']}: {_names(group['leads'])}" for group in report["shared_phone"]],
    )
    section(
        "Same website on several leads (possible duplicate or branches of one brand)",
        [f"{group['key']}: {_names(group['leads'])}" for group in report["shared_website"]],
    )
    section("Leads without a Google place id", [_names([item]) for item in report["without_place_id"]])
    if report.get("sources_available"):
        section(
            "Place id already recorded for another lead (not merged)",
            [f"{_names([item])}: {item['place_id']} -> lead {item['recorded_for']}" for item in report["place_owned_elsewhere"]],
        )
        section(
            "Place id not yet recorded in lead_sources (recorded when the lead is next saved)",
            [f"{_names([item])}: {item['place_id']}" for item in report["place_not_recorded"]],
        )
        gaps = report.get("lead_id_gaps") or {}
        lines.append("")
        lines.append(
            "Rows missing lead_id: "
            + ", ".join(f"{table}={count}" for table, count in gaps.items())
        )
    elif report["source"] == "supabase":
        lines.append("")
        lines.append("lead_sources is missing: apply supabase/migrations/008_lead_identity_expand.sql first.")
    section(
        "Stored external_id differs from the sync's name+city hash (rewritten on next sync)",
        [_names([item]) for item in report["external_id_mismatch"]],
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, help="read leads from a local JSON export instead of Supabase")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args()

    if args.file:
        leads = json.loads(args.file.read_text(encoding="utf-8"))
        report = {**find_identity_conflicts(leads), "source": str(args.file), "sources_available": False}
    else:
        from src.storage.supabase import fetch_identity_snapshot, is_enabled

        if not is_enabled():
            print("Supabase is not configured; pass --file to run against a local export.", file=sys.stderr)
            return 2
        snapshot = fetch_identity_snapshot()
        report = {
            **find_identity_conflicts(snapshot["leads"], snapshot["sources"]),
            "source": "supabase",
            "sources_available": snapshot["sources"] is not None,
            "lead_id_gaps": snapshot["lead_id_gaps"],
        }

    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
