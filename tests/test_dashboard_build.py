"""The dashboard build: generated config, committed bundle and CSP stay in step.

The app itself is built by `npm --prefix web run build` (CI rebuilds it and
fails if public/ differs); these checks need no Node.
"""

import base64
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.activity import FOLLOW_UP_DELAYS
from src.dashboard.build import build_dashboard, render_config
from src.services import ZEPLIN_SERVICES

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_INDEX = ROOT / "public" / "index.html"


def _csp() -> dict[str, str]:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    values = {header["value"] for header in config["headers"][0]["headers"] if header["key"] == "Content-Security-Policy"}
    values |= {route["headers"]["Content-Security-Policy"] for route in config["routes"] if "headers" in route}
    assert len(values) == 1, "the two CSP copies in vercel.json differ"
    policy = values.pop()
    return {part.split()[0]: part for part in (item.strip() for item in policy.split(";")) if part}


class DashboardBuildTests(unittest.TestCase):
    def test_config_comes_from_the_python_rules_and_reads_no_lead_data(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "app-config.json"
            original = Path.read_text
            with patch.object(Path, "read_text", autospec=True, side_effect=original) as reads:
                build_dashboard(output)
            self.assertEqual(reads.call_args_list, [])
            config = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(config, {"services": ZEPLIN_SERVICES, "followUpDelays": FOLLOW_UP_DELAYS})

    def test_committed_config_is_current(self):
        committed = (ROOT / "web" / "src" / "generated" / "app-config.json").read_text(encoding="utf-8")
        self.assertEqual(committed, render_config(), "run: python src/dashboard/build.py")

    def test_page_has_no_runtime_compiler_or_cdn_scripts(self):
        html = PUBLIC_INDEX.read_text(encoding="utf-8")
        self.assertNotIn("text/babel", html)
        self.assertNotIn("unpkg.com", html)
        for src in re.findall(r'<script[^>]*\bsrc="([^"]+)"', html):
            self.assertTrue(src.startswith("/assets/"), src)
            self.assertTrue((ROOT / "public" / src.lstrip("/")).exists(), f"{src} is not in public/")

    def test_dashboard_sources_are_all_typescript(self):
        # Every screen is typed; untyped JS/JSX would skip the typecheck.
        untyped = [str(path.relative_to(ROOT)) for path in (ROOT / "web" / "src").rglob("*") if path.suffix in {".js", ".jsx"}]
        self.assertEqual(untyped, [])

    def test_unknown_paths_fall_back_to_the_built_page(self):
        # Vercel serves public/ as the site root, so deep links such as
        # /leads/57 must be rewritten to /index.html (not /public/index.html).
        routes = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))["routes"]
        fallback = routes[-1]
        self.assertEqual(fallback["src"], "/(.*)")
        self.assertTrue((ROOT / "public" / fallback["dest"].lstrip("/")).is_file(), fallback["dest"])
        handled = [route.get("handle") for route in routes]
        self.assertLess(handled.index("filesystem"), len(routes) - 1, "files and the API must win over the fallback")

    def test_csp_allows_exactly_the_inline_scripts_of_the_built_page(self):
        csp = _csp()
        script_src = csp["script-src"]
        for forbidden in ("'unsafe-inline'", "'unsafe-eval'", "unpkg.com"):
            self.assertNotIn(forbidden, script_src)
        html = PUBLIC_INDEX.read_text(encoding="utf-8")
        inline = re.findall(r"<script>(.*?)</script>", html, re.S)
        expected = {
            "'sha256-" + base64.b64encode(hashlib.sha256(code.encode("utf-8")).digest()).decode() + "'" for code in inline
        }
        allowed = set(re.findall(r"'sha256-[^']+'", script_src))
        self.assertEqual(allowed, expected, "update script-src in vercel.json to the inline script hashes")

    def test_csp_allows_no_inline_styles(self):
        # React sets styles through the CSSOM, which style-src does not govern;
        # style attributes or <style> blocks in served HTML would be blocked.
        style_src = _csp()["style-src"]
        self.assertNotIn("'unsafe-inline'", style_src)
        html = PUBLIC_INDEX.read_text(encoding="utf-8")
        self.assertNotIn("<style", html)
        self.assertNotIn(" style=", html)


if __name__ == "__main__":
    unittest.main()
