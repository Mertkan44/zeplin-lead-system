from datetime import datetime, timezone
from pathlib import Path
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import tarfile
import unittest

from scripts.encrypted_backup import encrypt_archive, retention, validate_source
from scripts.database_backup import BackupFailed
from scripts.decrypt_backup import open_backup


class BackupGuardTests(unittest.TestCase):
    def test_wrong_project_transaction_pooler_and_tls_disable_refused(self):
        for uri in ('postgresql://postgres:synthetic@db.other.supabase.co/postgres',
                    'postgresql://postgres.jlxjftzxheqwwttaizio:synthetic@evil.example/postgres',
                    'postgresql://postgres.jlxjftzxheqwwttaizio:synthetic@aws-0-eu-central-1.pooler.supabase.com:6543/postgres',
                    'postgresql://postgres:synthetic@db.jlxjftzxheqwwttaizio.supabase.co/postgres?sslmode=disable'):
            with self.subTest(uri=uri),self.assertRaises(BackupFailed):
                validate_source(uri)

    def test_daily_and_weekly_retention_follow_istanbul_day(self):
        self.assertEqual(retention(datetime(2026,10,17,23,30,tzinfo=timezone.utc)),('weekly',28))
        self.assertEqual(retention(datetime(2026,10,18,23,30,tzinfo=timezone.utc)),('daily',7))


@unittest.skipUnless(shutil.which('age') and shutil.which('age-keygen'),'age required for encryption tests')
class BackupEncryptionTests(unittest.TestCase):
    def test_roundtrip_tamper_detection_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            f=Path(directory);key=f/'key'
            subprocess.run(['age-keygen','-o',str(key)],check=True,capture_output=True)
            recipient=subprocess.run(['age-keygen','-y',str(key)],check=True,capture_output=True,text=True).stdout.strip()
            source=f/'synthetic.tar';source.write_bytes(b'synthetic private data'*1000)
            encrypted=f/'synthetic.tar.age'
            encrypt_archive(source,recipient,encrypted)
            self.assertEqual(encrypted.stat().st_mode & 0o777,0o600)
            restored=subprocess.run(['age','--decrypt','-i',str(key),str(encrypted)],check=True,capture_output=True).stdout
            self.assertEqual(restored,source.read_bytes())
            self.assertNotIn(b'synthetic private data',encrypted.read_bytes())
            before=encrypted.read_bytes()
            with self.assertRaises(FileExistsError):
                encrypt_archive(source,recipient,encrypted)
            self.assertEqual(encrypted.read_bytes(),before)
            damaged=bytearray(before);damaged[-1]^=1;encrypted.write_bytes(damaged)
            result=subprocess.run(['age','--decrypt','-i',str(key),str(encrypted)],capture_output=True)
            self.assertNotEqual(result.returncode,0)

    def test_safe_unpack_checks_ciphertext_and_native_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            f=Path(directory);key=f/'key'
            subprocess.run(['age-keygen','-o',str(key)],check=True,capture_output=True)
            recipient=subprocess.run(['age-keygen','-y',str(key)],check=True,capture_output=True,text=True).stdout.strip()
            data=b'synthetic native archive'
            manifest=json.dumps(dict(format=1,scope='public',sha256=hashlib.sha256(data).hexdigest())).encode()
            plain=f/'bundle.tar'
            with tarfile.open(plain,'w') as bundle:
                for name,content in (('database.dump',data),('database.dump.backup.json',manifest)):
                    member=tarfile.TarInfo(name);member.size=len(content);bundle.addfile(member,io.BytesIO(content))
            encrypted=f/'bundle.tar.age';encrypt_archive(plain,recipient,encrypted)
            meta=encrypted.with_suffix('.age.sha256.json')
            meta.write_text(json.dumps(dict(format=1,encrypted_sha256=hashlib.sha256(encrypted.read_bytes()).hexdigest(),bytes=encrypted.stat().st_size)))
            result=open_backup(encrypted,key,f/'opened')
            self.assertEqual(result.read_bytes(),data)
            self.assertEqual(result.stat().st_mode & 0o777,0o600)
            with self.assertRaises(BackupFailed):open_backup(encrypted,key,f/'opened')
            meta.write_text(json.dumps(dict(format=1,encrypted_sha256='bad',bytes=encrypted.stat().st_size)))
            with self.assertRaises(BackupFailed):open_backup(encrypted,key,f/'other')

    def test_malicious_tar_member_never_writes_outside_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            f=Path(directory);key=f/'key'
            subprocess.run(['age-keygen','-o',str(key)],check=True,capture_output=True)
            recipient=subprocess.run(['age-keygen','-y',str(key)],check=True,capture_output=True,text=True).stdout.strip()
            plain=f/'bundle.tar'
            with tarfile.open(plain,'w') as bundle:
                member=tarfile.TarInfo('../escape');member.size=4;bundle.addfile(member,io.BytesIO(b'evil'))
            encrypted=f/'bundle.tar.age';encrypt_archive(plain,recipient,encrypted)
            encrypted.with_suffix('.age.sha256.json').write_text(json.dumps(dict(format=1,encrypted_sha256=hashlib.sha256(encrypted.read_bytes()).hexdigest(),bytes=encrypted.stat().st_size)))
            with self.assertRaises(BackupFailed):open_backup(encrypted,key,f/'opened')
            self.assertFalse((f/'opened').exists())
            self.assertFalse((f/'escape').exists())
