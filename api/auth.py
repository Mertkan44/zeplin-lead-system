from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import (
    auth_configured,
    clear_session_cookie,
    create_session_cookie,
    current_admin,
    verify_admin_password,
)
from src.config import env
from src.http_api import read_json, send_json, send_options


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="GET, POST, DELETE, OPTIONS")

    def do_GET(self):
        admin = current_admin(self)
        send_json(
            self,
            200,
            {
                "authenticated": bool(admin),
                "configured": auth_configured(),
                "admin": {"email": admin.get("sub")} if admin else None,
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
        if not verify_admin_password(payload.get("password")):
            send_json(self, 401, {"ok": False, "error": "invalid password"})
            return
        cookie = create_session_cookie(payload.get("email") or env("ADMIN_EMAIL", "admin"))
        send_json(
            self,
            200,
            {"ok": True, "authenticated": True},
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
