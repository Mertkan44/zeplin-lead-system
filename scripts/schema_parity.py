"""Prove that every supported way of building the database ends in the same schema.

`supabase/schema.sql` (the bundle of every migration, see build_schema.py) is
the fresh install. It is compared with every historical `schema.sql` snapshot
in tests/fixtures/schema_history followed by migrations 002 .. latest, i.e. a
real project created from an older checkout and upgraded since.

Every path runs twice to prove the SQL is re-runnable. The script needs a
throwaway PostgreSQL server and `psql`; it creates and drops its own databases.

    python scripts/schema_parity.py --dsn postgresql://postgres@localhost:5432/postgres
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
HISTORY = sorted((ROOT / "tests" / "fixtures" / "schema_history").glob("*.sql"))
SNAPSHOT = ROOT / "supabase" / "schema.sql"
BEHAVIOUR_TESTS = sorted((ROOT / "tests" / "sql").glob("*.sql"))

# Supabase creates these roles; a plain PostgreSQL server needs them for GRANTs.
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

CATALOG_SQL = r"""
with ext_objects as (
  select objid from pg_depend where deptype = 'e'
)
select json_build_object(
  'columns', (
    select coalesce(json_agg(row_to_json(c) order by c.key), '[]'::json) from (
      select table_name || '.' || column_name as key,
             data_type, udt_name, is_nullable, column_default, is_identity
      from information_schema.columns
      where table_schema = 'public'
    ) c
  ),
  'constraints', (
    select coalesce(json_agg(x order by x), '[]'::json) from (
      select conrelid::regclass::text || ' ' || conname || ' ' || pg_get_constraintdef(oid) as x
      from pg_constraint
      where connamespace = 'public'::regnamespace and contype <> 'n'
    ) s
  ),
  'indexes', (
    select coalesce(json_agg(indexdef order by indexdef), '[]'::json)
    from pg_indexes where schemaname = 'public'
  ),
  'functions', (
    select coalesce(json_agg(x order by x), '[]'::json) from (
      select p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ') '
             || pg_get_function_result(p.oid) || ' secdef=' || p.prosecdef
             || ' config=' || coalesce(array_to_string(p.proconfig, ','), '')
             || ' body=' || md5(p.prosrc) as x
      from pg_proc p
      where p.pronamespace = 'public'::regnamespace
        and p.oid not in (select objid from ext_objects)
    ) s
  ),
  'triggers', (
    select coalesce(json_agg(pg_get_triggerdef(t.oid) order by pg_get_triggerdef(t.oid)), '[]'::json)
    from pg_trigger t join pg_class c on c.oid = t.tgrelid
    where c.relnamespace = 'public'::regnamespace and not t.tgisinternal
  ),
  'rls', (
    select coalesce(json_agg(relname || '=' || relrowsecurity order by relname), '[]'::json)
    from pg_class where relnamespace = 'public'::regnamespace and relkind = 'r'
  ),
  'table_grants', (
    select coalesce(json_agg(x order by x), '[]'::json) from (
      select grantee || ' ' || table_name || ' ' || privilege_type as x
      from information_schema.role_table_grants
      where table_schema = 'public' and grantee in ('anon', 'authenticated', 'service_role')
    ) s
  ),
  'routine_grants', (
    select coalesce(json_agg(x order by x), '[]'::json) from (
      select p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ') '
             || coalesce(array_to_string(p.proacl, ','), 'default') as x
      from pg_proc p
      where p.pronamespace = 'public'::regnamespace
        and p.oid not in (select objid from ext_objects)
    ) s
  ),
  'sequence_grants', (
    select coalesce(json_agg(x order by x), '[]'::json) from (
      select c.relname || ' ' || coalesce(array_to_string(c.relacl, ','), 'default') as x
      from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind = 'S'
    ) s
  )
)::text;
"""


class Server:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def url(self, database: str) -> str:
        parsed = urlparse(self.dsn)
        return urlunparse(parsed._replace(path=f"/{database}"))

    def psql(self, database: str, *args: str, sql: str | None = None) -> str:
        command = ["psql", self.url(database), "-v", "ON_ERROR_STOP=1", "-X", "-q", "-At", *args]
        result = subprocess.run(
            command,
            input=sql,
            text=True,
            capture_output=True,
            env={**os.environ, "PGOPTIONS": "-c client_min_messages=warning"},
        )
        if result.returncode != 0:
            raise RuntimeError(f"psql failed ({' '.join(args) or 'stdin'}):\n{result.stderr.strip()}")
        return result.stdout

    def ensure_roles(self) -> None:
        for role in SUPABASE_ROLES:
            self.psql(
                "postgres",
                sql=f"do $$ begin create role {role} nologin; exception when duplicate_object then null; end $$;",
            )

    def recreate(self, database: str) -> None:
        self.psql("postgres", "-c", f'drop database if exists "{database}"')
        self.psql("postgres", "-c", f'create database "{database}"')

    def drop(self, database: str) -> None:
        self.psql("postgres", "-c", f'drop database if exists "{database}"')

    def apply(self, database: str, files: list[Path]) -> None:
        for path in files:
            try:
                self.psql(database, "-f", str(path))
            except RuntimeError as exc:
                raise RuntimeError(f"{path.relative_to(ROOT)}: {exc}") from None

    def catalog(self, database: str) -> dict[str, list]:
        return json.loads(self.psql(database, sql=CATALOG_SQL))


def build_paths() -> dict[str, list[Path]]:
    upgrade_migrations = [path for path in MIGRATIONS if not path.name.startswith("001_")]
    paths = {}
    for snapshot in HISTORY:
        paths[f"upgrade-from-{snapshot.stem}"] = [snapshot, *upgrade_migrations]
    return paths


def diff(expected: dict[str, list], actual: dict[str, list]) -> list[str]:
    problems = []
    for section in expected:
        want = [json.dumps(item, sort_keys=True) for item in expected[section]]
        got = [json.dumps(item, sort_keys=True) for item in actual.get(section, [])]
        for item in sorted(set(want) - set(got)):
            problems.append(f"  {section}: missing {item}")
        for item in sorted(set(got) - set(want)):
            problems.append(f"  {section}: extra   {item}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", default=os.getenv("SCHEMA_PARITY_DSN", "postgresql://postgres@localhost:5432/postgres"))
    parser.add_argument("--keep", action="store_true", help="keep the databases for inspection")
    args = parser.parse_args()

    server = Server(args.dsn)
    server.ensure_roles()

    server.recreate("parity_snapshot")
    server.apply("parity_snapshot", [SNAPSHOT, SNAPSHOT])
    expected = server.catalog("parity_snapshot")
    print(f"snapshot: {SNAPSHOT.relative_to(ROOT)} ({sum(len(v) for v in expected.values())} catalog entries)")

    failures = 0
    for index, (name, files) in enumerate(build_paths().items()):
        database = f"parity_{index}"
        server.recreate(database)
        try:
            server.apply(database, files)
            server.apply(database, [path for path in files if path.parent.name == "migrations"])
            problems = diff(expected, server.catalog(database))
        except RuntimeError as exc:
            problems = [f"  {exc}"]
        if problems:
            failures += 1
            print(f"FAIL {name}")
            print("\n".join(problems))
        else:
            print(f"ok   {name}")
        if not args.keep:
            server.drop(database)
    for path in BEHAVIOUR_TESTS:
        try:
            server.apply("parity_snapshot", [path])
            print(f"ok   behaviour {path.name}")
        except RuntimeError as exc:
            failures += 1
            print(f"FAIL behaviour {path.name}\n  {exc}")
    if not args.keep:
        server.drop("parity_snapshot")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
