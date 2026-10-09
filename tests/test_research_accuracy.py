"""WP07: Places matching gates and the effective lead snapshot."""

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx

import api.lead_ai as lead_ai_api
import api.leads as leads_api
import api.place_refresh as place_refresh_api
import api.workspace as workspace_api
from src.activity import encode_manual_note, manual_verification_from_event
from src.integrations.google_places import (
    ambiguous_candidate_ids,
    merge_place_result,
    search_place,
    select_candidate,
)
from src.lead_facts import apply_effective_facts, build_lead_facts
from src.workflow import build_lead_workflow
import test_access_policy as access
from test_access_policy import ADMIN, ALI, FakeStore

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)


def _place(place_id, name, address, *, phone=None, website=None, rating=None):
    return {
        "id": place_id,
        "displayName": {"text": name},
        "formattedAddress": address,
        "googleMapsUri": f"https://maps.google.com/?cid={place_id}",
        "nationalPhoneNumber": phone,
        "websiteUri": website,
        "rating": rating,
        "userRatingCount": 10 if rating else None,
    }


class FakePlaces:
    """httpx transport answering Places details and text search."""

    def __init__(self, *, details=None, search=None, status=200):
        self.details = details or {}
        self.search = search or []
        self.status = status
        self.calls = []

    def __call__(self, request):
        self.calls.append((request.method, request.url.path))
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": "boom"}})
        if request.method == "GET":
            place_id = request.url.path.rsplit("/", 1)[-1]
            place = self.details.get(place_id)
            return httpx.Response(200, json=place) if place else httpx.Response(404, json={})
        return httpx.Response(200, json={"places": self.search})

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self))


