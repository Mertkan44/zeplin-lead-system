from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import (
    authenticate_user,
    auth_configured,
    clear_session_cookie,
    create_session_cookie,
    current_user,
    login_rate_limited,
    normalize_email,
    record_login_attempt,
)
from src.http_api import read_json, send_json, send_options
from src.storage.supabase import insert_audit_event


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="GET, POST, DELETE, OPTIONS")

    def do_GET(self):
        user = current_user(self)
        send_json(
            self,
            200,
            {
                "authenticated": bool(user),
                "configured": auth_configured(),
                "user": (
                    {
                        "email": user.get("sub"),
                        "name": user.get("name"),
                        "role": user.get("role"),
                        "title": user.get("title"),
                        "avatar_url": user.get("avatar_url"),
                    }
                    if user
                    else None
                ),
                "admin": {"email": user.get("sub")} if user and user.get("role") == "admin" else None,
            },
            allow_methods="GET, POST, DELETE, OPTIONS",
        )

    def do_POST(self):
        if not auth_configured():
            send_json(self, 503, {"ok": False, "error": "admin auth is not configured"})
            return
        try:
            payload = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)})
            return
        if not isinstance(payload.get("email"), str) or not isinstance(payload.get("password"), str) or not isinstance(payload.get("role", ""), str):
            send_json(self, 400, {"ok": False, "error": "email, password and role must be text"})
            return
        client_ip = (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()
        email = normalize_email(payload.get("email"))
        throttle_keys = [(f"pair:{client_ip}:{email}", 8), (f"ip:{client_ip}", 40), (f"account:{email}", 16)]
        try:
            limited = any(login_rate_limited(key, max_attempts=maximum) for key, maximum in throttle_keys)
        except RuntimeError:
            send_json(self, 503, {"ok": False, "error": "login protection is temporarily unavailable"})
            return
        if limited:
            insert_audit_event(
                actor_email=email,
                event_type="login_rate_limited",
                target_type="auth",
                meta={"ip": client_ip},
            )
            send_json(self, 429, {"ok": False, "error": "too many login attempts; try again later"})
            return
        user = authenticate_user(payload.get("email"), payload.get("password"), payload.get("role"))
        try:
            for key, _ in throttle_keys:
                if user and key.startswith("ip:"):
                    continue
                record_login_attempt(key, success=bool(user))
        except RuntimeError:
            send_json(self, 503, {"ok": False, "error": "login protection is temporarily unavailable"})
            return
        if not user:
            insert_audit_event(
                actor_email=normalize_email(payload.get("email")),
                event_type="login_failed",
                target_type="auth",
                meta={"ip": client_ip},
            )
            send_json(self, 401, {"ok": False, "error": "invalid credentials"})
            return
        insert_audit_event(
            actor_email=user.get("email"),
            event_type="login_succeeded",
            target_type="auth",
            meta={"ip": client_ip},
        )
        cookie = create_session_cookie(
            user["email"],
            role=user["role"],
            name=user.get("name"),
            title=user.get("title"),
            avatar_url=user.get("avatar_url"),
            session_version=user.get("session_version"),
        )
        send_json(
            self,
            200,
            {
                "ok": True,
                "authenticated": True,
                "user": {
                    "email": user["email"],
                    "name": user.get("name"),
                    "role": user["role"],
                    "title": user.get("title"),
                    "avatar_url": user.get("avatar_url"),
                },
            },
            allow_methods="GET, POST, DELETE, OPTIONS",
            set_cookie=cookie,
        )

    def do_DELETE(self):
        send_json(
            self,
            200,
            {"ok": True, "authenticated": False},
            allow_methods="GET, POST, DELETE, OPTIONS",
            set_cookie=clear_session_cookie(),
        )
