import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auth import make_password_hash
from src.storage.supabase import upsert_app_user
from src.team import TEAM_MEMBERS


def main() -> None:
    for member in TEAM_MEMBERS:
        key = "TEAM_PASSWORD_" + member["email"].split("@", 1)[0].upper().replace(".", "_")
        password = os.getenv(key)
        if not password:
            raise SystemExit(f"{member['email']} için {key} ortam değişkeni gerekli.")
        user = upsert_app_user(
            email=member["email"],
            name=member["name"],
            role=member["role"],
            title=member["title"],
            avatar_url=member["avatar_url"],
            password_hash=make_password_hash(password),
            active=True,
        )
        print(f"{user['email']} hazır ({user['role']} / {user.get('title')}).")


if __name__ == "__main__":
    main()
