"""Verify and open an encrypted backup into a new private directory; never restores a DB."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.database_backup import BackupFailed, digest, private_file


def open_backup(path, identity, destination):
    path=Path(path);destination=Path(destination)
    info=json.loads(path.with_suffix('.age.sha256.json').read_text())
    if info.get('format')!=1 or info.get('encrypted_sha256')!=digest(path) or info.get('bytes')!=path.stat().st_size:
        raise BackupFailed('Şifreli yedek checksum doğrulaması başarısız.')
    if destination.exists():
        raise BackupFailed('Yeni ve boş bir açma dizini seç; mevcut dizine yazılmaz.')
    with tempfile.TemporaryDirectory(prefix='zeplin-private-decrypt-') as scratch:
        scratch=Path(scratch);plain=scratch/'opened.tar'
        with private_file(plain) as output:
            result=subprocess.run(['age','--decrypt','--identity',str(identity),str(path)],
                                  stdout=output,stderr=subprocess.PIPE,check=False)
        if result.returncode:
            raise BackupFailed('Yedek açılamadı; anahtar veya dosya geçersiz.')
        with tarfile.open(plain) as bundle:
            members=bundle.getmembers()
            if len(members)!=2 or {m.name for m in members}!={'database.dump','database.dump.backup.json'}:
                raise BackupFailed('Yedek paketi beklenen dosyaları içermiyor.')
            for member in members:
                if not member.isfile() or member.size<0 or member.size>1_000_000_000:
                    raise BackupFailed('Geçersiz veya aşırı büyük yedek üyesi.')
                with bundle.extractfile(member) as source,private_file(scratch/member.name) as output:
                    shutil.copyfileobj(source,output)
        manifest=json.loads((scratch/'database.dump.backup.json').read_text())
        if manifest.get('format')!=1 or manifest.get('scope')!='public' or manifest.get('sha256')!=digest(scratch/'database.dump'):
            raise BackupFailed('Açılan native archive checksum doğrulaması başarısız.')
        destination.mkdir(mode=0o700,parents=True)
        for name in ('database.dump','database.dump.backup.json'):
            with (scratch/name).open('rb') as source,private_file(destination/name) as output:
                shutil.copyfileobj(source,output)
    return destination/'database.dump'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file',required=True)
    parser.add_argument('--identity',required=True)
    parser.add_argument('--directory',required=True)
    args=parser.parse_args()
    try:
        open_backup(args.file,args.identity,args.directory)
        print('Yedek açıldı ve doğrulandı; veritabanına geri yükleme yapılmadı.')
        return 0
    except BackupFailed as exc:
        print(str(exc),file=sys.stderr)
    except Exception as exc:
        print('Yedek açma başarısız: '+type(exc).__name__,file=sys.stderr)
    return 1


if __name__=='__main__':
    raise SystemExit(main())
