"""Command-line interface.

Usage:
  python -m backend.cli migrate
"""
import argparse
import sys

from backend import config
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


def cmd_migrate(_args) -> int:
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        applied = apply_migrations(conn, discover_migrations())
    finally:
        conn.close()
    if applied:
        print(f"Applied {len(applied)} migrations: {', '.join(applied)}")
    else:
        print("No pending migrations.")
    return 0


COMMANDS = {
    "migrate": cmd_migrate,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backend.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply pending DB migrations")

    args = parser.parse_args(argv)
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.error(f"unknown command: {args.command}")
        return 2
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
