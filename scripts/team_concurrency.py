"""Last-admin races on a throwaway database, including legacy direct writes."""

from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.schema_parity import Server, SNAPSHOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn",
        required=True,
        help="throwaway server ONLY; a test database is recreated",
    )
    server = Server(parser.parse_args().dsn)
    database = "team_concurrency"
    server.ensure_roles()
    server.recreate(database)
    try:
        server.apply(database, [SNAPSHOT])
        for mode in ("command", "legacy", "repeatable-read"):
            server.psql(
                database,
                sql="insert into public.app_users(email,name,role,password_hash) values('race-a@example.com','Demo A','admin','synthetic'),('race-b@example.com','Demo B','admin','synthetic') on conflict(email) do update set role='admin',active=true;",
            )

            def demote(index):
                email = f"race-{index}@example.com"
                if mode == "command":
                    sql = f"select public.manage_team_user('{email}','61000000-0000-4000-8000-00000000000{1 if index=='a' else 2}','synthetic-{index}',false,'{email}',(select updated_at from public.app_users where email='{email}'),'Demo','sales',true,null,null,null);"
                else:
                    sql = f"update public.app_users set role='sales' where email='{email}';"
                isolation = (
                    " isolation level repeatable read"
                    if mode == "repeatable-read"
                    else ""
                )
                # Both statements overlap. The successful transaction holds its
                # locks briefly so the second transaction exercises waiting.
                return subprocess.run(
                    ["psql", server.url(database), "-X", "-q", "-v", "ON_ERROR_STOP=1"],
                    input=f"begin{isolation}; select pg_sleep(0.1); {sql} select pg_sleep(0.2); commit;",
                    text=True,
                    capture_output=True,
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(demote, ["a", "b"]))
            assert sum(row.returncode == 0 for row in results) == 1, (
                mode + " did not allow exactly one demotion"
            )
            assert (
                server.psql(
                    database,
                    sql="select count(*) from public.app_users where active and role='admin';",
                ).strip()
                == "1"
            ), (
                mode + " lost last admin"
            )
            assert any(
                any(
                    code in row.stderr
                    for code in (
                        "LAST_ADMIN_REQUIRED",
                        "deadlock detected",
                        "could not serialize",
                    )
                )
                for row in results
            ), (
                mode + " lacked a controlled database refusal"
            )
            print("ok last-admin race:", mode)
        return 0
    finally:
        server.drop(database)


if __name__ == "__main__":
    sys.exit(main())
