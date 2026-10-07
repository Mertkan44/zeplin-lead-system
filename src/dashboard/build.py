import base64
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.activity import FOLLOW_UP_DELAYS
from src.services import ZEPLIN_SERVICES

DEFAULT_TEMPLATE = ROOT / "src" / "dashboard" / "template.html"
DEFAULT_OUTPUT = ROOT / "public" / "index.html"


def build_dashboard(
    template_path: Path = DEFAULT_TEMPLATE,
    output_path: Path = DEFAULT_OUTPUT,
) -> None:
    # The build reads no lead data at all: leads reach the browser only through
    # authenticated APIs, never as part of the static HTML.
    payload = base64.b64encode(b"[]").decode("ascii")
    services_payload = base64.b64encode(
        json.dumps(ZEPLIN_SERVICES, ensure_ascii=True).encode("utf-8")
    ).decode("ascii")
    html = (
        template_path.read_text(encoding="utf-8")
        .replace("__DATA__", payload)
        .replace("__SERVICES__", services_payload)
        .replace("__FOLLOW_UP_DELAYS__", json.dumps(FOLLOW_UP_DELAYS, sort_keys=True))
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    build_dashboard()
