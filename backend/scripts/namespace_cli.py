"""Ops CLI for namespace CRUD on the singleton tenant.

The dashboard authenticates against ONE F5 XC tenant with ONE token but
watches MULTIPLE namespaces within it. This tool manages the watched-
namespaces list.

Subcommands:
    list                              Show current namespaces
    add NAMESPACE                     Probe + append (validates against F5 XC)
    remove NAMESPACE                  Remove from list (refuses to leave empty)
    replace NAMESPACES (comma-sep)    Bulk replace (probes each new entry)

Run via the entrypoint shim:

    docker compose exec backend /app/scripts/entrypoint.sh \\
        python -m scripts.namespace_cli <subcommand> [args...]

Probe-on-add hits F5 XC's namespace registry endpoint and refuses to add
non-existent namespaces. This catches typos and bad RBAC at write time.
"""
from __future__ import annotations

import argparse
import sys

from app.db import SessionLocal
from app.logging_config import configure_logging
from app.services.namespaces import (
    LastNamespaceError,
    NamespaceAlreadyPresent,
    NamespaceNotPresent,
    NamespaceProbeError,
    NamespaceServiceError,
    add_namespace,
    list_namespaces,
    remove_namespace,
    replace_namespaces,
)

configure_logging()


def cmd_list(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        ns = list_namespaces(db)
        print(f"Namespaces ({len(ns)}):")
        for n in ns:
            print(f"  - {n}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        try:
            new_list = add_namespace(db, args.namespace)
            db.commit()
        except NamespaceAlreadyPresent as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        except NamespaceProbeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            if e.status_code == 404:
                print(
                    "  hint: namespace does not exist in F5 XC, or your token "
                    "lacks read access. Verify in console.ves.volterra.io.",
                    file=sys.stderr,
                )
            return 1
        except NamespaceServiceError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"OK — added {args.namespace!r}")
        print(f"namespaces ({len(new_list)}): {new_list}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        try:
            new_list = remove_namespace(db, args.namespace)
            db.commit()
        except NamespaceNotPresent as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        except LastNamespaceError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            print(
                "  hint: use `make namespace-replace NAMESPACES=<other>` to swap "
                "the last namespace if intentional.",
                file=sys.stderr,
            )
            return 1
        except NamespaceServiceError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"OK — removed {args.namespace!r}")
        print(f"namespaces ({len(new_list)}): {new_list}")
    return 0


def cmd_replace(args: argparse.Namespace) -> int:
    namespaces = [n.strip() for n in args.namespaces.split(",") if n.strip()]
    if not namespaces:
        print("ERROR: NAMESPACES list is empty", file=sys.stderr)
        return 2

    print(f"Will replace current namespaces with: {namespaces}")
    if not args.yes:
        confirm = input("Continue? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return 2

    with SessionLocal() as db:
        try:
            new_list = replace_namespaces(db, namespaces)
            db.commit()
        except NamespaceProbeError as e:
            print(f"ERROR: probe failed: {e}", file=sys.stderr)
            return 1
        except NamespaceServiceError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"OK — replaced. namespaces ({len(new_list)}): {new_list}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="namespace_cli",
        description="Namespace CRUD CLI (F5 XC Dashboard, ops-only)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List current namespaces")

    p_add = sub.add_parser("add", help="Add a namespace (probes F5 XC)")
    p_add.add_argument("namespace")

    p_remove = sub.add_parser("remove", help="Remove a namespace")
    p_remove.add_argument("namespace")

    p_replace = sub.add_parser("replace", help="Bulk replace namespace list (comma-sep)")
    p_replace.add_argument("namespaces", help="comma-separated list, e.g. 'shared,foo,bar'")
    p_replace.add_argument("--yes", "-y", action="store_true", help="skip confirmation prompt")

    args = parser.parse_args()

    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "add":
        return cmd_add(args)
    if args.cmd == "remove":
        return cmd_remove(args)
    if args.cmd == "replace":
        return cmd_replace(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
