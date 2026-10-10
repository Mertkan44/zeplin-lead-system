"""Read-only release probe: readiness, deployed commit, assets and API access gates."""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]


class ProbeFailed(RuntimeError):
    pass


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []
        self.root = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id") == "root":
            self.root = True
        value = values.get("src") if tag == "script" else values.get("href") if tag == "link" else None
        if value and value.startswith("/assets/"):
            self.paths.append(value)


def base_url(value: str) -> str:
    parsed = urlsplit(value)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise ProbeFailed("HTTPS URL gerekli (yerel deneme dışında).")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ProbeFailed("URL yalnızca sitenin adresini içermeli; kimlik bilgisi veya yol ekleme.")
    return value.rstrip("/")


def probe(url: str, *, expected_commit: str | None = None, client=None) -> list[str]:
    url = base_url(url)
    if expected_commit and not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ProbeFailed("Beklenen sürüm 40 karakterlik commit kimliği olmalı.")
    if client is None:
        # Optional existing Vercel protection bypass secret; never add it to URLs/logs.
        headers = {}
        bypass = os.getenv("VERCEL_AUTOMATION_BYPASS_SECRET")
        if bypass:
            headers["x-vercel-protection-bypass"] = bypass
        with httpx.Client(timeout=30, follow_redirects=False, headers=headers) as session:
            return probe(url, expected_commit=expected_commit, client=session)

    checks = []

    def get(path, status=200):
        response = client.get(url + path)
        if response.status_code != status:
            raise ProbeFailed(f"{path}: HTTP {response.status_code}, beklenen {status}.")
        return response

    health = get("/api/health")
    try:
        readiness = health.json()
    except ValueError:
        raise ProbeFailed("Sağlık kontrolü JSON döndürmedi; yayın korumasını kontrol et.") from None
    if readiness.get("ready") is not True or readiness.get("ok") is not True:
        raise ProbeFailed("Veritabanı şeması hazır değil.")
    if expected_commit and readiness.get("release") != expected_commit:
        raise ProbeFailed("Yayın beklenen commit ile eşleşmiyor.")
    if "schema" in readiness:
        raise ProbeFailed("Anonim sağlık kontrolünde yönetici şema bilgisi açığa çıkıyor.")
    checks.append("schema readiness / release")

    page = get("/")
    csp = page.headers.get("content-security-policy", "")
    if "frame-ancestors 'none'" not in csp or "script-src 'self'" not in csp:
        raise ProbeFailed("Panelin güvenlik başlıkları eksik.")
    parser = Assets()
    parser.feed(page.text)
    if not parser.root or not any(p.endswith(".js") for p in parser.paths) or not any(p.endswith(".css") for p in parser.paths):
        raise ProbeFailed("Panel veya derlenmiş dosyaları bulunamadı.")
    for path in set(parser.paths):
        # Only root-relative build assets; no customer data or arbitrary external requests.
        if urlsplit(path).query or not re.fullmatch(r"/assets/[A-Za-z0-9_.-]+\.(js|css)", path):
            raise ProbeFailed("Beklenmeyen panel dosyası yolu.")
        response = get(path)
        expected_type = "javascript" if path.endswith(".js") else "text/css"
        if expected_type not in response.headers.get("content-type", ""):
            raise ProbeFailed("Panel dosyası yanlış içerik türü döndürdü.")
    checks.append("dashboard / assets / CSP")

    session = get("/api/auth").json()
    if session.get("authenticated") is not False or session.get("user") is not None:
        raise ProbeFailed("Anonim istek oturum açmış görünüyor.")
    for path in ("/api/leads", "/api/workspace?view=metrics", "/api/admin_search"):
        denied = get(path, 401).json()
        if denied.get("ok") is not False or any(key in denied for key in ("leads", "jobs", "metrics", "events")):
            raise ProbeFailed("Korunan uç nokta anonim veri döndürdü.")
    checks.append("anonymous API access gates")
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("SMOKE_URL"))
    parser.add_argument("--expected-commit", default=os.getenv("SMOKE_EXPECTED_COMMIT"))
    args = parser.parse_args()
    try:
        if not args.url:
            raise ProbeFailed("SMOKE_URL veya --url gerekli.")
        for check in probe(args.url, expected_commit=args.expected_commit):
            print("ok  " + check)
        return 0
    except ProbeFailed as exc:
        print("Smoke başarısız: " + str(exc), file=sys.stderr)
    except Exception as exc:
        # HTTP exception strings may contain proxy or bypass credentials.
        print("Smoke bağlantı/yanıt hatası: " + type(exc).__name__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
