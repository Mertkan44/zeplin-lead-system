from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from typing import Any

from src.config import env
from src.storage import supabase

COOKIE_NAME = "zl_admin_session"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
USER_ROLES = {"admin", "sales"}


def auth_configured() -> bool:
    return bool(env("SESSION_SECRET") and (env("ADMIN_PASSWORD") or supabase.is_enabled()))


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def verify_admin_password(password: str | None) -> bool:
    configured = env("ADMIN_PASSWORD")
    if not configured or password is None:
        return False
    return hmac.compare_digest(password, configured)


def make_password_hash(password: str) -> str:
    if not password:
        raise ValueError("password is required")
    iterations = 210_000
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password_hash(password: str | None, password_hash: str | None) -> bool:
    if not password or not password_hash:
        return False
    try:
        algo, iterations_raw, salt_b64, digest_b64 = password_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        expected = _unb64(digest_b64)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _unb64(salt_b64),
            int(iterations_raw),
        )
    except Exception:
        return False
    return hmac.compare_digest(digest, expected)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign(payload_b64: str) -> str:
    secret = env("SESSION_SECRET") or ""
    digest = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64(digest)


def create_session_cookie(email: str | None = None, *, role: str = "admin", name: str | None = None) -> str:
    now = int(time.time())
    role = role if role in USER_ROLES else "sales"
    payload = {
        "sub": normalize_email(email) or normalize_email(env("ADMIN_EMAIL")) or "admin",
        "role": role,
        "name": name or None,
        "iat": now,
        "exp": now + SESSION_TTL_SECONDS,
    }
    payload_b64 = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    token = f"{payload_b64}.{_sign(payload_b64)}"
    attrs = [
        f"{COOKIE_NAME}={token}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        f"Max-Age={SESSION_TTL_SECONDS}",
    ]
    if env("VERCEL") or env("AUTH_SECURE_COOKIES", "0") == "1":
        attrs.append("Secure")
    return "; ".join(attrs)


def clear_session_cookie() -> str:
    return f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


def current_admin(handler: BaseHTTPRequestHandler) -> dict[str, Any] | None:
    user = current_user(handler)
    if user and user.get("role") == "admin":
        return user
    return None


def current_user(handler: BaseHTTPRequestHandler) -> dict[str, Any] | None:
    if not auth_configured():
        return None
    raw_cookie = handler.headers.get("Cookie", "")
    cookie = SimpleCookie()
    cookie.load(raw_cookie)
    morsel = cookie.get(COOKIE_NAME)
    if not morsel:
        return None
    token = morsel.value
    if "." not in token:
        return None
    payload_b64, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(payload_b64)):
        return None
    try:
        payload = json.loads(_unb64(payload_b64))
    except Exception:
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    if payload.get("role") not in USER_ROLES:
        payload["role"] = "admin"
    return payload


def require_auth(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    user = current_user(handler)
    if not user:
        raise PermissionError("login required")
    return user


def require_role(handler: BaseHTTPRequestHandler, *roles: str) -> dict[str, Any]:
    user = require_auth(handler)
    if user.get("role") not in set(roles):
        raise PermissionError("insufficient role")
    return user


def require_admin(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    return require_role(handler, "admin")


def authenticate_user(email: str | None, password: str | None, requested_role: str | None = None) -> dict[str, Any] | None:
    normalized_email = normalize_email(email)
    requested_role = (requested_role or "").strip().lower()

    if normalized_email and supabase.is_enabled():
        try:
            row = supabase.fetch_app_user_by_email(normalized_email)
        except Exception:
            row = None
        if row and row.get("active", True) and verify_password_hash(password, row.get("password_hash")):
            return {
                "email": row.get("email"),
                "name": row.get("name"),
                "role": row.get("role") or "sales",
            }

    admin_email = normalize_email(env("ADMIN_EMAIL")) or "admin"
    admin_role_ok = not requested_role or requested_role == "admin"
    admin_email_ok = not normalized_email or normalized_email == admin_email or normalized_email == "admin"
    if admin_role_ok and admin_email_ok and verify_admin_password(password):
        return {"email": admin_email, "name": "Admin", "role": "admin"}

    return None
