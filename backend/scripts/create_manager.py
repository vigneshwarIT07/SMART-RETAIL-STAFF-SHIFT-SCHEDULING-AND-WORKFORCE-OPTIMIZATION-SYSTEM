"""Create the initial store manager account (secure bootstrap).

There is no public self-registration: the first manager is created by running
this script on the server with explicit arguments. Employee accounts are then
created by managers from the Employees screen.

Usage (from ``backend/``)::

    py scripts/create_manager.py --email boss@shop.com --name "Shop Boss" --store-code MAIN-01 --store-name "Main Street Shop"

The password is read from the ``MANAGER_PASSWORD`` environment variable, or
prompted interactively (never passed on the command line, never logged).
Refuses to run when ``ENVIRONMENT=production`` unless ``ALLOW_PROD_BOOTSTRAP=1``
is set explicitly by the operator.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import Store, User, UserRole  # noqa: E402


def main() -> None:
    """Parse arguments and create the manager account."""
    parser = argparse.ArgumentParser(description="Bootstrap the first store manager.")
    parser.add_argument("--email", required=True, help="Manager login email.")
    parser.add_argument("--name", required=True, help="Manager full name.")
    parser.add_argument("--store-code", required=True, help="Unique store code.")
    parser.add_argument("--store-name", required=True, help="Store display name.")
    args = parser.parse_args()

    settings = get_settings()
    if settings.is_production and os.environ.get("ALLOW_PROD_BOOTSTRAP") != "1":
        raise SystemExit(
            "Refusing to bootstrap in production without ALLOW_PROD_BOOTSTRAP=1."
        )

    password = os.environ.get("MANAGER_PASSWORD") or getpass.getpass("Manager password: ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")

    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == args.email)) is not None:
            raise SystemExit(f"A user with email {args.email} already exists.")
        store = db.scalar(select(Store).where(Store.code == args.store_code))
        if store is None:
            store = Store(
                name=args.store_name, code=args.store_code, is_active=True
            )
            db.add(store)
            db.flush()
            print(f"created store {store.code}")
        manager = User(
            email=args.email,
            hashed_password=hash_password(password),
            full_name=args.name,
            role=UserRole.MANAGER,
            store_id=store.id,
            is_active=True,
        )
        db.add(manager)
        db.commit()
        print(f"manager {args.email} created for store {store.code}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
