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
from src.auth import lead_read_scope
from src.workflow import build_lead_workflow, build_team_performance

ADMIN = {"sub": "admin@example.com", "role": "admin", "name": "Admin"}
ALI = {"sub": "ali@example.com", "role": "sales", "name": "Ali"}
BERK = {"sub": "berk@example.com", "role": "sales", "name": "Berk"}

# Every storage function the read paths may call; the fake answers all of them.
_STORAGE_FUNCTIONS = (
    "fetch_lead_assignments", "fetch_active_assignments_for_leads", "fetch_lead_assignment_by_id",
    "fetch_readable_leads", "fetch_all_leads", "fetch_leads_by_names", "fetch_lead_by_name",
    "fetch_lead_by_id", "fetch_all_assignments", "fetch_activity_states", "fetch_events_since",
    "fetch_event_page", "list_leads_page",
)


def _assignment(row_id, lead, email, status):
    return {"id": row_id, "lead_name": lead, "user_email": email, "status": status, "meta": {}}


class FakeStore:
    """In-memory stand-in for Supabase. fetch_readable_leads mirrors
    public.readable_leads; the SQL itself is tested in tests/sql/."""

    def __init__(self):
        self.leads = [
            {"lead_id": index + 1, "name": name, "status": "contacted", "scoring": {"score": 50}}
            for index, name in enumerate(("Handed Over", "Own Closed", "Closed Then Reassigned", "Own Active"))
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
            {"id": index + 1, "lead_name": lead["name"], "action": "note_added", "note": "x",
             "happened_at": "2026-10-01T09:00:00+00:00", "actor_email": BERK["sub"]}
            for index, lead in enumerate(self.leads)
        ]
        self.states = {}
        self.updated = []
        self.list_calls = []

    def fetch_readable_leads(self, email):
        rows = []
        for item in self.assignments:
            if item["user_email"] != email:
                continue
            other_owner = any(
                other["lead_name"] == item["lead_name"] and other["status"] == "active" and other["user_email"] != email
                for other in self.assignments
            )
            if item["status"] == "active" or (item["status"] in {"done", "snoozed"} and not other_owner):
                rows.append({"lead_name": item["lead_name"], "can_write": item["status"] == "active"})
        return rows

    def fetch_all_leads(self):
        return [dict(lead) for lead in self.leads]

    def fetch_leads_by_names(self, names):
        return [dict(lead) for lead in self.leads if lead["name"] in set(names)]

    def fetch_lead_by_name(self, name):
        return next((dict(lead) for lead in self.leads if lead["name"] == name), None)

    def fetch_lead_by_id(self, lead_id):
        return next((dict(lead) for lead in self.leads if lead["lead_id"] == lead_id), None)

    def fetch_all_assignments(self):
        return [dict(item) for item in self.assignments]

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

    def fetch_activity_states(self, lead_ids=None):
        return {key: value for key, value in self.states.items() if lead_ids is None or key in lead_ids}

    def fetch_events_since(self, since_iso, lead_names=None):
        return [
            dict(event) for event in self.events
            if lead_names is None or event["lead_name"] in set(lead_names)
        ]

    def fetch_event_page(self, *, lead_names, before_id, limit):
        rows = [
            dict(event) for event in self.events
            if (lead_names is None or event["lead_name"] in set(lead_names))
            and (before_id is None or event["id"] < before_id)
        ]
        return sorted(rows, key=lambda event: event["id"], reverse=True)[:limit]

    def list_leads_page(self, **kwargs):
        self.list_calls.append(kwargs)
        return {"items": [], "total": 0, "total_is_exact": True, "next_cursor": None}

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
            for name in _STORAGE_FUNCTIONS:
                stack.enter_context(patch(f"src.storage.supabase.{name}", getattr(store, name)))
                if hasattr(module, name):
                    stack.enter_context(patch.object(module, name, getattr(store, name)))
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

    def _scope(self, user):
        with patch("src.storage.supabase.fetch_readable_leads", self.store.fetch_readable_leads), \
                patch("src.storage.supabase.fetch_lead_assignments", self.store.fetch_lead_assignments):
            return lead_read_scope(user)

    def test_read_scope_excludes_handed_over_and_reassigned_leads(self):
        names, visible = self._scope(ALI)
        self.assertEqual(names, {"Own Closed", "Own Active"})
        self.assertNotIn("archived", {item["status"] for item in visible})
        self.assertEqual(self._scope(BERK)[0], {"Handed Over", "Closed Then Reassigned"})
        self.assertIsNone(self._scope(ADMIN))

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

    def test_metrics_count_only_the_readable_leads(self):
        self.store.events = [
            {"id": index + 1, "lead_name": lead["name"], "action": "contact_result_recorded", "outcome": "won",
             "happened_at": datetime.now(timezone.utc).isoformat()}
            for index, lead in enumerate(self.store.leads)
        ]
        status, payload = self._call(workspace_api, "GET", ALI, path="/api/workspace?view=metrics&period=7")
        self.assertEqual(status, 200)
        # Ali reads "Own Closed" and "Own Active" only.
        self.assertEqual(payload["metrics"]["lead_count"], 2)
        self.assertEqual(payload["metrics"]["sales"]["won_businesses"]["value"], 2)
        _, payload = self._call(workspace_api, "GET", ADMIN, path="/api/workspace?view=metrics&period=all")
        self.assertEqual(payload["metrics"]["sales"]["won_businesses"]["value"], 4)
        status, payload = self._call(workspace_api, "GET", ADMIN, path="/api/workspace?view=metrics&period=365")
        self.assertEqual(status, 400)

    def test_only_admins_see_schema_readiness_in_workspace(self):
        _, payload = self._call(workspace_api, "GET", ADMIN, path="/api/workspace")
        self.assertEqual(payload["schema"]["failed_checks"], ["lead_sources"])
        _, payload = self._call(workspace_api, "GET", ALI, path="/api/workspace")
        self.assertIsNone(payload["schema"])

    def test_detail_and_timeline_use_the_same_scope(self):
        status, _ = self._call(leads_api, "GET", ALI, path="/api/leads?name=Handed%20Over")
        self.assertEqual(status, 404)
        status, payload = self._call(leads_api, "GET", ALI, path="/api/leads?id=2")
        self.assertEqual((status, payload["lead"]["name"]), (200, "Own Closed"))
        _, payload = self._call(outreach_api, "GET", ALI, path="/api/outreach?lead=Handed%20Over")
        self.assertEqual(payload["items"], [])
        _, payload = self._call(outreach_api, "GET", ALI, path="/api/outreach")
        self.assertEqual({event["lead_name"] for event in payload["items"]}, {"Own Closed", "Own Active"})
        _, payload = self._call(outreach_api, "GET", ADMIN, path="/api/outreach?limit=2")
        self.assertEqual(([event["id"] for event in payload["items"]], payload["next_before"]), ([4, 3], 3))

    def test_list_passes_the_session_actor_and_validates_input(self):
        self._call(leads_api, "GET", ALI, path="/api/leads?limit=500&q=kafe&status=follow_up")
        call = self.store.list_calls[-1]
        self.assertEqual((call["actor_email"], call["is_admin"], call["limit"], call["search"]),
                         ("ali@example.com", False, 100, "kafe"))
        for bad in ("status=nope", "limit=x", "cursor=%%%"):
            status, _ = self._call(leads_api, "GET", ALI, path=f"/api/leads?{bad}")
            self.assertEqual(status, 400, bad)

    def test_list_cursor_round_trips(self):
        cursor = leads_api.encode_cursor({"priority": 87, "id": 1400})
        self.assertEqual(leads_api.decode_cursor(cursor), (87, 1400))
        self.assertEqual(leads_api.decode_cursor(leads_api.encode_cursor({"priority": None, "id": 5})), (None, 5))
        self._call(leads_api, "GET", ALI, path=f"/api/leads?cursor={cursor}")
        last = self.store.list_calls[-1]
        self.assertEqual((last["after_priority"], last["after_id"]), (87, 1400))

    def test_workflow_uses_the_projection_not_the_event_window(self):
        # The latest contact is older than the event window; the projection still has it.
        self.store.states[4] = {
            "lead_id": 4,
            "latest_contact": {"id": 99, "lead_name": "Own Active", "action": "contact_result_recorded",
                               "outcome": "won", "channel": "phone", "happened_at": "2026-01-01T09:00:00+00:00",
                               "actor_email": "ali@example.com"},
            "latest_contact_actor": "ali@example.com",
            "latest_manual_verification": None,
        }
        self.store.leads[3]["status"] = "converted"
        _, payload = self._call(workspace_api, "GET", ALI, path="/api/workspace")
        lead = next(item for item in payload["leads"] if item["name"] == "Own Active")
        self.assertEqual(lead["workflow"]["latest_outcome"], "won")
        self.assertIn(99, {event.get("id") for event in payload["outreach"]})
        ali = next(row for row in payload["team_performance"] if row["email"] == "ali@example.com")
        self.assertEqual(ali["won_total"], 1)

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
