"""Exercise the entire encrypted backup flow with synthetic rows only."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.backup_rehearsal import FIXTURE
from scripts.database_backup import connection, restore
from scripts.decrypt_backup import open_backup
from scripts.encrypted_backup import create_encrypted_backup
from scripts.schema_parity import Server, SNAPSHOT, diff


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn',required=True,help='throwaway server only')
    parser.add_argument('--directory',default='backups/encrypted-rehearsal')
    args=parser.parse_args()
    server=Server(args.dsn);source='encrypted_rehearsal_source';target='encrypted_rehearsal_target'
    server.ensure_roles()
    try:
        server.recreate(source);server.recreate(target);server.apply(source,[SNAPSHOT])
        server.psql(source,sql=FIXTURE)
        with tempfile.TemporaryDirectory(prefix='zeplin-synthetic-crypto-') as scratch:
            scratch=Path(scratch);key=scratch/'key'
            subprocess.run(['age-keygen','-o',str(key)],check=True,capture_output=True)
            recipient=subprocess.run(['age-keygen','-y',str(key)],check=True,capture_output=True,text=True).stdout.strip()
            encrypted,info=create_encrypted_backup(server.url(source),recipient,args.directory)
            archive=open_backup(encrypted,key,scratch/'opened')
            env,identity=connection(server.url(target));restore(archive,env,identity)
            assert not diff(server.catalog(source),server.catalog(target))
            tables=server.psql(source,sql="select tablename from pg_tables where schemaname='public' order by tablename;").splitlines()
            for table in tables:
                query="select md5(coalesce(string_agg(to_jsonb(t)::text,'|' order by to_jsonb(t)::text),'')) from public."+table+' t;'
                assert server.psql(source,sql=query)==server.psql(target,sql=query),table
            if os.getenv('GITHUB_OUTPUT'):
                with open(os.environ['GITHUB_OUTPUT'],'a') as out:
                    out.write(f'archive={encrypted}\nsidecar={encrypted.with_suffix(".age.sha256.json")}\n')
            print(f'ok synthetic encryption/decryption/empty restore: {len(tables)} table hashes and catalog match')
    finally:
        server.drop(source);server.drop(target)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
