from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import make_password_hash, normalize_email, require_admin
from src.http_api import read_json, send_json, send_options
from src.storage.supabase import (
    fetch_app_user_by_email,
    fetch_app_users,
    is_enabled as supabase_enabled,
    set_app_user_active,
    upsert_app_user,
)


def _clean_text(value: str | None, *, max_len: int = 120) -> str:
    return (value or "").strip()[:max_len]


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="GET, POST, PATCH, OPTIONS")

    def do_GET(self):
        try:
            require_admin(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "admin login required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "error": "supabase is not configured"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            send_json(self, 200, {"ok": True, "users": fetch_app_users()}, allow_methods="GET, POST, PATCH, OPTIONS")
        except Exception as exc:
            send_json(self, 502, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, PATCH, OPTIONS")

    def do_POST(self):
        try:
            require_admin(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "admin login required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            payload = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, PATCH, OPTIONS")
            return

        email = normalize_email(payload.get("email"))
        name = _clean_text(payload.get("name") or email)
        role = _clean_text(payload.get("role") or "sales", max_len=20)
        title = _clean_text(payload.get("title") or ("Patron" if role == "admin" else "Çalışan"))
        avatar_url = _clean_text(payload.get("avatar_url"), max_len=240)
        password = payload.get("password")
        active = bool(payload.get("active", True))
        if not email or "@" not in email:
            send_json(self, 400, {"ok": False, "error": "valid email is required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if role not in {"admin", "sales"}:
            send_json(self, 400, {"ok": False, "error": "role must be admin or sales"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if not password:
            send_json(self, 400, {"ok": False, "error": "password is required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            user = upsert_app_user(
                email=email,
                name=name,
                role=role,
                title=title,
                avatar_url=avatar_url,
                password_hash=make_password_hash(password),
                active=active,
            )
            user.pop("password_hash", None)
            send_json(self, 200, {"ok": True, "user": user}, allow_methods="GET, POST, PATCH, OPTIONS")
        except Exception as exc:
            send_json(self, 502, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, PATCH, OPTIONS")

    def do_PATCH(self):
        try:
            require_admin(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "admin login required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        query = parse_qs(urlparse(self.path).query)
        email = normalize_email(query.get("email", [""])[0])
        try:
            payload = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if not email:
            send_json(self, 400, {"ok": False, "error": "email is required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            if "active" in payload:
                set_app_user_active(email, bool(payload["active"]))
            fields = {"name", "role", "title", "avatar_url", "password"}
            if any(field in payload for field in fields):
                current = fetch_app_user_by_email(email)
                if not current:
                    send_json(self, 404, {"ok": False, "error": "user not found"}, allow_methods="GET, POST, PATCH, OPTIONS")
                    return
                role = _clean_text(payload.get("role") or current.get("role") or "sales", max_len=20)
                if role not in {"admin", "sales"}:
                    send_json(self, 400, {"ok": False, "error": "role must be admin or sales"}, allow_methods="GET, POST, PATCH, OPTIONS")
                    return
                user = upsert_app_user(
                    email=email,
                    name=_clean_text(payload.get("name") or current.get("name") or email),
                    role=role,
                    title=_clean_text(payload.get("title") or current.get("title") or ("Patron" if role == "admin" else "Çalışan")),
                    avatar_url=_clean_text(payload.get("avatar_url") or current.get("avatar_url"), max_len=240),
                    password_hash=make_password_hash(payload["password"]) if payload.get("password") else None,
                    active=bool(payload.get("active", current.get("active", True))),
                )
                user.pop("password_hash", None)
                send_json(self, 200, {"ok": True, "user": user}, allow_methods="GET, POST, PATCH, OPTIONS")
                return
            send_json(self, 200, {"ok": True}, allow_methods="GET, POST, PATCH, OPTIONS")
        except Exception as exc:
            send_json(self, 502, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, PATCH, OPTIONS")
