from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config


def main() -> int:
    import gi

    from gi.repository import GLib

    GLib.set_prgname("gtimer")
    GLib.set_application_name("gTimer")

    from .ui import run

    parser = argparse.ArgumentParser(description="Run gTimer.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to a TOML config file. Defaults to ./config.toml.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="Override the SQLite database path from config.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    if args.database is not None:
        config.database_path = args.database.expanduser()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
