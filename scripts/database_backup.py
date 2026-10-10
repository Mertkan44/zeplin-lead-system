"""Private public-schema backup; restore only to an empty database, in one transaction.

Uses BACKUP_DATABASE_URL or RESTORE_DATABASE_URL from the environment, never a
command-line password. PostgreSQL tools of the server's major version are needed.
This application backup excludes Supabase Auth, Storage and platform settings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, unquote, urlsplit


class BackupFailed(RuntimeError):
    pass


def connection(value: str) -> tuple[dict[str, str], str]:
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise BackupFailed("Geçerli PostgreSQL bağlantısı gerekli.")
    query = parse_qs(parsed.query)
    if set(query) - {"sslmode", "sslrootcert"} or parsed.fragment:
        raise BackupFailed("Bağlantıda desteklenmeyen seçenek var.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", unquote(parsed.path[1:])):
        raise BackupFailed("Geçersiz veritabanı adı.")
    # Clean inherited libpq connection/SQL options so they cannot silently redirect
    # restore or weaken the explicitly selected connection.
    environment = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    environment.update({
        "PGHOST": parsed.hostname, "PGPORT": str(parsed.port or 5432),
        "PGDATABASE": unquote(parsed.path[1:]), "PGUSER": unquote(parsed.username or "postgres"),
        "PGCONNECT_TIMEOUT": "20", "PGAPPNAME": "zeplin-backup",
        "PGSSLMODE": query.get("sslmode", ["disable" if parsed.hostname in {"localhost", "127.0.0.1", "::1"} else "require"])[0],
    })
    if parsed.password is not None:
        environment["PGPASSWORD"] = unquote(parsed.password)
    if "sslrootcert" in query:
        environment["PGSSLROOTCERT"] = query["sslrootcert"][0]
    identity = "|".join(environment[k] for k in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER"))
    return environment, hashlib.sha256(identity.encode()).hexdigest()


def run(command, environment, *, output=None, sql=None):
    try:
        result = subprocess.run(command, input=sql.encode() if sql is not None else None,
                                stdout=output if output is not None else subprocess.PIPE,
                                stderr=subprocess.PIPE, env=environment, check=False)
    except FileNotFoundError:
        raise BackupFailed(command[0] + " bulunamadı; PostgreSQL araçlarını kur.") from None
    if result.returncode:
        # pg_restore/psql stderr can contain row values or connection information.
        raise BackupFailed(f"{command[0]} başarısız (kod {result.returncode}); işlem durduruldu.")
    return result.stdout.decode() if output is None else ""


def psql(environment, sql):
    return run(["psql", "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "--no-password"], environment, sql=sql).strip()


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def private_file(path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(fd, "wb")


def backup(path, environment, identity):
    path = Path(path).resolve()
    manifest = path.with_suffix(path.suffix + ".backup.json")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() or manifest.exists():
        raise BackupFailed("Yedek veya kayıt dosyası zaten var; üzerine yazılmaz.")
    created = False
    manifest_created = False
    try:
        with private_file(path) as stream:
            created = True
            run(["pg_dump", "--format=custom", "--schema=public", "--no-password"], environment, output=stream)
        run(["pg_restore", "--list", str(path)], environment)
        info = {"format": 1, "scope": "public", "created_at": datetime.now(timezone.utc).isoformat(),
                "source_fingerprint": identity, "sha256": digest(path), "bytes": path.stat().st_size}
        with private_file(manifest) as stream:
            manifest_created = True
            stream.write((json.dumps(info, indent=2) + "\n").encode())
    except Exception:
        # Only remove a partial file created by this operation, never an old backup.
        if created:
            path.unlink(missing_ok=True)
        if manifest_created:
            manifest.unlink(missing_ok=True)
        raise
    return info


def restore(path, environment, identity):
    path = Path(path).resolve()
    info = json.loads(path.with_suffix(path.suffix + ".backup.json").read_text())
    if info.get("format") != 1 or info.get("scope") != "public" or digest(path) != info.get("sha256"):
        raise BackupFailed("Yedeğin kapsamı veya SHA-256 doğrulaması başarısız.")
    if identity == info.get("source_fingerprint"):
        raise BackupFailed("Kaynak veritabanına geri yükleme engellendi; ayrı boş hedef kullan.")
    objects = psql(environment, """
        select count(*) from (
          select c.oid from pg_class c where c.relnamespace='public'::regnamespace
            and c.relkind in ('r','p','v','m','S','f')
            and not exists (select 1 from pg_depend d where d.objid=c.oid and d.classid='pg_class'::regclass and d.deptype='e')
          union all
          select p.oid from pg_proc p where p.pronamespace='public'::regnamespace
            and not exists (select 1 from pg_depend d where d.objid=p.oid and d.classid='pg_proc'::regclass and d.deptype='e')
        ) s;
    """)
    if objects != "0":
        raise BackupFailed("Hedef public şeması boş değil; hiçbir veri silinmedi.")
    if psql(environment, "select count(*) from pg_roles where rolname in ('anon','authenticated','service_role');") != "3":
        raise BackupFailed("Hedefte Supabase rolleri eksik; hazırlanmış boş proje kullan.")
    listing = run(["pg_restore", "--list", str(path)], environment)
    # A fresh Supabase/PostgreSQL database already has public. Keep its grants,
    # but omit only the CREATE SCHEMA entry to make single-transaction restore work.
    filtered = "\n".join(line for line in listing.splitlines()
                         if not (" SCHEMA - public " in line and not line.startswith(";"))) + "\n"
    with tempfile.TemporaryDirectory(prefix="zeplin-restore-") as directory:
        toc = Path(directory) / "toc"
        with private_file(toc) as stream:
            stream.write(filtered.encode())
        run(["pg_restore", "--dbname=" + environment["PGDATABASE"], "--no-owner", "--no-password",
             "--single-transaction", "--exit-on-error", "--use-list=" + str(toc), str(path)], environment)
    readiness = json.loads(psql(environment, "select public.schema_readiness();"))
    if not readiness.get("version") or not all(value is True for value in readiness.get("checks", {}).values()):
        raise BackupFailed("Geri yüklenen şema readiness kontrolünü geçemedi; hedefi kullanmadan incele.")
    return readiness["version"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    try:
        key = "BACKUP_DATABASE_URL" if args.action == "backup" else "RESTORE_DATABASE_URL"
        value = os.getenv(key)
        if not value:
            raise BackupFailed(key + " ortam değişkeni gerekli; bağlantıyı sohbete veya komuta yapıştırma.")
        environment, identity = connection(value)
        if args.action == "backup":
            info = backup(args.file, environment, identity)
            print(f"Yedek doğrulandı: {info['bytes']} bayt; özel dosya izinleri 0600.")
        else:
            version = restore(args.file, environment, identity)
            print("Boş hedefe geri yükleme tamamlandı; şema sürümü " + version)
        return 0
    except BackupFailed as exc:
        print(str(exc), file=sys.stderr)
    except Exception as exc:
        print("Yedekleme/geri yükleme durduruldu: " + type(exc).__name__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
