import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai import cache as ai_cache
from src.ai.generator import enrich_ai_fields
from src.dashboard.build import build_dashboard
from src.lead_schema import format_issues, validate_leads
from src.research import enrich_research
from src.storage.supabase import insert_outreach_event, list_leads, set_lead_status, upsert_leads

STATUSES = ["yeni", "missing_info", "ready", "contacted", "follow_up", "converted", "lost"]
OUTREACH_ACTIONS = [
    "data_enrichment_started",
    "note_added",
    "call_started",
    "call_completed",
    "email_drafted",
    "email_sent",
    "follow_up_scheduled",
    "proposal_created",
    "proposal_sent",
    "deal_won",
    "deal_lost",
]


def _load(path: str) -> list[dict]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _write(path: str, leads: list[dict]) -> None:
    (ROOT / path).write_text(json.dumps(leads, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_validate(args) -> int:
    leads = _load(args.path)
    issues = validate_leads(leads)
    if issues:
        print(format_issues(issues, limit=80))
        return 1
    print(f"valid: {len(leads)} leads")
    return 0


def cmd_build(args) -> int:
    build_dashboard(ROOT / args.path)
    print("dashboard built")
    return 0


def cmd_sync(args) -> int:
    leads = _load(args.path)
    issues = validate_leads(leads)
    if issues:
        print(format_issues(issues, limit=80))
        return 1
    print(f"synced: {upsert_leads(leads)} leads")
    return 0


def cmd_research(args) -> int:
    leads = _load(args.path)
    count = 0
    for lead in leads:
        if args.limit and count >= args.limit:
            break
        if lead.get("research") and not args.force:
            continue
        updated = enrich_research(lead)
        lead.clear()
        lead.update(updated)
        count += 1
        print(f"researched: {lead['name']}")
    _write(args.path, leads)
    print(f"research complete: {count} leads")
    return 0


def cmd_ai(args) -> int:
    leads = _load(args.path)
    count = 0
    for lead in sorted(leads, key=lambda l: l.get("sales_priority_score") or 0, reverse=True):
        if args.limit and count >= args.limit:
            break
        if all(lead.get(key) for key in ("research_brief", "ai_report", "ai_email")) and not args.force:
            continue
        updated = enrich_ai_fields(lead, force=args.force)
        lead.clear()
        lead.update(updated)
        count += 1
        print(f"ai enriched: {lead['name']} ({lead.get('ai_tier')})")
    _write(args.path, leads)
    print(f"ai complete: {count} leads")
    return 0


def cmd_status(args) -> int:
    set_lead_status(args.name, args.status)
    print(f"status updated: {args.name} -> {args.status}")
    return 0


def cmd_event(args) -> int:
    insert_outreach_event(lead_name=args.name, action=args.action, note=args.note)
    print(f"event inserted: {args.name} / {args.action}")
    return 0


def cmd_leads(args) -> int:
    for lead in list_leads(args.limit):
        print(
            f"{lead.get('sales_priority_score', 0):>3} "
            f"{lead.get('grade', '-'):<1} "
            f"{lead.get('status', '-'):<9} "
            f"{lead.get('name')}"
        )
    return 0


def cmd_cache(args) -> int:
    print(json.dumps(ai_cache.stats(), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Zeplin Lead System technical CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate")
    p.add_argument("path", nargs="?", default="leads_final.json")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("build")
    p.add_argument("path", nargs="?", default="leads_final.json")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("sync")
    p.add_argument("path", nargs="?", default="leads_final.json")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("research")
    p.add_argument("path", nargs="?", default="leads_final.json")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_research)

    p = sub.add_parser("ai")
    p.add_argument("path", nargs="?", default="leads_final.json")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_ai)

    p = sub.add_parser("status")
    p.add_argument("name")
    p.add_argument("status", choices=STATUSES)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("event")
    p.add_argument("name")
    p.add_argument("action", choices=OUTREACH_ACTIONS)
    p.add_argument("--note")
    p.set_defaults(func=cmd_event)

    p = sub.add_parser("leads")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_leads)

    p = sub.add_parser("cache")
    p.set_defaults(func=cmd_cache)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
