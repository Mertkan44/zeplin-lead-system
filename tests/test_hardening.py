import base64
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from src import auth
from src.audit.finder import _parse_ig_num, _parse_maps_search_card
from src.audit.findings import analyze_lead
from src.audit.website import _robots_blocks_all
from src.ai.generator import has_email_evidence
from src.dashboard.build import build_dashboard
from src.net_security import assert_safe_public_url
from src.services import ZEPLIN_SERVICES, discovery_services, estimate_value, match_services, recommended_package
from src.storage.supabase import _lead_row
from scripts.migrate_leads import normalize_lead
from scripts.reaudit_leads import _official_instagram_matches


class HardeningTests(unittest.TestCase):
    def test_environment_values_are_trimmed(self):
        from src.config import env

        with patch.dict("os.environ", {"ZEPLIN_TEST_SECRET": "  secret-value \r\n"}):
            self.assertEqual(env("ZEPLIN_TEST_SECRET"), "secret-value")

    def test_maps_card_parses_review_count(self):
        parsed = _parse_maps_search_card("Örnek Klinik\n4,8\n(1.234)\nDiş Kliniği · Kadıköy")
        self.assertEqual(parsed["rating"], 4.8)
        self.assertEqual(parsed["review_count"], 1234)

    def test_robots_parser_respects_user_agent_groups(self):
        cloudflare = """
        User-agent: *
        Allow: /
        User-agent: GPTBot
        Disallow: /
        """
        blocked = """
        User-agent: *
        Disallow: /
        User-agent: Googlebot
        Allow: /
        """
        self.assertFalse(_robots_blocks_all(cloudflare))
        self.assertTrue(_robots_blocks_all(blocked))

    def test_theme_vendor_instagram_is_not_treated_as_official(self):
        lead = {
            "name": "Kanlıca Paysage Restaurant",
            "website": {"website_url": "https://paysagerestaurant.com/"},
        }
        self.assertFalse(
            _official_instagram_matches(
                lead,
                "https://www.instagram.com/themerex_net/",
            )
        )
        self.assertTrue(
            _official_instagram_matches(
                lead,
                "https://www.instagram.com/paysagerestaurant/",
            )
        )

    def test_placeholder_page_does_not_create_cascading_seo_findings(self):
        audit = analyze_lead(
            {
                "name": "Test İşletme",
                "website": {
                    "audit_version": 3,
                    "audit_status": "ok",
                    "lookup_status": "found",
                    "website_url": "https://example.com",
                    "final_url": "https://example.com",
                    "http_status": 200,
                    "placeholder_detected": True,
                    "placeholder_reason": "Coming soon page",
                    "title": "Çok Yakında",
                },
            }
        )
        codes = {item["code"] for item in audit["findings"]}
        self.assertEqual(codes, {"website.placeholder"})

    def test_email_requires_confirmed_high_confidence_service_evidence(self):
        low_confidence = {
            "audit_findings": [
                {
                    "status": "confirmed",
                    "confidence": 66,
                    "service_slugs": ["website_creation"],
                }
            ]
        }
        verified = {
            "audit_findings": [
                {
                    "status": "confirmed",
                    "confidence": 94,
                    "service_slugs": ["website_creation"],
                }
            ]
        }
        self.assertFalse(has_email_evidence(low_confidence))
        self.assertTrue(has_email_evidence(verified))

    def test_missing_website_is_a_finding_only_when_maps_confirmed_it(self):
        unknown = normalize_lead({"name": "Test", "website": {"audit_version": 3, "audit_status": "missing", "lookup_status": "unknown"}})
        confirmed = normalize_lead({"name": "Test", "website": {"audit_version": 3, "audit_status": "missing", "lookup_status": "not_found"}})
        self.assertFalse(any(item["code"] == "website.absent" for item in unknown["audit_findings"]))
        self.assertTrue(any(item["code"] == "website.absent" for item in confirmed["audit_findings"]))

    def test_invalid_messaging_link_is_not_a_website(self):
        lead = {
            "name": "Test",
            "website": {
                "audit_version": 3,
                "audit_status": "invalid_candidate",
                "lookup_status": "found",
                "candidate_kind": "social_or_messaging",
                "website_url": "https://wa.me/905000000000",
            },
        }
        audit = analyze_lead(lead)
        self.assertIn("website.invalid_candidate", {item["code"] for item in audit["findings"]})
        self.assertNotIn("seo.schema", {item["code"] for item in audit["findings"]})

    def test_empty_structured_audit_does_not_fall_back_to_legacy_flags(self):
        services = match_services(
            {
                "audit": {"version": 3, "findings": []},
                "website": {"has_website": False, "has_schema": False},
            }
        )
        self.assertEqual(services, [])

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
        self.assertTrue(row["external_id"].startswith("name-city:"))

    def test_lead_identity_does_not_change_with_maps_url(self):
        base = {
            "name": "Test Lead",
            "city": "Istanbul Kadikoy",
        }
        first = _lead_row({**base, "maps_url": "https://www.google.com/maps/place/test?one"})
        second = _lead_row({**base, "maps_url": "https://www.google.com/maps/place/test?two"})
        self.assertEqual(first["external_id"], second["external_id"])

    def test_catalog_contains_only_owner_approved_services(self):
        self.assertEqual(
            {service["slug"] for service in ZEPLIN_SERVICES},
            {
                "website_creation",
                "seo_organic",
                "social_media",
                "post_design",
                "ad_management",
                "photo_video_shoot",
                "menu_shoot",
                "reels_production",
                "chatbot_voicebot",
                "ai_ad_videos",
            },
        )

    def test_low_reviews_does_not_recommend_a_service(self):
        services = match_services({"review_count": 8})
        slugs = {service["slug"] for service in services}
        self.assertEqual(slugs, set())

    def test_missing_whatsapp_does_not_recommend_chatbot(self):
        services = match_services({"website": {"has_whatsapp": False}})
        slugs = {service["slug"] for service in services}
        self.assertEqual(slugs, set())

    def test_restaurant_menu_shoot_requires_discovery(self):
        services = match_services({"sector": "restaurant"})
        self.assertNotIn("menu_shoot", {service["slug"] for service in services})

    def test_missing_schema_conditionally_recommends_seo(self):
        services = match_services({"website": {"has_schema": False}})
        self.assertEqual({service["slug"] for service in services}, {"seo_organic"})
        self.assertTrue(services[0]["requires_discovery"])

    def test_missing_service_match_precedes_ai_generation(self):
        lead = normalize_lead(
            {
                "name": "Test Lead",
                "phone": "0212 000 00 00",
                "website": {"has_website": True},
                "social": {"has_instagram": True, "stats": {}},
                "scoring": {"score": 70},
            }
        )
        self.assertEqual(lead["next_action"], "Derin audit yap")

    def test_unknown_metrics_do_not_create_false_findings(self):
        services = match_services(
            {
                "rating": None,
                "review_count": None,
                "social": {"has_instagram": True, "stats": {}},
            }
        )
        self.assertEqual(services, [])
        recommendation = recommended_package({})
        self.assertEqual(recommendation["kind"], "discovery_recommendation")
        self.assertEqual(recommendation["confidence"], 0)
        self.assertEqual(recommendation["evidence"], [])

    def test_discovery_options_fill_empty_state_without_claiming_evidence(self):
        lead = {"sector": "restaurant", "website": {"has_website": True}}
        options = discovery_services(lead)
        self.assertEqual(options[0]["slug"], "menu_shoot")
        self.assertTrue(all(item["requires_discovery"] for item in options))
        self.assertTrue(all(not item["evidence"] for item in options))
        self.assertEqual(recommended_package(lead)["primary_service"], "Menü Çekimi")

    def test_unapproved_prices_do_not_create_revenue_estimates(self):
        lead = {"website": {"has_website": False}}
        self.assertEqual(estimate_value(lead), 0)

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
