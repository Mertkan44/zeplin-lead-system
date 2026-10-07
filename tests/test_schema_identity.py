"""Schema readiness, the health probe and the lead identity dry-run report."""

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import api.health as health_api
from src.lead_identity import find_identity_conflicts, google_place_id, lead_external_id
from src.storage.supabase import REQUIRED_SCHEMA_VERSION, _in_list, _lead_row, evaluate_schema_readiness

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tests" / "fixtures" / "leads_sample.json"
ALL_CHECKS = {
    "assign_lead_owner": True,
    "idempotency_constraint": True,
    "lead_sources": True,
}


def _lead(name, place_id=None, phone=None, website=None, lead_id=None, verified=None):
    lead = {"id": lead_id, "name": name, "city": "Bursa", "phone": phone, "website": {"website_url": website}}
    if place_id:
        lead["maps_url"] = f"https://www.google.com/maps/place/X/data=!4m7!3m6!19s{place_id}?hl=tr"
    if verified:
        lead["research"] = {"google_places": {"status": "verified", "place_id": verified}}
    return lead


class SchemaReadinessTests(unittest.TestCase):
    def test_ready_only_with_required_version_and_all_checks(self):
        self.assertTrue(evaluate_schema_readiness({"version": REQUIRED_SCHEMA_VERSION, "checks": ALL_CHECKS})["ready"])
        old = evaluate_schema_readiness({"version": "008", "checks": ALL_CHECKS})
        self.assertFalse(old["ready"])
        broken = evaluate_schema_readiness({"version": REQUIRED_SCHEMA_VERSION, "checks": {**ALL_CHECKS, "idempotency_constraint": False}})
        self.assertFalse(broken["ready"])
        self.assertEqual(broken["failed_checks"], ["idempotency_constraint"])

    def test_database_without_readiness_rpc_is_not_ready(self):
        status = evaluate_schema_readiness({"version": None, "checks": {"schema_readiness": False}})
        self.assertFalse(status["ready"])
        self.assertEqual(status["failed_checks"], ["schema_readiness"])

    def _health(self, status, user):
        handler = health_api.handler.__new__(health_api.handler)
        handler.headers = {}
        captured = {}

        def fake_send_json(_handler, code, payload, **_kwargs):
            captured.update(code=code, payload=payload)

        with patch.object(health_api, "send_json", fake_send_json), \
                patch.object(health_api, "supabase_enabled", return_value=True), \
                patch.object(health_api, "schema_status", return_value=status), \
                patch.object(health_api, "current_user", return_value=user):
            handler.do_GET()
        return captured["code"], captured["payload"]

    def test_health_hides_details_from_anonymous_callers(self):
        status = {"ready": False, "version": "007", "required_version": "008", "failed_checks": ["lead_sources"]}
        code, payload = self._health(status, None)
        self.assertEqual(code, 503)
        self.assertEqual(payload, {"ok": False, "ready": False})
        code, payload = self._health(status, {"role": "admin"})
        self.assertEqual(payload["schema"]["failed_checks"], ["lead_sources"])
        code, payload = self._health({**status, "ready": True, "failed_checks": []}, {"role": "sales"})
        self.assertEqual((code, payload), (200, {"ok": True, "ready": True}))


class LeadIdentityTests(unittest.TestCase):
    def test_place_id_prefers_verified_places_result(self):
        self.assertEqual(google_place_id(_lead("A", place_id="ChIJfromUrl0001")), "ChIJfromUrl0001")
        self.assertEqual(
            google_place_id(_lead("A", place_id="ChIJfromUrl0001", verified="ChIJverified001")),
            "ChIJverified001",
        )
        self.assertIsNone(google_place_id({"name": "A", "maps_url": "https://maps.example/a"}))

    def test_same_business_under_two_names_is_reported_not_merged(self):
        leads = [
            _lead("Dayıoğlu Dental", place_id="ChIJsamePlace001", phone="0216 330 09 99", website="https://www.kadikoydis.com/", lead_id=1),
            _lead("Dayıoğlu Diş Polikliniği", place_id="ChIJsamePlace001", phone="+90 216 330 0999", website="kadikoydis.com", lead_id=2),
            _lead("Başka Kafe", place_id="ChIJotherPlace01", website="https://instagram.com/baska", lead_id=3),
        ]
        report = find_identity_conflicts(leads)
        self.assertEqual(len(report["shared_place_id"]), 1)
        self.assertEqual({item["id"] for item in report["shared_place_id"][0]["leads"]}, {1, 2})
        self.assertEqual(report["shared_phone"][0]["key"], "2163300999")
        self.assertEqual(report["shared_website"][0]["key"], "kadikoydis.com")
        self.assertEqual(report["lead_count"], 3)

    def test_place_recorded_for_another_lead_is_flagged(self):
        leads = [_lead("Twin", place_id="ChIJsamePlace001", lead_id=2), _lead("New", place_id="ChIJnewPlace0001", lead_id=3)]
        sources = [{"lead_id": 1, "provider": "google_places", "provider_id": "ChIJsamePlace001"}]
        report = find_identity_conflicts(leads, sources)
        self.assertEqual([item["id"] for item in report["place_owned_elsewhere"]], [2])
        self.assertEqual([item["id"] for item in report["place_not_recorded"]], [3])

    def test_sync_external_id_matches_report_algorithm(self):
        lead = {"name": " Demo Cafe ", "city": "Bursa"}
        self.assertEqual(_lead_row(lead)["external_id"], lead_external_id(lead))

    def test_postgrest_in_list_quotes_reserved_characters(self):
        self.assertEqual(_in_list(['A, "B"', "C\\D"]), "%28%22A%2C%20%5C%22B%5C%22%22%2C%22C%5C%5CD%22%29")

    def test_report_script_runs_offline_without_writing(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/lead_identity_report.py"), "--file", str(SAMPLE), "--json"],
            capture_output=True, text=True, check=True, cwd=ROOT,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["lead_count"], len(json.loads(SAMPLE.read_text(encoding="utf-8"))))
        # The sample stores one invented clinic twice on purpose.
        self.assertEqual([group["key"] for group in report["shared_place_id"]], ["ChIJsynthetic000002"])
        self.assertIn("shared_place_id", report)


class SchemaBundleTests(unittest.TestCase):
    def test_schema_sql_is_built_from_migrations(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_schema.py"), "--check"],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
