from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from gtimer.allowance import AllowanceManager
from gtimer.config import AppConfig, AllowanceConfig, MatchRule, TimerConfig
from gtimer.models import WindowInfo
from gtimer.persistence import TimeStore


def timestamp(year: int, month: int, day: int, hour: int = 12) -> float:
    return datetime(year, month, day, hour).timestamp()


def test_config() -> AppConfig:
    return AppConfig(
        timers={
            "minecraft": TimerConfig(
                name="minecraft",
                label="Minecraft",
                prominent=True,
                match=MatchRule(title_contains=("Minecraft",)),
            )
        },
        allowances={
            "minecraft": AllowanceConfig(
                name="minecraft",
                timer_name="minecraft",
                enabled=True,
                credit_weekdays=(4, 5, 6),
                credit_seconds=3600,
            )
        },
        ignore=MatchRule(title_contains=("gTimer",)),
    )


class AllowanceTests(unittest.TestCase):
    def test_reconciles_weekend_credits_from_first_matching_activity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            window_id = store.upsert_window(WindowInfo("Minecraft", "java", "launcher"), 100.0)
            interval_id = store.start_interval(window_id, timestamp(2026, 5, 1))
            store.end_interval(interval_id, timestamp(2026, 5, 1, 13))

            manager = AllowanceManager(test_config(), store)
            summary = manager.for_timer(
                "minecraft",
                usage_seconds=3600,
                now=timestamp(2026, 5, 4),
            )
            store.close()

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.scheduled_seconds, 10800.0)
        self.assertEqual(summary.balance_seconds, 7200.0)

    def test_reconcile_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            window_id = store.upsert_window(WindowInfo("Minecraft", "java", "launcher"), 100.0)
            interval_id = store.start_interval(window_id, timestamp(2026, 5, 1))
            store.end_interval(interval_id, timestamp(2026, 5, 1, 13))

            manager = AllowanceManager(test_config(), store)
            manager.reconcile(timestamp(2026, 5, 4))
            manager.reconcile(timestamp(2026, 5, 4))
            totals = store.allowance_totals("minecraft")
            store.close()

        self.assertEqual(totals["scheduled"], 10800.0)


if __name__ == "__main__":
    unittest.main()
