from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from typing import Any

from src.config import env
from src.storage import supabase

COOKIE_NAME = "zl_admin_session"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
USER_ROLES = {"admin", "sales"}
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_MAX_ATTEMPTS = 8
_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def auth_configured() -> bool:
    legacy_enabled = env("ALLOW_LEGACY_ADMIN_LOGIN", "0") == "1" and bool(env("ADMIN_PASSWORD"))
    return bool(env("SESSION_SECRET") and (supabase.is_enabled() or legacy_enabled))


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


def create_session_cookie(
    email: str | None = None,
    *,
    role: str = "admin",
    name: str | None = None,
    title: str | None = None,
    avatar_url: str | None = None,
    session_version: str | None = None,
) -> str:
    now = int(time.time())
    role = role if role in USER_ROLES else "sales"
    payload = {
        "sub": normalize_email(email) or normalize_email(env("ADMIN_EMAIL")) or "admin",
        "role": role,
        "name": name or None,
        "title": title or None,
        "avatar_url": avatar_url or None,
        "ver": session_version or None,
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
        return None
    email = normalize_email(payload.get("sub"))
    if supabase.is_enabled() and email and email != "admin":
        try:
            row = supabase.fetch_app_user_by_email(email)
        except Exception:
            return None
        if not row or not row.get("active", True) or row.get("role") not in USER_ROLES:
            return None
        session_version = str(row.get("updated_at") or "")
        if payload.get("ver") and not hmac.compare_digest(str(payload["ver"]), session_version):
            return None
        payload.update(
            {
                "sub": normalize_email(row.get("email")),
                "role": row.get("role"),
                "name": row.get("name"),
                "title": row.get("title"),
                "avatar_url": row.get("avatar_url"),
                "ver": session_version,
            }
        )
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


def lead_read_scope(user: dict[str, Any]) -> tuple[set[str], list[dict[str, Any]]] | None:
    """Return (readable lead names, the user's visible assignments); None means every lead.

    The rule lives in public.readable_leads (migration 010): an active assignment,
    or a done/snoozed one while nobody else owns the lead. Archived (handed-over)
    assignments grant nothing.
    """
    if user.get("role") == "admin":
        return None
    email = normalize_email(user.get("sub"))
    names = {row["lead_name"] for row in supabase.fetch_readable_leads(email) if row.get("lead_name")}
    own = supabase.fetch_lead_assignments(user_email=email, limit=1000)
    visible = [
        item for item in own
        if item.get("lead_name") in names and item.get("status") != "archived"
    ]
    return names, visible


def require_lead_access(user: dict[str, Any], lead_name: str) -> None:
    if user.get("role") == "admin":
        return
    assignments = supabase.fetch_lead_assignments(
        user_email=normalize_email(user.get("sub")),
        lead_name=lead_name,
        status="active",
        limit=1,
    )
    if not assignments:
        raise PermissionError("lead is not assigned to this user")


def login_rate_limited(key: str) -> bool:
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    durable_result = supabase.check_login_rate_limit(
        key_hash,
        max_attempts=_LOGIN_MAX_ATTEMPTS,
        window_seconds=_LOGIN_WINDOW_SECONDS,
    )
    if durable_result is not None:
        return durable_result
    now = time.time()
    cutoff = now - _LOGIN_WINDOW_SECONDS
    with _login_lock:
        attempts = [stamp for stamp in _login_attempts.get(key, []) if stamp >= cutoff]
        _login_attempts[key] = attempts
        return len(attempts) >= _LOGIN_MAX_ATTEMPTS


def record_login_attempt(key: str, *, success: bool) -> None:
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    if supabase.record_login_attempt(key_hash, success=success):
        return
    with _login_lock:
        if success:
            _login_attempts.pop(key, None)
        else:
            _login_attempts.setdefault(key, []).append(time.time())


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
                "title": row.get("title"),
                "avatar_url": row.get("avatar_url"),
                "session_version": str(row.get("updated_at") or ""),
            }

    if env("ALLOW_LEGACY_ADMIN_LOGIN", "0") != "1":
        return None
    admin_email = normalize_email(env("ADMIN_EMAIL")) or "admin"
    admin_role_ok = not requested_role or requested_role == "admin"
    admin_email_ok = not normalized_email or normalized_email == admin_email or normalized_email == "admin"
    if admin_role_ok and admin_email_ok and verify_admin_password(password):
        return {"email": admin_email, "name": "Admin", "role": "admin", "title": "Patron", "avatar_url": None}

    return None
