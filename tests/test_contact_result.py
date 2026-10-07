"""Contact results go through one database command (migration 009)."""

import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import api.outreach as outreach_api
from src.activity import contact_request_hash
from src.storage.supabase import CommandRejected
from src.workflow import build_lead_workflow

ALI = {"sub": "ali@example.com", "role": "sales", "name": "Ali"}
KEY = "0b6f4f3e-8a1c-4c2e-9d55-6a3f2b1c9e10"


class ContactResultApiTests(unittest.TestCase):
    def _post(self, body, *, rpc_result=None, rpc_error=None, user=ALI):
        handler = outreach_api.handler.__new__(outreach_api.handler)
        raw = json.dumps(body).encode()
        handler.path = "/api/outreach"
        handler.headers = {"Content-Length": str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        captured = {"calls": []}

        def fake_send_json(_handler, status, payload, **_kwargs):
            captured.update(status=status, payload=payload)

        def fake_record(**kwargs):
            captured["calls"].append(kwargs)
            if rpc_error:
                raise rpc_error
            return rpc_result or {
                "event_id": 9, "lead_status": "follow_up", "lead_revision": 4,
                "follow_up_at": "2026-10-08T07:00:00+00:00", "happened_at": "2026-10-07T09:00:00+00:00",
                "actor_email": "ali@example.com", "replayed": False,
            }

        def fail(_handler, exc, **_kwargs):
            raise exc

        with patch.object(outreach_api, "send_json", fake_send_json), \
                patch.object(outreach_api, "send_internal_error", fail), \
                patch.object(outreach_api, "require_auth", return_value=user), \
                patch.object(outreach_api, "require_lead_access", return_value=None), \
                patch.object(outreach_api, "supabase_enabled", return_value=True), \
                patch.object(outreach_api, "record_contact_result", fake_record), \
                patch.object(outreach_api, "insert_outreach_event", side_effect=AssertionError("legacy write path used")):
            handler.do_POST()
        return captured

    def _body(self, **overrides):
        body = {
            "lead_name": "Demo Cafe", "action": "contact_result_recorded", "channel": "phone",
            "outcome": "no_answer", "note": "Açmadı", "idempotency_key": KEY, "expected_revision": 3,
        }
        body.update(overrides)
        return body

    def test_contact_result_is_one_command_with_session_actor(self):
        result = self._post(self._body(actor_email="someone-else@example.com"))
        self.assertEqual(result["status"], 200)
        self.assertEqual(len(result["calls"]), 1)
        call = result["calls"][0]
        self.assertEqual(call["actor_email"], "ali@example.com")
        self.assertFalse(call["actor_is_admin"])
        self.assertEqual(call["lead_status"], "follow_up")
        self.assertEqual(call["assignment_status"], "active")
        self.assertEqual(call["expected_revision"], 3)
        self.assertEqual(call["idempotency_key"], KEY)
        self.assertEqual(result["payload"]["lead_revision"], 4)
        self.assertEqual(result["payload"]["event"]["outcome"], "no_answer")

    def test_won_closes_the_assignment(self):
        call = self._post(self._body(outcome="won"))["calls"][0]
        self.assertEqual((call["lead_status"], call["assignment_status"]), ("converted", "done"))
        self.assertIsNone(call["activity"]["follow_up_at"])

    def test_missing_or_malformed_idempotency_key_is_rejected(self):
        for key in (None, "dashboard-1728290000000"):
            result = self._post(self._body(idempotency_key=key))
            self.assertEqual(result["status"], 400)
            self.assertEqual(result["calls"], [])

    def test_expected_revision_must_be_an_integer(self):
        for value in ("3", True, 2.5):
            self.assertEqual(self._post(self._body(expected_revision=value))["status"], 400)

    def test_command_rejections_keep_their_status_and_code(self):
        for status, code in ((409, "LEAD_VERSION_CONFLICT"), (403, "LEAD_NOT_ASSIGNED"), (409, "IDEMPOTENCY_KEY_REUSED")):
            result = self._post(self._body(), rpc_error=CommandRejected(status, code))
            self.assertEqual(result["status"], status)
            self.assertEqual(result["payload"]["code"], code)

    def test_request_hash_ignores_the_computed_default_follow_up(self):
        body = self._body()
        first = contact_request_hash("Demo Cafe", body)
        self.assertEqual(first, contact_request_hash("Demo Cafe", dict(body)))
        self.assertNotEqual(first, contact_request_hash("Demo Cafe", {**body, "outcome": "won"}))
        self.assertNotEqual(first, contact_request_hash("Demo Cafe", {**body, "expected_revision": 4}))


class WrongNumberWorkflowTests(unittest.TestCase):
    def test_wrong_number_sends_the_lead_back_to_verification(self):
        now = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
        event = {"lead_name": "Demo Cafe", "action": "contact_result_recorded", "outcome": "wrong_number",
                 "happened_at": "2026-10-07T08:00:00+00:00"}
        workflow = build_lead_workflow({"name": "Demo Cafe", "status": "missing_info"}, [event], now=now)
        self.assertEqual(workflow["stage"], "verification_required")


if __name__ == "__main__":
    unittest.main()
