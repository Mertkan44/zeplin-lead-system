from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from typing import Any

from src.config import env

COOKIE_NAME = "zl_admin_session"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60


def auth_configured() -> bool:
    return bool(env("ADMIN_PASSWORD") and env("SESSION_SECRET"))


def verify_admin_password(password: str | None) -> bool:
    configured = env("ADMIN_PASSWORD")
    if not configured or password is None:
        return False
    return hmac.compare_digest(password, configured)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign(payload_b64: str) -> str:
    secret = env("SESSION_SECRET") or ""
    digest = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64(digest)


def create_session_cookie(email: str | None = None) -> str:
    now = int(time.time())
    payload = {
        "sub": email or env("ADMIN_EMAIL", "admin"),
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
    return payload


def require_admin(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    admin = current_admin(handler)
    if not admin:
        raise PermissionError("admin login required")
    return admin
