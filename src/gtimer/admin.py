from __future__ import annotations

import argparse
from datetime import date
import getpass
import json
from pathlib import Path
import re
import sys
import time
import uuid

from .auth import DEFAULT_PASSWORD_FILE, password_file_exists, set_password, verify_password
from .allowance import AllowanceManager
from .config import AppConfig, load_config
from .formatting import format_duration, format_signed_duration
from .matching import matches_rule
from .models import AllowanceSummary
from .persistence import TimeStore


_DURATION_TOKEN_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?[hms]$")
_DURATION_UNITS = {"h": 3600.0, "m": 60.0, "s": 1.0}


def parse_duration(token: str) -> float:
    if not _DURATION_TOKEN_RE.match(token):
        raise ValueError(
            f"Invalid duration {token!r}. Use a value like -47m, +30m, +2h, or 30s."
        )
    return float(token[:-1]) * _DURATION_UNITS[token[-1]]


def _rewrite_duration_argv(argv: list[str]) -> list[str]:
    """Rewrite the first bare duration token (e.g. ``-47m``) to ``--duration=<token>``.

    Why: argparse would otherwise treat ``-47m`` as an unknown option flag.
    """
    rewritten = list(argv)
    for i, token in enumerate(rewritten):
        if _DURATION_TOKEN_RE.match(token):
            rewritten[i] = f"--duration={token}"
            break
    return rewritten


def main(argv: list[str] | None = None) -> int:
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

    password_common = argparse.ArgumentParser(add_help=False, parents=[common])
    password_common.add_argument(
        "--password-file",
        type=Path,
        default=DEFAULT_PASSWORD_FILE,
        help="Path to the admin password hash file.",
    )

    balance_common = argparse.ArgumentParser(add_help=False, parents=[common])

    subparsers.add_parser(
        "set-password",
        parents=[password_common],
        help="Create or replace the admin password.",
    )

    adjust = subparsers.add_parser(
        "adjust",
        parents=[password_common],
        help="Add a password-protected positive or negative allowance adjustment.",
    )
    adjust.add_argument("account", help="Allowance account name, for example minecraft.")
    adjust.add_argument(
        "--duration",
        required=True,
        help="Adjustment amount, for example -47m, +30m, +2h, or 30s.",
    )
    adjust.add_argument(
        "--note",
        required=True,
        help="Note stored with the adjustment.",
    )

    balance_parser = subparsers.add_parser(
        "balance",
        parents=[balance_common],
        help="Show the current allowance balance without changing the database.",
    )
    balance_parser.add_argument("account", help="Allowance account name, for example minecraft.")

    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(_rewrite_duration_argv(raw_argv))
    if args.command == "set-password":
        return _set_password(args.password_file.expanduser())
    if args.command == "adjust":
        return _adjust(args)
    if args.command == "balance":
        return _balance(args)
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


def _adjust(args: argparse.Namespace) -> int:
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

    try:
        amount_seconds = parse_duration(args.duration)
    except ValueError as error:
        print(error)
        return 1
    if amount_seconds == 0:
        print("Adjustment must not be zero.")
        return 1

    now = time.time()
    effective_date = date.fromtimestamp(now).isoformat()
    store = TimeStore(config.database_path)
    try:
        store.add_allowance_event(
            account_name=args.account,
            event_type="adjustment",
            amount_seconds=amount_seconds,
            effective_date=effective_date,
            created_at=now,
            note=args.note,
            source_key=f"adjustment:{args.account}:{uuid.uuid4()}",
        )
    finally:
        store.close()

    print(json.dumps({
        "account": args.account,
        "adjustment": format_signed_duration(amount_seconds, include_plus=True),
        "note": args.note,
    }))
    return 0


def _balance(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.database is not None:
        config.database_path = args.database.expanduser()

    if args.account not in config.allowances:
        accounts = ", ".join(sorted(config.allowances)) or "none configured"
        print(f"Unknown allowance account: {args.account}")
        print(f"Configured allowance accounts: {accounts}")
        return 1

    now = time.time()
    store = TimeStore(config.database_path)
    try:
        summary = calculate_balance(config, store, args.account, now)
    finally:
        store.close()

    print(f"Account: {summary.account_name}")
    print(
        f"Remaining: {format_signed_duration(summary.balance_seconds)} "
        f"({int(summary.balance_seconds)} seconds)"
    )
    print(f"Credits: {format_duration(summary.credit_seconds)} ({int(summary.credit_seconds)} seconds)")
    print(f"Used: {format_duration(summary.usage_seconds)} ({int(summary.usage_seconds)} seconds)")
    print(f"Database: {config.database_path}")
    return 0


def calculate_balance(
    config: AppConfig,
    store: TimeStore,
    account_name: str,
    now: float,
) -> AllowanceSummary:
    allowance = config.allowances[account_name]
    timer = config.timers[allowance.timer_name]
    usage_seconds = sum(
        max(0.0, interval.ended_at - interval.started_at)
        for interval in store.focus_intervals(open_ended_at=now)
        if matches_rule(interval.info, timer.match)
    )
    summary = AllowanceManager(config, store).for_timer(timer.name, usage_seconds, now)
    if summary is None:
        raise RuntimeError(f"Allowance account is disabled: {account_name}")
    return summary


if __name__ == "__main__":
    raise SystemExit(main())
