import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.lead_schema import format_issues, load_json, validate_leads


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Zeplin lead JSON schema.")
    parser.add_argument("path", nargs="?", default="leads_final.json")
    args = parser.parse_args()

    path = ROOT / args.path
    leads = load_json(path)
    issues = validate_leads(leads)
    if issues:
        print(f"Data validation failed: {path}")
        print(format_issues(issues, limit=50))
        return 1

    print(f"Data validation passed: {path} ({len(leads)} leads)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
