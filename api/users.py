from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import make_password_hash, normalize_email, require_admin, require_auth
from src.http_api import read_json, send_internal_error, send_json, send_options
from src.storage.supabase import (
    fetch_app_user_by_email,
    fetch_app_users,
    is_enabled as supabase_enabled,
    insert_audit_event,
    set_app_user_active,
    upsert_app_user,
)


def _clean_text(value: str | None, *, max_len: int = 120) -> str:
    return value.strip()[:max_len] if isinstance(value, str) else ""


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="GET, POST, PATCH, OPTIONS")

    def do_GET(self):
        try:
            viewer = require_auth(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "login required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if not supabase_enabled():
            send_json(self, 503, {"ok": False, "error": "supabase is not configured"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            users = fetch_app_users()
            if viewer.get("role") != "admin":
                own_email = normalize_email(viewer.get("sub"))
                users = [
                    {
                        "email": row.get("email") if normalize_email(row.get("email")) == own_email else None,
                        "name": row.get("name"),
                        "role": row.get("role"),
                        "title": row.get("title"),
                        "avatar_url": row.get("avatar_url"),
                        "active": row.get("active"),
                    }
                    for row in users
                    if row.get("active", True)
                ]
            send_json(self, 200, {"ok": True, "users": users}, allow_methods="GET, POST, PATCH, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="user fetch failed", allow_methods="GET, POST, PATCH, OPTIONS")

    def do_POST(self):
        try:
            admin = require_admin(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "admin login required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            payload = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="GET, POST, PATCH, OPTIONS")
            return

        for field in ("email", "name", "role", "title", "avatar_url", "password"):
            if field in payload and payload[field] is not None and not isinstance(payload[field], str):
                send_json(self, 400, {"ok": False, "error": f"{field} must be text"}, allow_methods="GET, POST, PATCH, OPTIONS")
                return

        email = normalize_email(payload.get("email"))
        name = _clean_text(payload.get("name") or email)
        role = _clean_text(payload.get("role") or "sales", max_len=20)
        title = _clean_text(payload.get("title") or ("Patron" if role == "admin" else "Çalışan"))
        avatar_url = _clean_text(payload.get("avatar_url"), max_len=240)
        password = payload.get("password")
        if not isinstance(payload.get("active", True), bool):
            send_json(self, 400, {"ok": False, "error": "active must be boolean"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        active = payload.get("active", True)
        if not email or "@" not in email:
            send_json(self, 400, {"ok": False, "error": "valid email is required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if role not in {"admin", "sales"}:
            send_json(self, 400, {"ok": False, "error": "role must be admin or sales"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if not isinstance(password, str) or len(password) < 12:
            send_json(self, 400, {"ok": False, "error": "password must contain at least 12 characters"}, allow_methods="GET, POST, PATCH, OPTIONS")
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
            insert_audit_event(
                actor_email=admin.get("sub"),
                event_type="user_created",
                target_type="user",
                target_key=email,
                meta={"role": role, "active": active},
            )
            send_json(self, 200, {"ok": True, "user": user}, allow_methods="GET, POST, PATCH, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="user save failed", allow_methods="GET, POST, PATCH, OPTIONS")

    def do_PATCH(self):
        try:
            admin = require_admin(self)
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
        for field in ("name", "role", "title", "avatar_url", "password"):
            if field in payload and payload[field] is not None and not isinstance(payload[field], str):
                send_json(self, 400, {"ok": False, "error": f"{field} must be text"}, allow_methods="GET, POST, PATCH, OPTIONS")
                return
        if not email:
            send_json(self, 400, {"ok": False, "error": "email is required"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if "active" in payload and not isinstance(payload["active"], bool):
            send_json(self, 400, {"ok": False, "error": "active must be boolean"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        if "password" in payload and payload["password"] is not None and (not isinstance(payload["password"], str) or len(payload["password"]) < 12):
            send_json(self, 400, {"ok": False, "error": "password must contain at least 12 characters"}, allow_methods="GET, POST, PATCH, OPTIONS")
            return
        try:
            current = fetch_app_user_by_email(email)
            if not current:
                send_json(self, 404, {"ok": False, "error": "user not found"}, allow_methods="GET, POST, PATCH, OPTIONS")
                return
            role = _clean_text(payload.get("role") or current.get("role") or "sales", max_len=20)
            if role not in {"admin", "sales"}:
                send_json(self, 400, {"ok": False, "error": "role must be admin or sales"}, allow_methods="GET, POST, PATCH, OPTIONS")
                return
            active = payload.get("active", current.get("active", True))
            if current.get("role") == "admin" and current.get("active", True) and (role != "admin" or not active):
                active_admins = [row for row in fetch_app_users(limit=200) if row.get("role") == "admin" and row.get("active", True)]
                if len(active_admins) <= 1:
                    send_json(self, 409, {"ok": False, "error": "the last active admin cannot be removed"}, allow_methods="GET, POST, PATCH, OPTIONS")
                    return
            fields = {"name", "role", "title", "avatar_url", "password"}
            if any(field in payload for field in fields):
                user = upsert_app_user(
                    email=email,
                    name=_clean_text(payload.get("name") or current.get("name") or email),
                    role=role,
                    title=_clean_text(payload.get("title") or current.get("title") or ("Patron" if role == "admin" else "Çalışan")),
                    avatar_url=_clean_text(payload.get("avatar_url") or current.get("avatar_url"), max_len=240),
                    password_hash=make_password_hash(payload["password"]) if payload.get("password") else None,
                    active=active,
                )
                user.pop("password_hash", None)
                insert_audit_event(
                    actor_email=admin.get("sub"),
                    event_type="user_updated",
                    target_type="user",
                    target_key=email,
                    meta={"role": role, "password_changed": bool(payload.get("password"))},
                )
                send_json(self, 200, {"ok": True, "user": user}, allow_methods="GET, POST, PATCH, OPTIONS")
                return
            if "active" in payload:
                set_app_user_active(email, active)
                insert_audit_event(
                    actor_email=admin.get("sub"),
                    event_type="user_active_changed",
                    target_type="user",
                    target_key=email,
                    meta={"active": active},
                )
            send_json(self, 200, {"ok": True}, allow_methods="GET, POST, PATCH, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="user update failed", allow_methods="GET, POST, PATCH, OPTIONS")
