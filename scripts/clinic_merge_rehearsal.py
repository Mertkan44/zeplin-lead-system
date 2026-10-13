"""Test the actual one-off clinic SQL in a disposable local PostgreSQL database."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.schema_parity import Server, SNAPSHOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn', required=True, help='throwaway server only')
    args = parser.parse_args()
    server = Server(args.dsn)
    database = 'clinic_merge_rehearsal'
    server.ensure_roles()
    source = (ROOT/'supabase/data_fixes/2026-10-07_merge_dayioglu_clinic.sql').read_text()
    match = re.search(r'\bdo\s+\$\$(.*?)\$\$;', source, re.I|re.S)
    if not match:
        raise RuntimeError('Expected one atomic DO block')
    wrapper = 'create function pg_temp.merge_clinic() returns void language plpgsql as $$'+match[1]+'$$;\n'
    try:
        server.recreate(database)
        server.apply(database, [SNAPSHOT])
        server.psql(database, sql=wrapper+(ROOT/'tests/data_fixes/clinic_merge.sql').read_text())
        print('ok clinic merge: references/history/amounts retained, replay no-op and conflicts atomic')
    finally:
        server.drop(database)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
