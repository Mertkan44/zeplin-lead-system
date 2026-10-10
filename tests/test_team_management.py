import io
import json
import unittest
from unittest.mock import patch
import api.users as api
from src.users import team_command
from src import auth
from src.auth import make_password_hash
from src.storage.supabase import CommandRejected

ADMIN = {"sub": "boss@example.com", "role": "admin"}
SALES = {"sub": "sales@example.com", "role": "sales"}
KEY = "51000000-0000-4000-8000-000000000001"
STAMP = "2026-10-10T07:00:00+00:00"


class TeamApiTests(unittest.TestCase):
    def body(self, **overrides):
        return dict(
            idempotency_key=KEY,
            email="sales@example.com",
            name="Demo Sales",
            role="sales",
            active=True,
            title="",
            avatar_url="",
            expected_updated_at=STAMP,
            **overrides
        )

    def request(
        self,
        method,
        body=None,
        *,
        user=ADMIN,
        path="/api/users?view=team",
        rpc_error=None,
        valid_password=True
    ):
        h = api.handler.__new__(api.handler)
        h.path = path
        raw = json.dumps(body or {}).encode()
        h.headers = {"Content-Length": str(len(raw))}
        h.rfile = io.BytesIO(raw)
        out = {"calls": []}

        def send(_h, status, payload, **kwargs):
            out.update(status=status, payload=payload, kwargs=kwargs)

        def rpc(rpc_name, **values):
            out["calls"].append((rpc_name, values))
            if rpc_error:
                raise rpc_error
            return {"user": {"email": "sales@example.com"}, "session_ended": True}

        def fail(_h, exc, **kwargs):
            raise exc

        with patch.object(api, "require_auth", return_value=user), patch.object(
            api, "is_enabled", return_value=True
        ), patch.object(api, "team_rpc", rpc), patch.object(
            api, "send_json", send
        ), patch.object(
            api, "send_internal_error", fail
        ), patch.object(
            api, "login_rate_limited", return_value=False
        ), patch.object(
            api, "record_login_attempt"
        ), patch.object(
            api,
            "fetch_app_user_by_email",
            return_value={"password_hash": "prior-secret-hash"},
        ), patch.object(
            api, "verify_password_hash", return_value=valid_password
        ), patch(
            "src.users.env", return_value="synthetic-session-secret"
        ):
            getattr(h, "do_" + method)()
        return out

    def test_role_and_active_use_one_command_with_session_actor(self):
        body = self.body()
        body.update(role="admin", active=False, actor="attacker@example.com")
        out = self.request("PATCH", body)
        self.assertEqual(out["status"], 200)
        self.assertEqual(len(out["calls"]), 1)
        name, values = out["calls"][0]
        self.assertEqual(name, "manage_team_user")
        self.assertEqual(values["actor"], ADMIN["sub"])
        self.assertEqual((values["role"], values["active"]), ("admin", False))
        self.assertIsNone(values["password_hash"])

    def test_invalid_payload_never_partially_changes_active(self):
        for change in (
            {"role": "owner"},
            {"active": "false"},
            {"name": 123},
            {"password": "short"},
            {"avatar_url": "javascript:alert(1)"},
            {"expected_updated_at": "now"},
        ):
            body = self.body()
            body.update(change)
            out = self.request("PATCH", body)
            self.assertEqual(out["status"], 400, change)
            self.assertEqual(out["calls"], [])

    def test_sales_cannot_manage_users(self):
        for method in ["GET", "POST", "PATCH"]:
            out = self.request(method, self.body(), user=SALES)
            self.assertEqual(out["status"], 403)
            self.assertEqual(out["calls"], [])

    def test_creation_hashes_password_and_never_passes_plaintext_to_rpc(self):
        out = self.request("POST", self.body(password="Synthetic password 2026"))
        values = out["calls"][0][1]
        self.assertTrue(values["password_hash"].startswith("pbkdf2_sha256$"))
        self.assertNotIn("Synthetic password 2026", json.dumps(values))
        self.assertTrue(values["create"])

    def test_replay_digest_stays_same_with_random_password_salt(self):
        body = self.body(password="Synthetic password 2026")
        with patch("src.users.env", return_value="synthetic-session-secret"):
            first, _ = team_command(body, create=True)
            second, _ = team_command(dict(body), create=True)
            changed, _ = team_command(
                {**body, "password": "Different password 2026"}, create=True
            )
        self.assertEqual(first["hash"], second["hash"])
        self.assertNotEqual(first["hash"], changed["hash"])
        self.assertNotEqual(
            make_password_hash(body["password"]), make_password_hash(body["password"])
        )

    def test_conflict_status_and_code_preserved(self):
        out = self.request(
            "PATCH", self.body(), rpc_error=CommandRejected(409, "LAST_ADMIN_REQUIRED")
        )
        self.assertEqual(out["status"], 409)
        self.assertEqual(out["payload"]["code"], "LAST_ADMIN_REQUIRED")

    def test_own_password_requires_correct_existing_password(self):
        body = {
            "current_password": "old",
            "new_password": "Synthetic new password",
            "expected_updated_at": STAMP,
        }
        out = self.request(
            "PATCH",
            body,
            user=SALES,
            path="/api/users?view=account",
            valid_password=False,
        )
        self.assertEqual(out["status"], 400)
        self.assertEqual(out["calls"], [])
        out = self.request("PATCH", body, user=SALES, path="/api/users?view=account")
        self.assertEqual(out["calls"][0][1]["actor"], SALES["sub"])
        self.assertEqual(out["calls"][0][1]["previous_hash"], "prior-secret-hash")
        self.assertIn("set_cookie", out["kwargs"])
        self.assertNotIn("password_hash", json.dumps(out["payload"]))

    def test_own_password_cannot_change_role_or_another_user(self):
        out = self.request(
            "PATCH",
            {
                "current_password": "old",
                "new_password": "Synthetic new password",
                "expected_updated_at": STAMP,
                "role": "admin",
            },
            user=SALES,
            path="/api/users?view=account",
        )
        self.assertEqual(out["status"], 400)
        self.assertEqual(out["calls"], [])


class TeamSessionTests(unittest.TestCase):
    def test_changed_account_and_unversioned_cookies_cannot_keep_a_session(self):
        row = {
            "email": "sales@example.com",
            "name": "Demo",
            "role": "sales",
            "active": True,
            "updated_at": STAMP,
        }
        with patch.object(auth, "auth_configured", return_value=True), patch.object(
            auth, "env", return_value="synthetic-session-secret"
        ), patch.object(auth.supabase, "is_enabled", return_value=True), patch.object(
            auth.supabase, "fetch_app_user_by_email", return_value=row
        ):
            cookie = auth.create_session_cookie(
                row["email"], role="sales", session_version=STAMP
            )
            request = type(
                "Request", (), {"headers": {"Cookie": cookie.split(";", 1)[0]}}
            )()
            self.assertIsNotNone(auth.current_user(request))
            row["updated_at"] = "2026-10-10T07:01:00+00:00"
            self.assertIsNone(auth.current_user(request))
            request.headers["Cookie"] = auth.create_session_cookie(
                row["email"], role="sales"
            ).split(";", 1)[0]
            self.assertIsNone(auth.current_user(request))
