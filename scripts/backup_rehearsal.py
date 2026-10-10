"""Prove backup/restore against synthetic data on a throwaway PostgreSQL server."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.database_backup import BackupFailed, backup, connection, restore
from scripts.schema_parity import Server, SNAPSHOT, diff

FIXTURE = """
insert into public.app_users(email,name,role,password_hash)
values ('sales@example.com','Demo Sales','sales','synthetic-only');
insert into public.leads(name,city,external_id,status,raw)
values ('Demo Restore Cafe','Bursa','test:restore-cafe','yeni','{"research":{"synthetic":true}}');
select public.assign_lead_owner('Demo Restore Cafe','sales@example.com',null,'admin@example.com','active','{}');
select public.record_contact_result('11111111-1111-4111-8111-111111111111', 'synthetic-hash',
  'sales@example.com',false,'Demo Restore Cafe',0,'phone','no_answer','2026-10-11T07:00:00Z',
  array['web-tasarim'],'Demo Contact','Synthetic note','follow_up','active');
insert into public.ai_generations(cache_key,task,provider,model,content,status)
values('demo-restore','report','demo','demo','Synthetic report','ready');
insert into public.ai_token_ledger(kind,provider,model,actual_tokens,actual_cost_usd)
values('usage','demo','demo',10,0.0001);
"""


def rows(server, database, table):
    return json.loads(server.psql(database, sql=f"select coalesce(json_agg(t order by to_jsonb(t)::text),'[]'::json) from public.{table} t;"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True, help="throwaway server ONLY; fixed rehearsal databases are recreated")
    args = parser.parse_args()
    server = Server(args.dsn)
    source, target = "backup_rehearsal_source", "backup_rehearsal_target"
    server.ensure_roles()
    try:
        server.recreate(source)
        server.recreate(target)
        server.apply(source, [SNAPSHOT])
        server.psql(source, sql=FIXTURE)
        source_env, source_id = connection(server.url(source))
        target_env, target_id = connection(server.url(target))
        with tempfile.TemporaryDirectory(prefix="zeplin-backup-rehearsal-") as folder:
            path = Path(folder) / "synthetic.dump"
            backup(path, source_env, source_id)
            assert path.stat().st_mode & 0o777 == 0o600
            try:
                restore(path, source_env, source_id)
                raise AssertionError("source restore was accepted")
            except BackupFailed:
                pass
            version = restore(path, target_env, target_id)
            problems = diff(server.catalog(source), server.catalog(target))
            assert not problems, "restored catalog differs: " + "\n".join(problems)
            tables = json.loads(server.psql(source, sql="select json_agg(tablename order by tablename) from pg_tables where schemaname='public';"))
            for table in tables:
                if table == "schema_migrations":
                    query = "select json_agg(t order by version) from public.schema_migrations t;"
                    assert server.psql(source, sql=query) == server.psql(target, sql=query)
                else:
                    assert rows(server, source, table) == rows(server, target, table), "rows differ: " + table
            print(f"ok backup/restore: schema {version}, {len(tables)} tables, rows / RLS / grants / functions match")
            # Sequence values must also survive, so the next CRM write cannot collide.
            seq_sql = "select last_value,is_called from public.leads_id_seq;"
            assert server.psql(source, sql=seq_sql) == server.psql(target, sql=seq_sql)
            try:
                restore(path, target_env, target_id)
                raise AssertionError("populated target restore was accepted")
            except BackupFailed:
                print("ok populated target refused")
            path.write_bytes(path.read_bytes() + b"tampered")
            try:
                restore(path, target_env, target_id)
                raise AssertionError("damaged backup was accepted")
            except BackupFailed:
                print("ok damaged backup refused")
        return 0
    finally:
        server.drop(source)
        server.drop(target)


if __name__ == "__main__":
    sys.exit(main())
