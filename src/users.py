"""Validated team commands. Passwords never enter audit or replay responses."""

from datetime import datetime
import hashlib
import hmac
import json
import re
from urllib.parse import urlparse
from src.config import env


def text(value, label, *, max_length=120, required=False):
    if (
        not isinstance(value, str)
        or len(value) > max_length
        or required
        and not value.strip()
    ):
        raise ValueError(label + " geçersiz.")
    return value.strip()


def password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise ValueError("Şifre 12–128 karakter olmalı.")
    return value


def version(value):
    value = text(value, "Hesap sürümü", max_length=80, required=True)
    try:
        if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError()
    except ValueError:
        raise ValueError("Hesap sürümü geçersiz.") from None
    return value


def team_command(payload, *, create):
    key = text(
        payload.get("idempotency_key"), "İşlem kimliği", max_length=36, required=True
    )
    if not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        key,
    ):
        raise ValueError("İşlem kimliği geçersiz.")
    email = text(payload.get("email"), "E-posta", max_length=240, required=True).lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("E-posta geçersiz.")
    role = payload.get("role")
    if role not in ("admin", "sales"):
        raise ValueError("Geçerli rol seç.")
    active = payload.get("active")
    if not isinstance(active, bool):
        raise ValueError("Aktif durumu doğru/yanlış olmalı.")
    avatar = text(payload.get("avatar_url", ""), "Fotoğraf bağlantısı", max_length=500)
    parsed = urlparse(avatar)
    if avatar and (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Fotoğraf bağlantısı HTTPS olmalı.")
    values = dict(
        create=create,
        email=email,
        name=text(payload.get("name"), "Ad", required=True),
        role=role,
        active=active,
        title=text(payload.get("title", ""), "Unvan"),
        avatar=avatar,
        expected=None if create else version(payload.get("expected_updated_at")),
    )
    raw_password = payload.get("password")
    if create or raw_password not in (None, ""):
        raw_password = password(raw_password)
    else:
        raw_password = None
    # A keyed digest avoids an extra unsalted password verifier in replay storage.
    secret = env("SESSION_SECRET")
    if not secret:
        raise RuntimeError("Session secret is not configured")
    canonical = json.dumps(
        {**values, "password": raw_password},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hmac.new(
        secret.encode(), ("team:" + canonical).encode(), hashlib.sha256
    ).hexdigest()
    return dict(key=key, hash=digest, **values), raw_password
