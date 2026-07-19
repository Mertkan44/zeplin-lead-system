import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auth import make_password_hash, normalize_email
from src.storage.supabase import upsert_app_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a Zeplin panel user in Supabase.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", choices=["admin", "sales"], default="sales")
    parser.add_argument("--title")
    parser.add_argument("--avatar-url")
    parser.add_argument("--password", required=True)
    parser.add_argument("--inactive", action="store_true")
    args = parser.parse_args()

    user = upsert_app_user(
        email=normalize_email(args.email),
        name=args.name,
        role=args.role,
        title=args.title or ("Patron" if args.role == "admin" else "Çalışan"),
        avatar_url=args.avatar_url,
        password_hash=make_password_hash(args.password),
        active=not args.inactive,
    )
    user.pop("password_hash", None)
    print(f"{user['email']} kullanıcısı hazır ({user['role']}).")


if __name__ == "__main__":
    main()
