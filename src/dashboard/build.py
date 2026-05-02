import base64
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "leads_final.json"
DEFAULT_TEMPLATE = ROOT / "src" / "dashboard" / "template.html"
DEFAULT_OUTPUT = ROOT / "public" / "index.html"


def build_dashboard(
    data_path: Path = DEFAULT_DATA,
    template_path: Path = DEFAULT_TEMPLATE,
    output_path: Path = DEFAULT_OUTPUT,
) -> None:
    data = json.loads(data_path.read_text(encoding="utf-8"))
    payload = base64.b64encode(json.dumps(data, ensure_ascii=True).encode("utf-8")).decode("ascii")
    html = template_path.read_text(encoding="utf-8").replace("__DATA__", payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    build_dashboard()
