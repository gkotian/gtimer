from __future__ import annotations

from argparse import Namespace
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gtimer.admin import _adjust, main, parse_duration
from gtimer.auth import set_password
from gtimer.persistence import TimeStore


def _write_config(config_path: Path, database_path: Path) -> None:
    config_path.write_text(
        f"""
        [app]
        database_path = "{database_path}"

        [timers.minecraft]
        label = "Minecraft"
        prominent = true
        title_contains = ["Minecraft"]

        [allowances.minecraft]
        timer = "minecraft"
        enabled = true
        credit_days = []
        credit_seconds = 3600
        """,
        encoding="utf-8",
    )


class AdminAdjustTests(unittest.TestCase):
    def test_adjust_accepts_negative_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = base / "config.toml"
            database_path = base / "gtimer.db"
            password_file = base / "admin_password.json"
            _write_config(config_path, database_path)
            set_password("secret", password_file)

            args = Namespace(
                account="minecraft",
                duration="-5m",
                note="Correction",
                config=config_path,
                database=database_path,
                password_file=password_file,
            )
            with patch("getpass.getpass", return_value="secret"):
                with redirect_stdout(io.StringIO()):
                    result = _adjust(args)

            store = TimeStore(database_path)
            try:
                totals = store.allowance_totals("minecraft")
            finally:
                store.close()

        self.assertEqual(result, 0)
        self.assertEqual(totals["total"], -300.0)
        self.assertEqual(totals["adjustment"], -300.0)

    def test_main_accepts_shorthand_duration_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = base / "config.toml"
            database_path = base / "gtimer.db"
            password_file = base / "admin_password.json"
            _write_config(config_path, database_path)
            set_password("secret", password_file)

            argv = [
                "adjust",
                "minecraft",
                "-47m",
                "--note",
                "Correction",
                "--config",
                str(config_path),
                "--database",
                str(database_path),
                "--password-file",
                str(password_file),
            ]
            with patch("getpass.getpass", return_value="secret"):
                with redirect_stdout(io.StringIO()):
                    result = main(argv)

            store = TimeStore(database_path)
            try:
                totals = store.allowance_totals("minecraft")
            finally:
                store.close()

        self.assertEqual(result, 0)
        self.assertEqual(totals["adjustment"], -47 * 60.0)


class ParseDurationTests(unittest.TestCase):
    def test_parses_signed_minutes(self) -> None:
        self.assertEqual(parse_duration("-47m"), -47 * 60.0)
        self.assertEqual(parse_duration("+30m"), 30 * 60.0)

    def test_parses_hours(self) -> None:
        self.assertEqual(parse_duration("+2h"), 7200.0)
        self.assertEqual(parse_duration("1.5h"), 5400.0)

    def test_parses_seconds(self) -> None:
        self.assertEqual(parse_duration("30s"), 30.0)

    def test_unsigned_is_positive(self) -> None:
        self.assertEqual(parse_duration("15m"), 900.0)

    def test_rejects_invalid_token(self) -> None:
        with self.assertRaises(ValueError):
            parse_duration("47")
        with self.assertRaises(ValueError):
            parse_duration("47x")
        with self.assertRaises(ValueError):
            parse_duration("m")


if __name__ == "__main__":
    unittest.main()
