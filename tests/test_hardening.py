import base64
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from pathlib import Path

from src import auth
from src.activity import (
    build_contact_result,
    build_draft_review,
    build_manual_verification,
    decode_activity_note,
    decode_draft_note,
    decode_manual_note,
    encode_activity_note,
    encode_draft_note,
    encode_manual_note,
    enrich_outreach_event,
    status_for_outcome,
)
from src.audit.finder import _parse_ig_num, _parse_maps_search_card
from src.audit.findings import analyze_lead
from src.audit.website import _robots_blocks_all
from src.ai.generator import has_email_evidence
from src.dashboard.build import build_dashboard
from src.net_security import assert_safe_public_url
from src.services import ZEPLIN_SERVICES, discovery_services, estimate_value, match_services, recommended_package
from src.sales_assistant import build_sales_playbook
from src.research_brief import build_research_brief
from src.storage.supabase import _lead_row
from src.workflow import build_lead_workflow, build_team_performance, required_manual_checks
from scripts.migrate_leads import normalize_lead
from scripts.reaudit_leads import _official_instagram_matches


class HardeningTests(unittest.TestCase):
    def test_workflow_requires_food_menu_and_blocks_contact_until_checks_complete(self):
        lead = {
            "name": "Örnek Restoran",
            "category": "Restoran",
            "phone": "+90 212 000 00 00",
            "manual_verification": {
                "google": {"checked": True, "status": "found"},
                "instagram": {"checked": True, "status": "active"},
                "menu": {"checked": False, "status": "unknown"},
                "website": {"checked": True, "status": "working"},
            },
        }
        self.assertEqual(required_manual_checks(lead), ["google", "instagram", "menu", "website"])
        workflow = build_lead_workflow(lead)
        self.assertFalse(workflow["ready_to_contact"])
        self.assertEqual(workflow["stage"], "verification_required")
        self.assertEqual(workflow["missing"], ["Menü"])

    def test_workflow_marks_non_food_lead_ready_after_three_checks(self):
        lead = {
            "name": "Örnek Klinik",
            "category": "Diş Kliniği",
            "phone": "+90 216 000 00 00",
            "manual_verification": {
                "google": {"checked": True, "status": "found"},
                "instagram": {"checked": True, "status": "not_found"},
                "menu": {"checked": False, "status": "unknown"},
                "website": {"checked": True, "status": "not_found"},
            },
        }
        workflow = build_lead_workflow(lead)
        self.assertTrue(workflow["ready_to_contact"])
        self.assertEqual(workflow["stage"], "ready_to_contact")
        self.assertEqual(workflow["completed_count"], 3)

    def test_team_performance_uses_real_actor_events(self):
        now = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
        rows = build_team_performance(
            [{"user_email": "ahu@example.com", "status": "active"}],
            [
                {"actor_email": "ahu@example.com", "action": "manual_verification_saved", "happened_at": now.isoformat()},
                {"actor_email": "ahu@example.com", "action": "contact_result_recorded", "channel": "phone", "outcome": "won", "happened_at": now.isoformat()},
            ],
            now=now,
        )
        self.assertEqual(rows[0]["checks_today"], 1)
        self.assertEqual(rows[0]["contacts_today"], 1)
        self.assertEqual(rows[0]["calls_today"], 1)
        self.assertEqual(rows[0]["won_total"], 1)

    def test_manual_verification_is_validated_and_round_trips(self):
        verification = build_manual_verification(
            {
                "manual_verification": {
                    "google": {"checked": True, "status": "found", "rating": "4.4", "review_count": "87"},
                    "instagram": {"checked": True, "status": "inactive", "followers": "1250"},
                    "menu": {"checked": False},
                    "website": {"checked": False},
                    "notes": "Aslıhan manuel kontrol etti.",
                }
            }
        )
        decoded = decode_manual_note(encode_manual_note(verification))
        self.assertEqual(decoded["google"]["rating"], 4.4)
        self.assertEqual(decoded["google"]["review_count"], 87)
        self.assertEqual(decoded["instagram"]["status"], "inactive")
        enriched = enrich_outreach_event({"action": "manual_verification_saved", "note": encode_manual_note(verification)})
        self.assertEqual(enriched["manual_verification"]["kind"], "manual_verification")

    def test_manual_verification_rejects_empty_and_invalid_rating(self):
        with self.assertRaises(ValueError):
            build_manual_verification({})
        with self.assertRaises(ValueError):
            build_manual_verification(
                {
                    "google": {"checked": True, "status": "found", "rating": 6},
                    "instagram": {}, "menu": {}, "website": {},
                }
            )

    def test_manual_menu_gap_creates_service_and_sales_language(self):
        lead = {
            "name": "Örnek Restoran",
            "sector": "restaurant",
            "manual_verification": {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "checked_by": "aslihan@example.com",
                "google": {"checked": False},
                "instagram": {"checked": False},
                "menu": {"checked": True, "status": "outdated", "url": "https://example.com/menu"},
                "website": {"checked": False},
            },
            "audit_checks": [
                {"code": "social.instagram_presence", "status": "unknown", "label": "Instagram"}
            ],
        }
        brief = build_research_brief(lead)
        self.assertEqual(brief["manual_gaps"][0]["service_slugs"], ["menu_shoot"])
        self.assertEqual(brief["counts"]["manual"], 1)
        playbook = build_sales_playbook(lead, sender_name="Ahu Okay")
        self.assertFalse(playbook["discovery_only"])
        self.assertEqual(playbook["services"][0]["slug"], "menu_shoot")
        self.assertIn("Dijital menü güncel değil", playbook["summary"])

    def test_manual_instagram_check_suppresses_unknown_audit_check(self):
        brief = build_research_brief(
            {
                "manual_verification": {
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "google": {"checked": False},
                    "instagram": {"checked": True, "status": "active", "followers": 4200},
                    "menu": {"checked": False},
                    "website": {"checked": False},
                },
                "audit_checks": [
                    {"code": "social.instagram_presence", "status": "unknown", "label": "Instagram"}
                ],
            }
        )
        self.assertEqual(brief["unknowns"], [])
        self.assertIn("4200 takipçi", brief["manual_facts"][0]["evidence"])

    def test_draft_review_is_validated_and_round_trips(self):
        review = build_draft_review(
            {
                "channel": "email",
                "draft_status": "approved",
                "subject": "Kısa ön inceleme",
                "body": "Merhaba, taslağı kontrol ettim.",
            }
        )
        decoded = decode_draft_note(encode_draft_note(review))
        self.assertEqual(decoded["channel"], "email")
        self.assertEqual(decoded["status"], "approved")
        self.assertEqual(decoded["subject"], "Kısa ön inceleme")

    def test_draft_review_requires_content(self):
        with self.assertRaises(ValueError):
            build_draft_review({"channel": "whatsapp", "draft_status": "approved"})

    def test_research_brief_separates_fact_from_unknown(self):
        brief = build_research_brief(
            {
                "last_analyzed": datetime.now(timezone.utc).isoformat(),
                "scoring": {"coverage": 72, "confidence": 88},
                "audit_findings": [
                    {
                        "code": "website.absent",
                        "status": "confirmed",
                        "confidence": 94,
                        "title": "Website bağlantısı yok",
                        "evidence": "Maps panelinde bağlantı bulunamadı.",
                        "source_url": "https://maps.google.com/example",
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                "audit_checks": [
                    {
                        "code": "social.instagram_presence",
                        "status": "unknown",
                        "label": "Instagram varlığı",
                        "note": "Profil güvenilir biçimde doğrulanamadı.",
                        "source_url": "https://instagram.com/example",
                    }
                ],
            }
        )
        self.assertEqual(brief["status"], "ready")
        self.assertEqual(brief["confirmed_gaps"][0]["source_label"], "Google Maps")
        self.assertEqual(brief["unknowns"][0]["title"], "Instagram varlığı")
        self.assertNotIn("Instagram varlığı", [item["title"] for item in brief["confirmed_gaps"]])

    def test_research_brief_marks_old_scans_stale(self):
        brief = build_research_brief(
            {
                "last_analyzed": "2020-01-01T00:00:00+00:00",
                "scoring": {"coverage": 90, "confidence": 90},
                "audit_findings": [],
                "audit_checks": [],
            }
        )
        self.assertTrue(brief["stale"])
        self.assertNotEqual(brief["status"], "ready")

    def test_contact_result_is_validated_and_round_trips(self):
        activity = build_contact_result(
            {
                "channel": "phone",
                "outcome": "reached_later",
                "follow_up_at": "2026-08-01T10:00:00+03:00",
                "service_slugs": ["seo_organic", "seo_organic"],
                "contact_name": "Ayşe Hanım",
                "note": "Cuma yeniden ara.",
            }
        )
        decoded = decode_activity_note(encode_activity_note(activity))
        self.assertEqual(decoded["outcome"], "reached_later")
        self.assertEqual(decoded["service_slugs"], ["seo_organic"])
        self.assertEqual(status_for_outcome(decoded["outcome"]), "follow_up")

    def test_follow_up_outcome_requires_a_date(self):
        with self.assertRaises(ValueError):
            build_contact_result({"channel": "phone", "outcome": "no_answer"})

    def test_sales_playbook_uses_verified_evidence(self):
        playbook = build_sales_playbook(
            {
                "name": "Örnek Klinik",
                "category": "Diş Kliniği",
                "city": "İstanbul Kadıköy",
                "audit_findings": [
                    {
                        "status": "confirmed",
                        "title": "Website bulunamadı",
                        "evidence": "Maps kaydında website bağlantısı yok.",
                        "impact": "Randevu öncesi güven ve bilgi erişimi azalabilir.",
                        "confidence": 96,
                        "finding_type": "gap",
                    },
                    {
                        "status": "unknown",
                        "title": "Reklam ölçümü yok",
                        "evidence": "Kontrol edilemedi.",
                        "confidence": 0,
                    },
                ],
                "matched_services": [
                    {
                        "slug": "website_creation",
                        "name": "Website Oluşturma",
                        "evidence": ["Website bulunamadı"],
                        "deliverables": ["Mobil uyumlu website"],
                        "discovery_questions": ["Website hedefiniz nedir?"],
                    }
                ],
            },
            sender_name="Aslıhan Hızal",
        )
        self.assertFalse(playbook["discovery_only"])
        self.assertEqual(len(playbook["evidence_points"]), 1)
        self.assertIn("Website bulunamadı", playbook["summary"])
        self.assertIn("Aslıhan", playbook["call_opener"])
        self.assertNotIn("Reklam ölçümü yok", playbook["email_body"])
        self.assertEqual(playbook["version"], 2)
        self.assertEqual(
            {item["channel"] for item in playbook["channel_drafts"]},
            {"phone", "whatsapp", "instagram", "email"},
        )

    def test_sales_playbook_marks_unproven_services_as_discovery(self):
        playbook = build_sales_playbook(
            {
                "name": "Örnek Restoran",
                "sector": "restaurant",
                "discovery_services": [
                    {
                        "slug": "menu_shoot",
                        "name": "Menü Çekimi",
                        "deliverables": ["Menü fotoğrafları"],
                        "discovery_questions": ["Güncel menü görselleriniz var mı?"],
                        "requires_discovery": True,
                    }
                ],
            }
        )
        self.assertTrue(playbook["discovery_only"])
        self.assertIn("kesin satış iddiası", playbook["summary"])

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
        opportunity = {
            "audit_findings": [
                {
                    "status": "confirmed",
                    "confidence": 90,
                    "service_slugs": ["ai_ad_videos"],
                    "finding_type": "opportunity",
                }
            ]
        }
        self.assertFalse(has_email_evidence(low_confidence))
        self.assertTrue(has_email_evidence(verified))
        self.assertFalse(has_email_evidence(opportunity))

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

    def test_commercial_signals_require_version_four_measurements(self):
        audit = analyze_lead(
            {
                "sector": "restaurant",
                "website": {
                    "audit_version": 3,
                    "audit_status": "ok",
                    "image_count": 0,
                    "has_video_content": False,
                    "has_analytics": False,
                },
            }
        )
        codes = {item["code"] for item in audit["findings"]}
        self.assertNotIn("restaurant.menu_visibility", codes)
        self.assertNotIn("content.video_format_opportunity", codes)
        self.assertNotIn("ads.measurement_absent", codes)

    def test_restaurant_commercial_audit_maps_measured_signals_to_services(self):
        lead = normalize_lead(
            {
                "name": "Test Restoran",
                "sector": "restaurant",
                "website": {
                    "audit_version": 4,
                    "audit_status": "ok",
                    "lookup_status": "found",
                    "website_url": "https://example.com",
                    "final_url": "https://example.com",
                    "placeholder_detected": False,
                    "instagram_links": [],
                    "image_count": 3,
                    "menu_page_urls": [],
                    "has_video_content": False,
                    "has_analytics": False,
                    "has_conversion_tracking": False,
                    "has_bot_signal": False,
                    "has_phone_link": True,
                },
            }
        )
        matches = {service["slug"]: service for service in lead["matched_services"]}
        self.assertTrue(
            {
                "social_media",
                "post_design",
                "ad_management",
                "photo_video_shoot",
                "menu_shoot",
                "reels_production",
                "chatbot_voicebot",
            }.issubset(matches)
        )
        self.assertEqual(matches["ad_management"]["match_type"], "confirmed_gap")
        self.assertEqual(matches["reels_production"]["match_type"], "qualified_opportunity")

    def test_ai_video_opportunity_requires_verified_social_audience(self):
        base = {
            "sector": "retail",
            "website": {"audit_version": 4, "audit_status": "blocked"},
        }
        unknown = analyze_lead(
            {
                **base,
                "social": {
                    "has_instagram": True,
                    "identity_confidence": 20,
                    "stats": {
                        "lookup_status": "found",
                        "followers": 50_000,
                        "post_count": 200,
                    },
                },
            }
        )
        verified = analyze_lead(
            {
                **base,
                "social": {
                    "has_instagram": True,
                    "identity_confidence": 98,
                    "instagram_url": "https://instagram.com/example",
                    "stats": {
                        "lookup_status": "found",
                        "followers": 50_000,
                        "post_count": 200,
                    },
                },
            }
        )
        self.assertNotIn(
            "creative.ai_video_test_opportunity",
            {item["code"] for item in unknown["findings"]},
        )
        self.assertIn(
            "creative.ai_video_test_opportunity",
            {item["code"] for item in verified["findings"]},
        )

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
