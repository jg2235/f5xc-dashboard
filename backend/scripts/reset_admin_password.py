"""Reset an existing admin user's password.

Unlike scripts/seed.py (which is create-only by design), this script
force-updates the hashed_password of an existing user. Use via Makefile:

    ADMIN_PASSWORD='new-password' make reset-admin-password

Or directly:
    docker compose exec -e ADMIN_USERNAME=admin -e ADMIN_PASSWORD=xyz \
        backend python -m scripts.reset_admin_password
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import select

from app.auth.security import hash_password
from app.db import SessionLocal
from app.logging_config import configure_logging, get_logger
from app.models import User

configure_logging()
log = get_logger("reset_admin_password")


def main() -> None:
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        print("ERROR: ADMIN_PASSWORD env var is required.", file=sys.stderr)
        sys.exit(1)

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if user is None:
            print(f"ERROR: User '{username}' not found. Run `make seed` first.", file=sys.stderr)
            sys.exit(2)

        user.hashed_password = hash_password(password)
        db.commit()

    print(f"Password updated for user '{username}'.")
    log.info("admin_password_reset", username=username)


if __name__ == "__main__":
    main()