class PlacesMatchingTests(unittest.TestCase):
    lead = {"name": "Demo Cafe", "city": "Bursa Nilüfer", "phone": "0224 111 22 33"}

    def test_same_name_in_another_city_is_rejected(self):
        decision = select_candidate(self.lead, [_place("ankara", "Demo Cafe", "Kızılay, Çankaya/Ankara, Türkiye")])
        self.assertEqual(decision["status"], "not_matched")
        self.assertEqual(decision["reason"], "location_conflict")

    def test_two_branches_in_the_same_district_need_a_person(self):
        decision = select_candidate(self.lead, [
            _place("a", "Demo Cafe", "Özlüce, 16110 Nilüfer/Bursa, Türkiye"),
            _place("b", "Demo Cafe", "Görükle, 16285 Nilüfer/Bursa, Türkiye"),
        ])
        self.assertEqual(decision["status"], "ambiguous")
        self.assertEqual(decision["reason"], "close_candidates")
        self.assertEqual({item["place_id"] for item in decision["candidates"]}, {"a", "b"})

    def test_same_name_in_another_district_is_not_accepted_automatically(self):
        decision = select_candidate(self.lead, [_place("osm", "Demo Cafe", "Osmangazi/Bursa, Türkiye")])
        self.assertEqual(decision["status"], "ambiguous")
        self.assertEqual(decision["reason"], "other_district")

    def test_the_right_district_beats_another_district(self):
        decision = select_candidate(self.lead, [
            _place("osm", "Demo Cafe", "Osmangazi/Bursa, Türkiye"),
            _place("nil", "Demo Cafe", "Nilüfer/Bursa, Türkiye"),
        ])
        self.assertEqual(decision["status"], "verified")
        self.assertEqual(decision["match"]["candidate"]["id"], "nil")

    def test_turkish_dotless_i_still_matches_the_district(self):
        lead = {"name": "Yuka Dükkan", "city": "Istanbul Kadikoy"}
        decision = select_candidate(lead, [_place("y", "Yuka Dükkan", "Caferağa, 34710 Kadıköy/İstanbul, Türkiye")])
        self.assertEqual(decision["status"], "verified")
        self.assertEqual(decision["match"]["location_match"], "district")

    def test_maps_address_not_the_scan_area_says_where_the_business_is(self):
        # Scanned under "Beşiktaş", but Maps puts the business in Fatih.
        lead = {"name": "Seabreeze Lounge", "city": "Istanbul Besiktas", "address": "Divan-I Ali Sok. No:9, 34126 Fatih/İstanbul"}
        self.assertEqual(
            select_candidate(lead, [_place("f", "Seabreeze Lounge", "Mimar Hayrettin, 34126 Fatih/İstanbul, Türkiye")])["status"],
            "verified",
        )
        self.assertEqual(
            select_candidate(lead, [_place("b", "Seabreeze Lounge", "Bebek, 34342 Beşiktaş/İstanbul, Türkiye")])["reason"],
            "other_district",
        )

    def test_address_without_a_province_is_unknown_not_a_conflict(self):
        decision = select_candidate(self.lead, [_place("x", "Demo Cafe", "İskele Cad. No:10")])
        self.assertEqual((decision["status"], decision["reason"]), ("ambiguous", "location_unknown"))

    def test_phone_evidence_settles_two_branches(self):
        decision = select_candidate(self.lead, [
            _place("a", "Demo Cafe", "Nilüfer/Bursa, Türkiye", phone="0224 999 99 99"),
            _place("b", "Demo Cafe", "Nilüfer/Bursa, Türkiye", phone="(0224) 111 22 33"),
        ])
        self.assertEqual(decision["status"], "verified")
        self.assertEqual(decision["match"]["candidate"]["id"], "b")
        self.assertIn("phone", decision["match"]["evidence"])

    def test_phone_match_accepts_a_differently_listed_name(self):
        decision = select_candidate(self.lead, [
            _place("b", "Demo Kafe & Pastane", "Nilüfer/Bursa, Türkiye", phone="0224 111 22 33"),
        ])
        self.assertEqual(decision["status"], "verified")

    def test_known_place_id_is_refreshed_without_a_search(self):
        lead = {**self.lead, "maps_url": "https://www.google.com/maps/place/x/data=!4m7!3m6!19sChIJknownPlace01"}
        places = FakePlaces(details={"ChIJknownPlace01": _place("ChIJknownPlace01", "Demo Cafe", "Nilüfer/Bursa", rating=4.5)})
        with patch("src.integrations.google_places.env", return_value="key"):
            result = search_place(lead, client=places.client())
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["match_method"], "place_id")
        self.assertEqual(places.calls, [("GET", "/v1/places/ChIJknownPlace01")])

    def test_gone_place_id_falls_back_to_a_gated_search(self):
        lead = {**self.lead, "research": {"google_places": {"status": "verified", "place_id": "ChIJgonePlace001"}}}
        places = FakePlaces(search=[_place("ankara", "Demo Cafe", "Çankaya/Ankara")])
        with patch("src.integrations.google_places.env", return_value="key"):
            result = search_place(lead, client=places.client())
        self.assertEqual(result["status"], "not_matched")
        self.assertEqual(result["previous_place_id"], "ChIJgonePlace001")
        self.assertEqual([method for method, _ in places.calls], ["GET", "POST"])

    def test_provider_error_is_reported_not_raised(self):
        with patch("src.integrations.google_places.env", return_value="key"):
            result = search_place(self.lead, client=FakePlaces(status=500).client())
        self.assertEqual(result["status"], "provider_error")
        self.assertEqual(result["error"], "HTTP 500")

    def test_a_failed_lookup_keeps_the_verified_place(self):
        lead = {
            "name": "Demo Cafe", "rating": 4.5,
            "research": {"google_places": {"status": "verified", "place_id": "ChIJkeep", "refreshed_at": "2026-09-01T00:00:00+00:00"}},
        }
        merged = merge_place_result(lead, {"status": "not_matched", "reason": "location_conflict", "attempted_at": "2026-10-08T09:00:00+00:00"})
        places = merged["research"]["google_places"]
        self.assertEqual((places["status"], places["place_id"]), ("verified", "ChIJkeep"))
        self.assertEqual(places["last_attempt"]["reason"], "location_conflict")
        self.assertEqual(merged["rating"], 4.5)

    def test_ambiguous_candidates_are_the_only_manual_choices(self):
        lead = merge_place_result({"name": "Demo Cafe"}, {
            "status": "ambiguous", "reason": "close_candidates", "attempted_at": "2026-10-08T09:00:00+00:00",
            "candidates": [{"place_id": "a"}, {"place_id": "b"}],
        })
        self.assertEqual(ambiguous_candidate_ids(lead), {"a", "b"})


class PlaceRefreshEndpointTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.store.leads[3].update({"name": "Own Active", "city": "Bursa Nilüfer"})
        self.upserts = []
        self.owner = None

    def _post(self, body, search_result):
        calls = {}

        def fake_search(lead, *, place_id=None, verified_by=None):
            calls.update(place_id=place_id, verified_by=verified_by)
            return dict(search_result)

        captured = {}
        handler = place_refresh_api.handler.__new__(place_refresh_api.handler)
        handler.path, handler.headers = "/api/place_refresh", {}
        with patch.object(place_refresh_api, "require_auth", return_value=ALI), \
                patch.object(place_refresh_api, "read_json", return_value=body), \
                patch.object(place_refresh_api, "is_configured", return_value=True), \
                patch.object(place_refresh_api, "fetch_lead_by_name", self.store.fetch_lead_by_name), \
                patch.object(place_refresh_api, "fetch_lead_assignments", self.store.fetch_lead_assignments), \
                patch.object(place_refresh_api, "fetch_place_owner", lambda place_id: self.owner), \
                patch.object(place_refresh_api, "search_place", fake_search), \
                patch.object(place_refresh_api, "upsert_leads", self.upserts.extend), \
                patch.object(place_refresh_api, "insert_audit_event", lambda **_: None), \
                patch.object(place_refresh_api, "send_json", lambda _h, status, payload, **_: captured.update(status=status, payload=payload)):
            handler.do_POST()
        return captured["status"], captured["payload"], calls

    def test_choice_must_be_one_of_the_candidates(self):
        status, _, _ = self._post({"lead_name": "Own Active", "place_id": "ChIJnotOffered"}, {"status": "verified"})
        self.assertEqual(status, 400)
        self.assertEqual(self.upserts, [])

    def test_chosen_candidate_is_recorded_with_the_person(self):
        self.store.leads[3]["research"] = {"google_places": {"status": "ambiguous", "candidates": [{"place_id": "ChIJpick"}]}}
        status, payload, calls = self._post(
            {"lead_name": "Own Active", "place_id": "ChIJpick"},
            {"status": "verified", "place_id": "ChIJpick", "match_method": "manual_selection", "attempted_at": "2026-10-08T09:00:00+00:00"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["place"]["status"], "verified")
        self.assertEqual(calls, {"place_id": "ChIJpick", "verified_by": ALI["sub"]})

    def test_place_owned_by_another_lead_is_not_copied(self):
        self.owner = 99
        status, payload, _ = self._post(
            {"lead_name": "Own Active"},
            {"status": "verified", "place_id": "ChIJdup", "phone": "1", "attempted_at": "2026-10-08T09:00:00+00:00"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["place"]["reason"], "place_owned_by_other_lead")
        stored = self.upserts[0]["research"]["google_places"]
        self.assertEqual(stored["status"], "ambiguous")
        self.assertNotIn("phone", stored)

    def test_provider_error_writes_nothing(self):
        status, _, _ = self._post({"lead_name": "Own Active"}, {"status": "provider_error", "error": "HTTP 503"})
        self.assertEqual(status, 502)
        self.assertEqual(self.upserts, [])

    def test_cron_skips_recent_definitive_attempts_but_retries_errors(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        rows = [
            {"name": "Not matched lately", "refreshed_at": None, "attempted_at": recent, "attempt_status": "not_matched"},
            {"name": "Errored lately", "refreshed_at": old, "attempted_at": recent, "attempt_status": "provider_error"},
            {"name": "Fresh", "refreshed_at": recent, "attempted_at": recent, "attempt_status": "verified"},
        ]
        picked = []
        handler = place_refresh_api.handler.__new__(place_refresh_api.handler)
        handler.path, handler.headers = "/api/place_refresh", {"Authorization": "Bearer s3cret"}
        with patch.object(place_refresh_api, "env", lambda key, default=None: "s3cret" if key == "CRON_SECRET" else default), \
                patch.object(place_refresh_api, "is_configured", return_value=True), \
                patch.object(place_refresh_api, "fetch_places_refresh_state", return_value=rows), \
                patch.object(place_refresh_api, "fetch_leads_by_names", lambda names: picked.extend(names) or []), \
                patch.object(place_refresh_api, "insert_run_log", lambda **_: None), \
                patch.object(place_refresh_api, "send_json", lambda *_a, **_k: None):
            handler.do_GET()
        self.assertEqual(picked, ["Errored lately"])


def _manual(event_time, **sections):
    payload = {
        name: {"checked": False, "status": "unknown"}
        for name in ("google", "instagram", "menu", "website")
    }
    payload.update(sections)
    note = encode_manual_note({"version": 1, "kind": "manual_verification", **payload, "notes": None})
    return manual_verification_from_event({"note": note, "happened_at": event_time, "actor_email": "ali@example.com"})


def _audited_lead():
    finding = {
        "code": "website.placeholder", "status": "confirmed", "confidence": 98, "category": "website",
        "source_url": "http://old-site.example/", "service_slugs": ["website_creation"],
        "recommendation_strength": "direct", "finding_type": "gap", "title": "Varsayılan sayfa",
    }
    social = {
        "code": "social.instagram_absent", "status": "likely", "confidence": 72, "category": "social",
        "source_url": "https://maps.google.com/x", "service_slugs": ["social_media"],
        "recommendation_strength": "conditional", "finding_type": "gap", "title": "Instagram yok",
    }
    return {
        "name": "Örnek Klinik", "sector": "health", "category": "Diş kliniği", "phone": "0216 000 00 00",
        "rating": 4.1, "review_count": 30, "last_analyzed": "2026-09-20 10:00",
        "website": {"has_website": True, "website_url": "http://old-site.example/", "final_url": "http://old-site.example/"},
        "social": {"instagram_url": None, "lookup_status": "not_found"},
        "audit": {"version": 4, "findings": [finding, social]},
        "audit_findings": [finding, social],
    }


class EffectiveFactsTests(unittest.TestCase):
    def test_manual_website_correction_is_the_effective_value_everywhere(self):
        lead = {**_audited_lead(), "manual_verification": _manual(
            "2026-10-07T09:00:00+00:00", website={"checked": True, "status": "working", "url": "https://new-site.example"},
        )}
        effective = apply_effective_facts(lead, now=NOW)
        self.assertEqual(effective["website"]["website_url"], "https://new-site.example")
        fact = effective["facts"]["website_url"]
        self.assertEqual((fact["source"], fact["verified_by"]), ("manual", "ali@example.com"))
        self.assertEqual(fact["conflicts"][0]["value"], "http://old-site.example/")
        # The old site's audit is not evidence about the new one.
        self.assertIn("website.placeholder", effective["audit"]["superseded_codes"])
        self.assertNotIn("website_creation", [service["slug"] for service in effective["matched_services"]])
        # The stored lead is untouched.
        self.assertEqual(lead["website"]["website_url"], "http://old-site.example/")

    def test_manual_not_found_is_negative_evidence(self):
        lead = _audited_lead()
        lead["website"] = {"has_website": None, "website_url": None}
        lead["audit"]["findings"] = lead["audit_findings"] = []
        lead["manual_verification"] = _manual("2026-10-07T09:00:00+00:00", website={"checked": True, "status": "not_found"})
        effective = apply_effective_facts(lead, now=NOW)
        self.assertEqual(effective["facts"]["website_url"]["status"], "absent")
        self.assertFalse(effective["website"]["has_website"])
        self.assertIn("website_creation", [service["slug"] for service in effective["matched_services"]])

    def test_unknown_is_not_negative_evidence(self):
        lead = {**_audited_lead(), "manual_verification": _manual(
            "2026-10-07T09:00:00+00:00", website={"checked": True, "status": "unknown"},
        )}
        effective = apply_effective_facts(lead, now=NOW)
        self.assertEqual(effective["facts"]["website_url"]["source"], "scrape")
        self.assertNotIn("superseded_codes", effective["audit"])

    def test_found_instagram_supersedes_the_absence_finding(self):
        lead = {**_audited_lead(), "manual_verification": _manual(
            "2026-10-07T09:00:00+00:00", instagram={"checked": True, "status": "active", "url": "https://instagram.com/ornek"},
        )}
        effective = apply_effective_facts(lead, now=NOW)
        self.assertIn("social.instagram_absent", effective["audit"]["superseded_codes"])
        self.assertEqual(effective["social"]["instagram_url"], "https://instagram.com/ornek")
        self.assertTrue(effective["social"]["has_instagram"])

    def test_newer_google_reading_wins_and_scrape_is_only_a_fallback(self):
        lead = {
            **_audited_lead(),
            "research": {"google_places": {"status": "verified", "rating": 4.6, "refreshed_at": "2026-10-01T00:00:00+00:00"}},
            "manual_verification": _manual("2026-10-05T00:00:00+00:00", google={"checked": True, "status": "found", "rating": 4.4}),
        }
        self.assertEqual(build_lead_facts(lead, now=NOW)["rating"]["source"], "manual")
        lead["research"]["google_places"]["refreshed_at"] = "2026-10-06T00:00:00+00:00"
        rating = build_lead_facts(lead, now=NOW)["rating"]
        self.assertEqual((rating["source"], rating["value"]), ("google_places", 4.6))
        self.assertEqual({item["source"] for item in rating["conflicts"]}, {"manual", "scrape"})

    def test_differing_places_phone_is_shown_as_a_conflict(self):
        lead = {**_audited_lead(), "research": {"google_places": {
            "status": "verified", "phone": "0216 555 55 55", "refreshed_at": "2026-10-01T00:00:00+00:00",
        }}}
        phone = build_lead_facts(lead, now=NOW)["phone"]
        self.assertEqual(phone["value"], "0216 555 55 55")
        self.assertEqual(phone["conflicts"][0]["value"], "0216 000 00 00")

    def test_legacy_lead_keeps_trigger_based_matching(self):
        lead = {"name": "Eski", "sector": "health", "website": {"has_website": False, "lookup_status": "not_found"},
                "matched_services": [{"slug": "website_creation"}],
                "manual_verification": _manual("2026-10-07T09:00:00+00:00", instagram={"checked": True, "status": "not_found"})}
        self.assertEqual(apply_effective_facts(lead, now=NOW)["matched_services"], [{"slug": "website_creation"}])

    def test_places_maps_link_is_not_a_conflict(self):
        lead = {**_audited_lead(), "maps_url": "https://www.google.com/maps/place/x", "research": {"google_places": {
            "status": "verified", "maps_url": "https://maps.google.com/?cid=1", "refreshed_at": "2026-10-01T00:00:00+00:00",
        }}}
        self.assertEqual(build_lead_facts(lead, now=NOW)["maps_url"]["conflicts"], [])

    def test_expired_manual_check_must_be_done_again(self):
        checks = {
            "google": {"checked": True, "status": "found"},
            "instagram": {"checked": True, "status": "active"},
            "website": {"checked": True, "status": "working"},
        }
        fresh = build_lead_workflow({**_audited_lead(), "manual_verification": _manual("2026-09-01T00:00:00+00:00", **checks)}, now=NOW)
        self.assertTrue(fresh["checks_complete"])
        old = build_lead_workflow({**_audited_lead(), "manual_verification": _manual("2026-06-01T00:00:00+00:00", **checks)}, now=NOW)
        self.assertFalse(old["checks_complete"])
        self.assertTrue(all(item["stale"] for item in old["checks"]))
        self.assertIn("Website (süresi doldu)", old["missing"])


class SnapshotConsumersTests(unittest.TestCase):
    """Workspace, detail and AI read the same effective snapshot."""

    _call = access.AccessPolicyTests._call

    def setUp(self):
        self.store = FakeStore()
        self.schema = {"ready": True}
        lead = next(item for item in self.store.leads if item["name"] == "Own Active")
        lead.update({key: value for key, value in _audited_lead().items() if key != "name"})
        lead["matched_services"] = [{"slug": "website_creation"}]
        self.store.states = {lead["lead_id"]: {"latest_manual_verification": {
            "id": 50, "lead_name": "Own Active", "action": "manual_verification_saved",
            "note": encode_manual_note({
                "version": 1, "kind": "manual_verification",
                "website": {"checked": True, "status": "working", "url": "https://new-site.example"},
                "google": {"checked": False, "status": "unknown"}, "instagram": {"checked": False, "status": "unknown"},
                "menu": {"checked": False, "status": "unknown"}, "notes": None,
            }),
            "happened_at": datetime.now(timezone.utc).isoformat(), "actor_email": ALI["sub"],
        }}}

    def test_workspace_and_detail_agree_on_the_corrected_website(self):
        _, workspace = self._call(workspace_api, "GET", ALI)
        listed = next(item for item in workspace["leads"] if item["name"] == "Own Active")
        _, detail = self._call(leads_api, "GET", ALI, path="/api/leads?name=Own%20Active")
        for lead in (listed, detail["lead"]):
            self.assertEqual(lead["website"]["website_url"], "https://new-site.example")
            self.assertEqual(lead["facts"]["website_url"]["source"], "manual")
        self.assertEqual(listed["workflow"]["stage"], detail["lead"]["workflow"]["stage"])

    def test_ai_uses_the_snapshot_but_stores_only_ai_fields(self):
        seen, stored = {}, []

        def fake_enrich(lead):
            seen["website"] = lead["website"]["website_url"]
            return {**lead, "ai_report": "rapor", "ai_email": None, "ai_tier": "flash", "ai_prompt_version": "test", "research_brief": "brief"}

        with patch.object(lead_ai_api, "require_lead_access", lambda user, name: None), \
                patch.object(lead_ai_api, "enrich_ai_fields", fake_enrich), \
                patch.object(lead_ai_api, "upsert_leads", stored.extend):
            status, payload = self._call(lead_ai_api, "POST", ADMIN, body={"name": "Own Active"})
        self.assertEqual(status, 200, payload)
        self.assertEqual(seen["website"], "https://new-site.example")
        self.assertEqual(stored[0]["website"]["website_url"], "http://old-site.example/")
        self.assertEqual(stored[0]["ai_report"], "rapor")
        self.assertNotIn("facts", stored[0])
        self.assertNotIn("manual_verification", stored[0])


if __name__ == "__main__":
    unittest.main()
