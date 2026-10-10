from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse


def _allowed_origin(handler: BaseHTTPRequestHandler) -> str | None:
    origin = (handler.headers.get("Origin") or "").strip()
    if not origin:
        return None
    configured = {
        value.strip().rstrip("/")
        for value in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    }
    host = (handler.headers.get("X-Forwarded-Host") or handler.headers.get("Host") or "").lower()
    parsed = urlparse(origin)
    if parsed.netloc.lower() == host or origin.rstrip("/") in configured:
        return origin
    return None


def _security_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
    handler.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    try:
        payload = json.loads(handler.rfile.read(length) or b"{}")
    except json.JSONDecodeError as exc:
        raise ValueError("invalid json") from exc
    if not isinstance(payload, dict):
        raise ValueError("json object is required")
    return payload


def send_json(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: Any,
    *,
    allow_methods: str = "GET, POST, OPTIONS",
    set_cookie: str | None = None,
) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    origin = _allowed_origin(handler)
    if origin:
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Access-Control-Allow-Credentials", "true")
        handler.send_header("Vary", "Origin")
    handler.send_header("Access-Control-Allow-Methods", allow_methods)
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-store")
    _security_headers(handler)
    if set_cookie:
        handler.send_header("Set-Cookie", set_cookie)
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def send_options(handler: BaseHTTPRequestHandler, *, allow_methods: str = "GET, POST, OPTIONS") -> None:
    origin = _allowed_origin(handler)
    if handler.headers.get("Origin") and not origin:
        handler.send_response(403)
        _security_headers(handler)
        handler.end_headers()
        return
    handler.send_response(204)
    if origin:
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Access-Control-Allow-Credentials", "true")
        handler.send_header("Vary", "Origin")
    handler.send_header("Access-Control-Allow-Methods", allow_methods)
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    _security_headers(handler)
    handler.end_headers()


def send_internal_error(
    handler: BaseHTTPRequestHandler,
    exc: Exception,
    *,
    error: str = "service temporarily unavailable",
    allow_methods: str = "GET, POST, PATCH, DELETE, OPTIONS",
) -> None:
    handler.log_error("%s (%s)", error, type(exc).__name__)
    send_json(handler, 502, {"ok": False, "error": error}, allow_methods=allow_methods)
