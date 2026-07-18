from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any


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
    handler.send_header("Access-Control-Allow-Origin", handler.headers.get("Origin", "*"))
    handler.send_header("Access-Control-Allow-Credentials", "true")
    handler.send_header("Access-Control-Allow-Methods", allow_methods)
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-store")
    if set_cookie:
        handler.send_header("Set-Cookie", set_cookie)
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def send_options(handler: BaseHTTPRequestHandler, *, allow_methods: str = "GET, POST, OPTIONS") -> None:
    handler.send_response(204)
    handler.send_header("Access-Control-Allow-Origin", handler.headers.get("Origin", "*"))
    handler.send_header("Access-Control-Allow-Credentials", "true")
    handler.send_header("Access-Control-Allow-Methods", allow_methods)
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
