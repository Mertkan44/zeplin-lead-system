import base64
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.lead_schema import format_issues, validate_leads
from src.services import ZEPLIN_SERVICES

DEFAULT_DATA = ROOT / "leads_final.json"
DEFAULT_TEMPLATE = ROOT / "src" / "dashboard" / "template.html"
DEFAULT_OUTPUT = ROOT / "public" / "index.html"


def build_dashboard(
    data_path: Path = DEFAULT_DATA,
    template_path: Path = DEFAULT_TEMPLATE,
    output_path: Path = DEFAULT_OUTPUT,
) -> None:
    data = json.loads(data_path.read_text(encoding="utf-8"))
    issues = validate_leads(data)
    if issues:
        raise ValueError("Invalid lead data:\n" + format_issues(issues, limit=50))
    # Lead data is loaded only through authenticated APIs. Never publish CRM data in static HTML.
    payload = base64.b64encode(b"[]").decode("ascii")
    services_payload = base64.b64encode(
        json.dumps(ZEPLIN_SERVICES, ensure_ascii=True).encode("utf-8")
    ).decode("ascii")
    html = (
        template_path.read_text(encoding="utf-8")
        .replace("__DATA__", payload)
        .replace("__SERVICES__", services_payload)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    build_dashboard()
