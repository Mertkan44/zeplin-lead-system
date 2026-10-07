"""Lead access regressions: a handed-over lead must disappear for its old owner
on every read path, while admins and the current owner keep access."""

import io
import json
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import patch

import api.assignments as assignments_api
import api.leads as leads_api
import api.outreach as outreach_api
import api.workspace as workspace_api
from src.auth import readable_lead_names
from src.workflow import build_lead_workflow, build_team_performance

ADMIN = {"sub": "admin@example.com", "role": "admin", "name": "Admin"}
ALI = {"sub": "ali@example.com", "role": "sales", "name": "Ali"}
BERK = {"sub": "berk@example.com", "role": "sales", "name": "Berk"}


def _assignment(row_id, lead, email, status):
    return {"id": row_id, "lead_name": lead, "user_email": email, "status": status, "meta": {}}


class FakeStore:
    """In-memory stand-in for the Supabase rows the access policy reads."""

    def __init__(self):
        self.leads = [
            {"name": name, "status": "contacted", "scoring": {"score": 50}}
            for name in ("Handed Over", "Own Closed", "Closed Then Reassigned", "Own Active")
        ]
        self.assignments = [
            # Ali owned it, admin moved it to Berk: Ali's row is archived.
            _assignment(1, "Handed Over", ALI["sub"], "archived"),
            _assignment(2, "Handed Over", BERK["sub"], "active"),
            # Ali closed it and nobody else owns it.
            _assignment(3, "Own Closed", ALI["sub"], "done"),
            # Ali closed it, then admin gave it to Berk; the RPC leaves Ali's row "done".
            _assignment(4, "Closed Then Reassigned", ALI["sub"], "done"),
            _assignment(5, "Closed Then Reassigned", BERK["sub"], "active"),
            _assignment(6, "Own Active", ALI["sub"], "active"),
        ]
        self.events = [
            {"id": index, "lead_name": lead["name"], "action": "note_added", "note": "x",
             "happened_at": "2026-10-01T09:00:00+00:00", "actor_email": BERK["sub"]}
            for index, lead in enumerate(self.leads)
        ]
        self.updated = []

    def fetch_lead_assignments(self, *, user_email=None, lead_name=None, status=None, limit=500):
        return [
            dict(item) for item in self.assignments
            if (user_email is None or item["user_email"] == user_email)
            and (lead_name is None or item["lead_name"] == lead_name)
            and (status is None or item["status"] == status)
        ][:limit]

    def fetch_active_assignments_for_leads(self, lead_names):
        return [
            dict(item) for item in self.assignments
            if item["lead_name"] in set(lead_names) and item["status"] == "active"
        ]

    def fetch_lead_assignment_by_id(self, assignment_id):
        return next((dict(item) for item in self.assignments if item["id"] == assignment_id), None)

    def update_lead_assignment(self, assignment_id, *, status, meta=None, due_at=None):
        self.updated.append((assignment_id, status))


class AccessPolicyTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.schema = {"ready": False, "version": "007", "required_version": "008", "failed_checks": ["lead_sources"]}

    def _call(self, module, method, user, *, path="/api/x", body=None):
        handler = module.handler.__new__(module.handler)
        raw = json.dumps(body or {}).encode()
        handler.path = path
        handler.headers = {"Content-Length": str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        captured = {}

        def fake_send_json(_handler, status, payload, **_kwargs):
            captured["status"] = status
            captured["payload"] = payload

        def fail(_handler, exc, **_kwargs):
            raise exc

        store = self.store
        with ExitStack() as stack:
            stack.enter_context(patch.object(module, "send_json", fake_send_json))
            stack.enter_context(patch.object(module, "send_internal_error", fail))
            stack.enter_context(patch.object(module, "require_auth", return_value=user))
            if hasattr(module, "supabase_enabled"):
                stack.enter_context(patch.object(module, "supabase_enabled", return_value=True))
            for name in ("fetch_lead_assignments", "fetch_active_assignments_for_leads", "fetch_lead_assignment_by_id"):
                stack.enter_context(patch(f"src.storage.supabase.{name}", getattr(store, name)))
                if hasattr(module, name):
                    stack.enter_context(patch.object(module, name, getattr(store, name)))
            if hasattr(module, "fetch_leads_full"):
                stack.enter_context(
                    patch.object(module, "fetch_leads_full", lambda limit=500: [dict(lead) for lead in store.leads])
                )
            if hasattr(module, "fetch_outreach_events"):
                stack.enter_context(
                    patch.object(module, "fetch_outreach_events", lambda limit=500: [dict(event) for event in store.events])
                )
            if hasattr(module, "update_lead_assignment"):
                stack.enter_context(patch.object(module, "update_lead_assignment", store.update_lead_assignment))
            if hasattr(module, "insert_audit_event"):
                stack.enter_context(patch.object(module, "insert_audit_event", lambda **_kwargs: None))
            if hasattr(module, "schema_status"):
                stack.enter_context(patch.object(module, "schema_status", lambda: dict(self.schema)))
            if module is workspace_api:
                stack.enter_context(patch.object(module, "build_research_brief", lambda lead: {}))
                stack.enter_context(patch.object(module, "build_sales_playbook", lambda lead, sender_name=None: {}))
            getattr(handler, f"do_{method}")()
        return captured["status"], captured["payload"]

    def test_readable_names_exclude_handed_over_and_reassigned_leads(self):
        names = readable_lead_names(ALI["sub"], self.store.assignments)
        self.assertEqual(names, {"Own Closed", "Own Active"})
        self.assertEqual(
            readable_lead_names(BERK["sub"], self.store.assignments),
            {"Handed Over", "Closed Then Reassigned"},
        )

    def test_snoozed_assignment_is_readable_only_without_another_owner(self):
        rows = [
            _assignment(1, "Paused", ALI["sub"], "snoozed"),
            _assignment(2, "Paused Elsewhere", ALI["sub"], "snoozed"),
            _assignment(3, "Paused Elsewhere", BERK["sub"], "active"),
        ]
        self.assertEqual(readable_lead_names(ALI["sub"], rows), {"Paused"})

    def test_workspace_hides_handed_over_lead_from_previous_owner(self):
        status, payload = self._call(workspace_api, "GET", ALI, path="/api/workspace")
        self.assertEqual(status, 200)
        names = {lead["name"] for lead in payload["leads"]}
        self.assertEqual(names, {"Own Closed", "Own Active"})
        self.assertEqual({event["lead_name"] for event in payload["outreach"]}, names)
        self.assertEqual({item["lead_name"] for item in payload["assignments"]}, names)
        self.assertNotIn("archived", {item["status"] for item in payload["assignments"]})

    def test_workspace_gives_new_owner_and_admin_access(self):
        _, payload = self._call(workspace_api, "GET", BERK, path="/api/workspace")
        self.assertEqual({lead["name"] for lead in payload["leads"]}, {"Handed Over", "Closed Then Reassigned"})
        _, payload = self._call(workspace_api, "GET", ADMIN, path="/api/workspace")
        self.assertEqual(len(payload["leads"]), 4)

    def test_only_admins_see_schema_readiness_in_workspace(self):
        _, payload = self._call(workspace_api, "GET", ADMIN, path="/api/workspace")
        self.assertEqual(payload["schema"]["failed_checks"], ["lead_sources"])
        _, payload = self._call(workspace_api, "GET", ALI, path="/api/workspace")
        self.assertIsNone(payload["schema"])

    def test_lead_and_outreach_lists_use_the_same_scope(self):
        _, leads = self._call(leads_api, "GET", ALI, path="/api/leads")
        self.assertEqual({lead["name"] for lead in leads}, {"Own Closed", "Own Active"})
        _, events = self._call(outreach_api, "GET", ALI, path="/api/outreach?lead=Handed%20Over")
        self.assertEqual(events, [])

    def test_closed_lead_is_read_only_for_previous_owner(self):
        status, _ = self._call(
            outreach_api, "POST", ALI,
            body={"lead_name": "Own Closed", "action": "note_added", "note": "x"},
        )
        self.assertEqual(status, 403)

    def test_sales_user_cannot_revive_archived_assignment(self):
        status, _ = self._call(assignments_api, "PATCH", ALI, body={"id": 1, "status": "active"})
        self.assertEqual(status, 403)
        self.assertEqual(self.store.updated, [])

    def test_sales_user_cannot_reclaim_lead_owned_by_someone_else(self):
        status, _ = self._call(assignments_api, "PATCH", ALI, body={"id": 4, "status": "active"})
        self.assertEqual(status, 409)
        self.assertEqual(self.store.updated, [])

    def test_sales_user_can_reopen_own_unowned_lead(self):
        status, _ = self._call(assignments_api, "PATCH", ALI, body={"id": 3, "status": "active"})
        self.assertEqual(status, 200)
        self.assertEqual(self.store.updated, [(3, "active")])

    def test_invalid_assignment_status_is_a_client_error(self):
        status, _ = self._call(assignments_api, "PATCH", ALI, body={"id": 6, "status": "deleted"})
        self.assertEqual(status, 400)


class BusinessDayTests(unittest.TestCase):
    def test_team_day_boundary_uses_istanbul_time(self):
        # 01:30 in Istanbul on 2 Aug is still 1 Aug in UTC.
        now = datetime(2026, 8, 2, 6, 0, tzinfo=timezone.utc)
        rows = build_team_performance(
            [],
            [{
                "actor_email": "ali@example.com",
                "action": "contact_result_recorded",
                "channel": "phone",
                "outcome": "no_answer",
                "happened_at": "2026-08-01T22:30:00+00:00",
            }],
            now=now,
        )
        self.assertEqual(rows[0]["calls_today"], 1)

    def test_previous_istanbul_day_is_not_today(self):
        # 23:30 Istanbul on 1 Aug; at 06:00 Istanbul on 2 Aug it is yesterday.
        now = datetime(2026, 8, 2, 3, 0, tzinfo=timezone.utc)
        rows = build_team_performance(
            [],
            [{
                "actor_email": "ali@example.com",
                "action": "contact_result_recorded",
                "channel": "phone",
                "happened_at": "2026-08-01T20:30:00+00:00",
            }],
            now=now,
        )
        self.assertEqual(rows[0]["calls_today"], 0)

    def test_closed_lead_has_no_due_follow_up(self):
        now = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
        event = {
            "lead_name": "Demo Cafe",
            "action": "contact_result_recorded",
            "outcome": "no_answer",
            "follow_up_at": "2026-08-02T07:00:00+00:00",
            "happened_at": "2026-08-01T09:00:00+00:00",
        }
        workflow = build_lead_workflow({"name": "Demo Cafe", "status": "lost"}, [event], now=now)
        self.assertEqual(workflow["stage"], "closed")
        self.assertFalse(workflow["follow_up_due"])
        open_workflow = build_lead_workflow({"name": "Demo Cafe", "status": "contacted"}, [event], now=now)
        self.assertTrue(open_workflow["follow_up_due"])


if __name__ == "__main__":
    unittest.main()
