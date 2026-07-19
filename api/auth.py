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
)
from src.http_api import read_json, send_json, send_options


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
        user = authenticate_user(payload.get("email"), payload.get("password"), payload.get("role"))
        if not user:
            send_json(self, 401, {"ok": False, "error": "invalid password"})
            return
        cookie = create_session_cookie(
            user["email"],
            role=user["role"],
            name=user.get("name"),
            title=user.get("title"),
            avatar_url=user.get("avatar_url"),
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
