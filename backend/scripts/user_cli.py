"""Ops CLI for user CRUD. Mirrors tenant_cli pattern.

User management is CLI-only by design — admins do NOT create users via
the dashboard UI. This tool runs inside the backend container, prompts
ops admins for inputs, and never accepts passwords on the command line.

Subcommands:
    list [--tenant <id-or-name>]     List users (optionally filtered by tenant)
    get <id-or-username>             Fetch one user
    add                              Interactive: prompts for fields + password
    rotate-password <id-or-username> Rotate password (interactive)
    set-role <id-or-username> <role> Change role (admin | viewer)
    deactivate <id-or-username>      Soft-delete via is_active=false
    activate <id-or-username>        Reactivate

Run via the entrypoint shim so DATABASE_URL gets the postgres password
substituted from /run/secrets/postgres_password:

    docker compose exec -it backend /app/scripts/entrypoint.sh \\
        python -m scripts.user_cli <subcommand> [args...]

Password reads use getpass — no echo, no shell history.
"""
from __future__ import annotations

import argparse
import getpass
import sys
import uuid
from typing import Any

from sqlalchemy import select

from app.db import SessionLocal
from app.logging_config import configure_logging
from app.models import Tenant
from app.services.users import (
    DuplicateUsername,
    LastActiveAdminError,
    ROLE_ADMIN,
    ROLE_VIEWER,
    TenantNotFoundForAssignment,
    UserNotFound,
    UserServiceError,
    VALID_ROLES,
    create_user,
    get_user,
    list_users,
    set_active,
    set_password,
    set_role,
)



class TenantNotFound(Exception):
    """Raised by _resolve_tenant_arg when a tenant id/name doesn't match.

    Local definition (not imported from app.services.tenants — that module
    was removed when v0.9.0 multi-tenant work was rolled back).
    """
configure_logging()


def _resolve_tenant_arg(db, id_or_name: str) -> Tenant:
    """Accept tenant UUID OR name."""
    try:
        tid = uuid.UUID(id_or_name)
        t = db.get(Tenant, tid)
        if t is None:
            raise TenantNotFound(f"no tenant with id {id_or_name}")
        return t
    except ValueError:
        pass
    t = db.execute(select(Tenant).where(Tenant.name == id_or_name)).scalar_one_or_none()
    if t is None:
        raise TenantNotFound(f"no tenant matching {id_or_name!r}")
    return t


def _print_table(rows: list[dict[str, Any]], headers: list[str]) -> None:
    if not rows:
        print("(no users)")
        return
    widths = {h: max(len(h), max((len(str(r.get(h, ""))) for r in rows), default=0)) for h in headers}
    sep = "  "
    print(sep.join(h.ljust(widths[h]) for h in headers))
    print(sep.join("-" * widths[h] for h in headers))
    for r in rows:
        print(sep.join(str(r.get(h, "")).ljust(widths[h]) for h in headers))


