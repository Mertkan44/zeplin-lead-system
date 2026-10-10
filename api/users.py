from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import (
    clear_session_cookie,
    login_rate_limited,
    make_password_hash,
    normalize_email,
    record_login_attempt,
    require_auth,
    verify_password_hash,
)
from src.http_api import read_json, send_internal_error, send_json, send_options
from src.storage.supabase import (
    CommandRejected,
    fetch_app_user_by_email,
    fetch_app_users,
    is_enabled,
    team_rpc,
)
from src.users import password, team_command, version

METHODS = "GET, POST, PATCH, OPTIONS"


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods=METHODS)

    def _user(self, *, admin=False):
        try:
            user = require_auth(self)
        except PermissionError:
            send_json(
                self,
                401,
                {"ok": False, "error": "login required"},
                allow_methods=METHODS,
            )
            return None
        if admin and user.get("role") != "admin":
            send_json(
                self,
                403,
                {"ok": False, "error": "Yönetici erişimi gerekli."},
                allow_methods=METHODS,
            )
            return None
        if not is_enabled():
            send_json(
                self,
                503,
                {"ok": False, "error": "Veritabanı bağlantısı gerekli."},
                allow_methods=METHODS,
            )
            return None
        return user

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        modern = query.get("view") == ["team"]
        viewer = self._user(admin=modern)
        if not viewer:
            return
        try:
            if modern:
                users = team_rpc(
                    "team_management_state", actor=normalize_email(viewer.get("sub"))
                )
            else:
                users = fetch_app_users()
                if viewer.get("role") != "admin":
                    own = normalize_email(viewer.get("sub"))
                    users = [
                        {
                            key: row.get(key)
                            for key in ("name", "role", "title", "avatar_url", "active")
                        }
                        | {
                            "email": (
                                row.get("email")
                                if normalize_email(row.get("email")) == own
                                else None
                            )
                        }
                        for row in users
                        if row.get("active", True)
                    ]
            send_json(self, 200, {"ok": True, "users": users}, allow_methods=METHODS)
        except CommandRejected as exc:
            self._rejected(exc)
        except Exception as exc:
            send_internal_error(
                self, exc, error="user fetch failed", allow_methods=METHODS
            )

    def _rejected(self, exc):
        send_json(
            self,
            exc.status,
            {"ok": False, "error": exc.code, "code": exc.code},
            allow_methods=METHODS,
        )

    def do_POST(self):
        self._manage(create=True)

    def do_PATCH(self):
        if parse_qs(urlparse(self.path).query).get("view") == ["account"]:
            self._password()
        else:
            self._manage(create=False)

    def _manage(self, *, create):
        viewer = self._user(admin=True)
        if not viewer:
            return
        try:
            payload = read_json(self)
            # Query email remains compatible as an identity selector.
            if "email" not in payload:
                payload["email"] = (
                    parse_qs(urlparse(self.path).query).get("email") or [""]
                )[0]
            values, raw_password = team_command(payload, create=create)
            result = team_rpc(
                "manage_team_user",
                actor=normalize_email(viewer.get("sub")),
                **values,
                password_hash=make_password_hash(raw_password) if raw_password else None
            )
            kwargs = (
                {"set_cookie": clear_session_cookie()}
                if result.get("account_changed")
                else {}
            )
            send_json(
                self, 200, {"ok": True, **result}, allow_methods=METHODS, **kwargs
            )
        except ValueError as exc:
            send_json(
                self, 400, {"ok": False, "error": str(exc)}, allow_methods=METHODS
            )
        except CommandRejected as exc:
            self._rejected(exc)
        except Exception as exc:
            send_internal_error(
                self, exc, error="user save failed", allow_methods=METHODS
            )

    def _password(self):
        viewer = self._user()
        if not viewer:
            return
        try:
            payload = read_json(self)
            if set(payload) - {
                "current_password",
                "new_password",
                "expected_updated_at",
            }:
                raise ValueError("Bu işlem yalnız kendi şifreni değiştirir.")
            old = payload.get("current_password")
            new = password(payload.get("new_password"))
            if not isinstance(old, str) or not 1 <= len(old) <= 128:
                raise ValueError("Mevcut şifreni yaz.")
            if old == new:
                raise ValueError("Yeni şifre mevcut şifreden farklı olmalı.")
            expected = version(payload.get("expected_updated_at"))
            actor = normalize_email(viewer.get("sub"))
            throttle = "password:" + actor
            if login_rate_limited(throttle):
                send_json(
                    self,
                    429,
                    {
                        "ok": False,
                        "error": "Çok fazla deneme. Bir süre sonra tekrar dene.",
                    },
                    allow_methods=METHODS,
                )
                return
            row = fetch_app_user_by_email(actor)
            if not row or not verify_password_hash(old, row.get("password_hash")):
                record_login_attempt(throttle, success=False)
                send_json(
                    self,
                    400,
                    {"ok": False, "error": "Mevcut şifre doğru değil."},
                    allow_methods=METHODS,
                )
                return
            result = team_rpc(
                "change_own_password",
                actor=actor,
                expected=expected,
                previous_hash=row["password_hash"],
                new_hash=make_password_hash(new),
            )
            record_login_attempt(throttle, success=True)
            send_json(
                self,
                200,
                {"ok": True, **result},
                allow_methods=METHODS,
                set_cookie=clear_session_cookie(),
            )
        except ValueError as exc:
            send_json(
                self, 400, {"ok": False, "error": str(exc)}, allow_methods=METHODS
            )
        except CommandRejected as exc:
            self._rejected(exc)
        except Exception as exc:
            send_internal_error(
                self, exc, error="password change failed", allow_methods=METHODS
            )
