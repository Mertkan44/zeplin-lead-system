import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auth import make_password_hash
from src.storage.supabase import upsert_app_user
from src.team import TEAM_MEMBERS


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Zeplin team users in Supabase.")
    parser.add_argument(
        "--password",
        default=os.getenv("TEAM_DEFAULT_PASSWORD"),
        help="Temporary password for every seeded user. Can also use TEAM_DEFAULT_PASSWORD.",
    )
    args = parser.parse_args()
    if not args.password:
        raise SystemExit("Şifre gerekli: --password veya TEAM_DEFAULT_PASSWORD kullan.")

    password_hash = make_password_hash(args.password)
    for member in TEAM_MEMBERS:
        user = upsert_app_user(
            email=member["email"],
            name=member["name"],
            role=member["role"],
            title=member["title"],
            avatar_url=member["avatar_url"],
            password_hash=password_hash,
            active=True,
        )
        print(f"{user['email']} hazır ({user['role']} / {user.get('title')}).")


if __name__ == "__main__":
    main()
