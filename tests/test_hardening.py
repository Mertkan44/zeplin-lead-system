import base64
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from src import auth
from src.audit.finder import _parse_ig_num, _parse_maps_search_card
from src.dashboard.build import build_dashboard
from src.net_security import assert_safe_public_url
from src.storage.supabase import _lead_row


class HardeningTests(unittest.TestCase):
    def test_environment_values_are_trimmed(self):
        from src.config import env

        with patch.dict("os.environ", {"ZEPLIN_TEST_SECRET": "  secret-value \r\n"}):
            self.assertEqual(env("ZEPLIN_TEST_SECRET"), "secret-value")

    def test_maps_card_parses_review_count(self):
        parsed = _parse_maps_search_card("Örnek Klinik\n4,8\n(1.234)\nDiş Kliniği · Kadıköy")
        self.assertEqual(parsed["rating"], 4.8)
        self.assertEqual(parsed["review_count"], 1234)

    def test_instagram_decimal_suffix(self):
        self.assertEqual(_parse_ig_num("5.8K"), 5800)
        self.assertEqual(_parse_ig_num("1,2M"), 1_200_000)

    def test_private_urls_are_rejected(self):
        with self.assertRaises(ValueError):
            assert_safe_public_url("http://127.0.0.1/admin")
        with self.assertRaises(ValueError):
            assert_safe_public_url("http://169.254.169.254/latest/meta-data")

    def test_scan_upsert_does_not_overwrite_crm_status(self):
        row = _lead_row(
            {
                "name": "Test Lead",
                "city": "Istanbul Kadikoy",
                "maps_url": "https://www.google.com/maps/place/test",
                "status": "converted",
            }
        )
        self.assertNotIn("status", row)
        self.assertTrue(row["external_id"].startswith("maps:"))

    def test_invalid_role_is_not_promoted(self):
        now = 2_000_000_000
        payload = {"sub": "admin", "role": "invalid", "iat": now - 10, "exp": now + 10}
        with patch.dict(os.environ, {"SESSION_SECRET": "test-secret", "ALLOW_LEGACY_ADMIN_LOGIN": "1", "ADMIN_PASSWORD": "x"}):
            raw = auth._b64(json.dumps(payload).encode())
            token = f"{raw}.{auth._sign(raw)}"

            class Request:
                headers = {"Cookie": f"{auth.COOKIE_NAME}={token}"}

            with patch("src.auth.time.time", return_value=now):
                self.assertIsNone(auth.current_user(Request()))

    def test_dashboard_build_contains_no_lead_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_path = root / "leads.json"
            template_path = root / "template.html"
            output_path = root / "index.html"
            data_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "SECRET CUSTOMER",
                            "city": "Istanbul",
                            "maps_url": "https://maps.example/customer",
                            "phone": None,
                            "address": None,
                            "rating": None,
                            "review_count": None,
                            "website": {},
                            "social": {},
                            "scoring": {},
                            "matched_services": [],
                            "recommended_package": {},
                            "estimated_value_tl": 0,
                            "sales_priority_score": 0,
                            "next_action": "Araştır",
                            "data_quality": {},
                            "schema_version": 2,
                            "status": "yeni",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            template_path.write_text("__DATA__ __SERVICES__", encoding="utf-8")
            with patch("src.dashboard.build.validate_leads", return_value=[]):
                build_dashboard(data_path, template_path, output_path)
            built = output_path.read_text(encoding="utf-8")
            self.assertNotIn("SECRET CUSTOMER", built)
            self.assertIn(base64.b64encode(b"[]").decode(), built)


if __name__ == "__main__":
    unittest.main()
