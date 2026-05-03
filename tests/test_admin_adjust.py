from __future__ import annotations

from argparse import Namespace
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gtimer.admin import _adjust
from gtimer.auth import set_password
from gtimer.persistence import TimeStore


class AdminAdjustTests(unittest.TestCase):
    def test_adjust_accepts_negative_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = base / "config.toml"
            database_path = base / "gtimer.db"
            password_file = base / "admin_password.json"
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
            set_password("secret", password_file)

            args = Namespace(
                account="minecraft",
                hours=0.0,
                minutes=-5.0,
                seconds=0.0,
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


if __name__ == "__main__":
    unittest.main()
