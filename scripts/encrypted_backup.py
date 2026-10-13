"""Create a verified public-schema archive; publish only age-encrypted output."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit, unquote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.database_backup import BackupFailed, backup, connection, digest, private_file, psql

PROJECT_REF = 'jlxjftzxheqwwttaizio'


def validate_source(dsn):
    parsed = urlsplit(dsn)
    local = parsed.hostname in {'localhost','127.0.0.1','::1'}
    if not local and not (parsed.hostname == 'db.'+PROJECT_REF+'.supabase.co'
                         or ((parsed.hostname or '').endswith('.pooler.supabase.com')
                             and unquote(parsed.username or '').endswith('.'+PROJECT_REF))):
        raise BackupFailed('Yedek bağlantısı Zeplin projesini göstermeli.')
    if not local and (parsed.port or 5432) != 5432:
        raise BackupFailed('Direct veya session pooler 5432 gerekli; transaction pooler kullanılmaz.')
    environment, identity = connection(dsn)
    if not local and environment['PGSSLMODE'] not in {'require','verify-ca','verify-full'}:
        raise BackupFailed('Uzak yedek bağlantısında TLS gerekli.')
    return environment, identity


def retention(at):
    return ('weekly',28) if at.astimezone(ZoneInfo('Europe/Istanbul')).weekday()==6 else ('daily',7)


def encrypt_archive(archive, recipient, destination):
    if not re.fullmatch(r'age1[0-9a-z]+',recipient or ''):
        raise BackupFailed('Geçerli age public recipient gerekli.')
    destination = Path(destination)
    # The encryption process does not need database credentials.
    clean_env = {k:v for k,v in os.environ.items() if not k.startswith('PG') and k!='BACKUP_DATABASE_URL'}
    made = False
    try:
        with Path(archive).open('rb') as source, private_file(destination) as output:
            made = True
            result = subprocess.run(['age','--encrypt','--recipient',recipient],stdin=source,stdout=output,
                                    stderr=subprocess.PIPE,env=clean_env,check=False)
        if result.returncode:
            raise BackupFailed('Yedek şifrelenemedi; hiçbir düz dosya yayımlanmadı.')
    except Exception:
        if made:
            destination.unlink(missing_ok=True)
        raise


def create_encrypted_backup(dsn, recipient, directory):
    environment, identity = validate_source(dsn)
    directory = Path(directory).resolve()
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    directory.chmod(0o700)
    now = datetime.now(timezone.utc)
    kind, days = retention(now)
    with tempfile.TemporaryDirectory(prefix='zeplin-private-backup-') as scratch:
        scratch = Path(scratch)
        # Fail before reading DB data if the recipient cannot encrypt a file.
        empty = scratch/'empty';empty.write_bytes(b'')
        encrypt_archive(empty,recipient,scratch/'recipient-test.age')
        server_major = int(psql(environment,'select current_setting(\'server_version_num\');'))//10000
        version = subprocess.run(['pg_dump','--version'],capture_output=True,text=True,check=True)
        major = int(re.search(r'\b(\d+)\.\d+',version.stdout)[1])
        if major != server_major:
            raise BackupFailed('pg_dump ve sunucu PostgreSQL ana sürümü eşleşmiyor.')
        dump = scratch/'database.dump'
        backup(dump,environment,identity)
        archive = scratch/'private.tar'
        with private_file(archive) as stream, tarfile.open(fileobj=stream,mode='w') as bundle:
            for path in (dump,dump.with_suffix('.dump.backup.json')):
                bundle.add(path,arcname=path.name)
        target = directory/f'zeplin-{kind}-{now:%Y%m%dT%H%M%S}-{os.urandom(4).hex()}.tar.age'
        encrypt_archive(archive,recipient,target)
    # Public sidecar contains only ciphertext metadata, not customer data or DSNs.
    info = dict(format=1,scope='public',created_at=now.isoformat(),encrypted_sha256=digest(target),
                bytes=target.stat().st_size,kind=kind,retention_days=days)
    with private_file(target.with_suffix('.age.sha256.json')) as stream:
        stream.write((json.dumps(info,indent=2)+'\n').encode())
    return target, info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',default='backups/encrypted')
    args = parser.parse_args()
    try:
        dsn = os.getenv('BACKUP_DATABASE_URL')
        recipient = os.getenv('BACKUP_AGE_RECIPIENT')
        if not dsn or not recipient:
            raise BackupFailed('BACKUP_DATABASE_URL secret ve BACKUP_AGE_RECIPIENT variable gerekli.')
        target, info = create_encrypted_backup(dsn,recipient,args.directory)
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as output:
                output.write(f'archive={target}\nsidecar={target.with_suffix(".age.sha256.json")}\nretention={info["retention_days"]}\n')
        print(f'Şifreli yedek doğrulandı: {info["bytes"]} bayt; saklama {info["retention_days"]} gün.')
        return 0
    except BackupFailed as exc:
        print(str(exc),file=sys.stderr)
    except Exception as exc:
        # Never echo raw connection/subprocess exceptions.
        print('Yedek başarısız: '+type(exc).__name__,file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
