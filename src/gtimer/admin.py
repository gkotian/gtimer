from __future__ import annotations

import argparse
from datetime import date
import getpass
from pathlib import Path
import time
import uuid

from .auth import DEFAULT_PASSWORD_FILE, password_file_exists, set_password, verify_password
from .config import load_config
from .formatting import format_duration
from .persistence import TimeStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Admin commands for gTimer.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to config.toml. Defaults to ./config.toml.",
    )
    common.add_argument(
        "--database",
        type=Path,
        default=None,
        help="Override the SQLite database path from config.",
    )
    common.add_argument(
        "--password-file",
        type=Path,
        default=DEFAULT_PASSWORD_FILE,
        help="Path to the admin password hash file.",
    )

    subparsers.add_parser(
        "set-password",
        parents=[common],
        help="Create or replace the admin password.",
    )

    bonus = subparsers.add_parser(
        "add-bonus",
        parents=[common],
        help="Add password-protected bonus allowance time.",
    )
    bonus.add_argument("account", help="Allowance account name, for example minecraft.")
    bonus.add_argument("--hours", type=float, default=0.0, help="Bonus hours to add.")
    bonus.add_argument("--minutes", type=float, default=0.0, help="Bonus minutes to add.")
    bonus.add_argument("--seconds", type=float, default=0.0, help="Bonus seconds to add.")
    bonus.add_argument("--note", default=None, help="Optional note stored with the bonus event.")

    args = parser.parse_args()
    if args.command == "set-password":
        return _set_password(args.password_file.expanduser())
    if args.command == "add-bonus":
        return _add_bonus(args)
    raise AssertionError(f"Unhandled command: {args.command}")


def _set_password(password_file: Path) -> int:
    password = getpass.getpass("New admin password: ")
    confirmation = getpass.getpass("Confirm admin password: ")
    if password != confirmation:
        print("Passwords did not match.")
        return 1
    try:
        set_password(password, password_file)
    except ValueError as error:
        print(error)
        return 1
    print(f"Admin password saved to {password_file}")
    return 0


def _add_bonus(args: argparse.Namespace) -> int:
    password_file = args.password_file.expanduser()
    if not password_file_exists(password_file):
        print(f"No admin password is configured at {password_file}")
        print("Run: PYTHONPATH=src python -m gtimer.admin set-password")
        return 1

    password = getpass.getpass("Admin password: ")
    if not verify_password(password, password_file):
        print("Invalid admin password.")
        return 1

    config = load_config(args.config)
    if args.database is not None:
        config.database_path = args.database.expanduser()

    if args.account not in config.allowances:
        accounts = ", ".join(sorted(config.allowances)) or "none configured"
        print(f"Unknown allowance account: {args.account}")
        print(f"Configured allowance accounts: {accounts}")
        return 1

    amount_seconds = args.hours * 3600 + args.minutes * 60 + args.seconds
    if amount_seconds <= 0:
        print("Bonus time must be greater than zero.")
        return 1

    now = time.time()
    effective_date = date.fromtimestamp(now).isoformat()
    store = TimeStore(config.database_path)
    try:
        store.add_allowance_event(
            account_name=args.account,
            event_type="bonus",
            amount_seconds=amount_seconds,
            effective_date=effective_date,
            created_at=now,
            note=args.note,
            source_key=f"bonus:{args.account}:{uuid.uuid4()}",
        )
    finally:
        store.close()

    print(f"Added {format_duration(amount_seconds)} bonus time to {args.account}.")
    print(f"Database: {config.database_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
