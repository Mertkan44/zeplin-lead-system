"""Generate the dashboard's non-secret configuration for the Vite app.

web/src/generated/app-config.json carries the service catalog and the default
follow-up delays from the Python source of truth, so the UI and the API use
the same rules. It contains no lead data: leads reach the browser only
through authenticated APIs. The dashboard itself is built with
`npm --prefix web run build` into public/.

    python src/dashboard/build.py          # write the file
    python src/dashboard/build.py --check  # fail if it is out of date (CI)
"""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.activity import FOLLOW_UP_DELAYS  # noqa: E402
from src.services import ZEPLIN_SERVICES  # noqa: E402

DEFAULT_OUTPUT = ROOT / "web" / "src" / "generated" / "app-config.json"


def render_config() -> str:
    config = {"services": ZEPLIN_SERVICES, "followUpDelays": FOLLOW_UP_DELAYS}
    return json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_dashboard(output_path: Path = DEFAULT_OUTPUT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_config(), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the generated file is out of date")
    args = parser.parse_args()
    if args.check:
        current = DEFAULT_OUTPUT.read_text(encoding="utf-8") if DEFAULT_OUTPUT.exists() else None
        if current != render_config():
            print(f"{DEFAULT_OUTPUT.relative_to(ROOT)} is out of date; run: python src/dashboard/build.py")
            return 1
        print(f"{DEFAULT_OUTPUT.relative_to(ROOT)} is up to date.")
        return 0
    build_dashboard()
    print(f"Wrote {DEFAULT_OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
