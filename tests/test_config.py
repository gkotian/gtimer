from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from gtimer.config import load_config


class ConfigTests(unittest.TestCase):
    def test_loads_multiple_named_timers_and_ignore_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text(
                """
                [app]
                database_path = "~/tmp/gtimer.db"
                refresh_interval_ms = 500
                regular_application_limit = 3

                [timers.minecraft]
                label = "Minecraft"
                prominent = true
                title_contains = ["Minecraft"]

                [timers.browser]
                label = "Browser"
                class_contains = ["Firefox"]

                [ignore]
                title_contains = ["gTimer"]
                """,
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.refresh_interval_ms, 500)
        self.assertEqual(config.regular_application_limit, 3)
        self.assertEqual(config.prominent_timer().name, "minecraft")
        self.assertIn("browser", config.timers)
        self.assertEqual(config.ignore.title_contains, ("gTimer",))

    def test_missing_config_uses_defaults(self) -> None:
        config = load_config(Path("/does/not/exist.toml"))

        self.assertEqual(config.prominent_timer().name, "minecraft")
        self.assertEqual(config.ignore.title_contains, ("gTimer",))


if __name__ == "__main__":
    unittest.main()