def cmd_list(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        tenant_id = None
        if args.tenant:
            try:
                t = _resolve_tenant_arg(db, args.tenant)
                tenant_id = t.id
            except TenantNotFound as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 1
        users = list_users(db, tenant_id=tenant_id)
        # Build name lookup for display
        tenants = {t.id: t.name for t in db.execute(select(Tenant)).scalars()}
        rows = [
            {
                "id": str(u.id),
                "username": u.username,
                "role": u.role,
                "active": "yes" if u.is_active else "no",
                "tenant": tenants.get(u.tenant_id, str(u.tenant_id)),
                "email": u.email or "-",
            }
            for u in users
        ]
    _print_table(rows, ["id", "username", "role", "active", "tenant", "email"])
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        try:
            u = get_user(db, args.id_or_username)
        except UserNotFound as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        tenant = db.get(Tenant, u.tenant_id)
        print(f"id:          {u.id}")
        print(f"username:    {u.username}")
        print(f"email:       {u.email or '-'}")
        print(f"role:        {u.role}")
        print(f"is_active:   {u.is_active}")
        print(f"tenant_id:   {u.tenant_id}")
        print(f"tenant_name: {tenant.name if tenant else '?'}")
        print(f"created_at:  {u.created_at}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    username = args.username or input("Username: ").strip()
    email = args.email if args.email is not None else input("Email (blank for none): ").strip() or None
    tenant_input = args.tenant or input("Tenant (id or name): ").strip()
    role = args.role or input(f"Role [{ROLE_ADMIN}|{ROLE_VIEWER}] (default viewer): ").strip() or ROLE_VIEWER

    if not username:
        print("ERROR: username required", file=sys.stderr)
        return 2
    if role not in VALID_ROLES:
        print(f"ERROR: invalid role {role!r} (must be: {sorted(VALID_ROLES)})", file=sys.stderr)
        return 2

    # Password NEVER from CLI args — interactive only
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("ERROR: passwords do not match", file=sys.stderr)
        return 2
    if len(password) < 8:
        print("ERROR: password must be at least 8 characters", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        try:
            t = _resolve_tenant_arg(db, tenant_input)
        except TenantNotFound as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        try:
            u = create_user(
                db,
                username=username,
                email=email,
                password=password,
                tenant_id=t.id,
                role=role,
            )
            db.commit()
            db.refresh(u)
        except DuplicateUsername as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        except TenantNotFoundForAssignment as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        except UserServiceError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"OK — created user {u.username} (id={u.id}) in tenant {t.name}, role={u.role}")
    return 0


def cmd_rotate_password(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        try:
            u = get_user(db, args.id_or_username)
        except UserNotFound as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        password = getpass.getpass(f"New password for {u.username!r}: ")
        confirm = getpass.getpass("Confirm: ")
        if password != confirm:
            print("ERROR: passwords do not match", file=sys.stderr)
            return 2
        try:
            set_password(db, u.id, new_password=password)
            db.commit()
        except UserServiceError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"OK — password rotated for {u.username}")
    return 0


def cmd_set_role(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        try:
            u = get_user(db, args.id_or_username)
        except UserNotFound as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        try:
            set_role(db, u.id, role=args.role)
            db.commit()
        except LastActiveAdminError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        except UserServiceError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"OK — {u.username} role set to {args.role}")
    return 0


def cmd_set_active(args: argparse.Namespace, *, is_active: bool) -> int:
    action = "activated" if is_active else "deactivated"
    with SessionLocal() as db:
        try:
            u = get_user(db, args.id_or_username)
        except UserNotFound as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        try:
            set_active(db, u.id, is_active=is_active)
            db.commit()
        except LastActiveAdminError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        except UserServiceError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"OK — {u.username} {action}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="user_cli",
        description="User CRUD CLI (F5 XC Dashboard, ops-only)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List users")
    p_list.add_argument("--tenant", default=None, help="Filter by tenant id or name")

    p_get = sub.add_parser("get", help="Fetch one user")
    p_get.add_argument("id_or_username")

    p_add = sub.add_parser("add", help="Create a new user (interactive)")
    p_add.add_argument("--username", default=None)
    p_add.add_argument("--email", default=None)
    p_add.add_argument("--tenant", default=None, help="Tenant id or name")
    p_add.add_argument("--role", default=None, choices=sorted(VALID_ROLES) + [None])

    p_rot = sub.add_parser("rotate-password", help="Rotate user password")
    p_rot.add_argument("id_or_username")

    p_role = sub.add_parser("set-role", help="Change user role")
    p_role.add_argument("id_or_username")
    p_role.add_argument("role", choices=sorted(VALID_ROLES))

    p_dea = sub.add_parser("deactivate", help="Soft-delete via is_active=false")
    p_dea.add_argument("id_or_username")

    p_act = sub.add_parser("activate", help="Reactivate")
    p_act.add_argument("id_or_username")

    args = parser.parse_args()

    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "get":
        return cmd_get(args)
    if args.cmd == "add":
        return cmd_add(args)
    if args.cmd == "rotate-password":
        return cmd_rotate_password(args)
    if args.cmd == "set-role":
        return cmd_set_role(args)
    if args.cmd == "deactivate":
        return cmd_set_active(args, is_active=False)
    if args.cmd == "activate":
        return cmd_set_active(args, is_active=True)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
