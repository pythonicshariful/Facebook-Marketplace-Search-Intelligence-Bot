"""User management CLI: create or reset dashboard users."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from werkzeug.security import generate_password_hash
from sqlalchemy import select

from app.config import Config
from app.db import init_engine, session_scope
from app.models import User, utcnow


def main():
    parser = argparse.ArgumentParser(description="Create or update dashboard user.")
    parser.add_argument("username", help="Username")
    parser.add_argument("password", help="Password")
    parser.add_argument("--role", choices=["admin", "viewer"], default="admin", help="Role (default: admin)")
    args = parser.parse_args()

    cfg = Config()
    init_engine(cfg.DATABASE_URL)

    with session_scope() as s:
        user = s.scalar(select(User).where(User.username == args.username))
        if user:
            user.password_hash = generate_password_hash(args.password)
            user.role = args.role
            print(f"Updated password and role for existing user '{args.username}'.")
        else:
            user = User(
                username=args.username,
                password_hash=generate_password_hash(args.password),
                role=args.role,
                created_at=utcnow(),
            )
            s.add(user)
            print(f"Created new user '{args.username}' ({args.role}).")


if __name__ == "__main__":
    main()
