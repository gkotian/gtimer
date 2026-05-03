from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from gtimer.admin import calculate_balance
from gtimer.config import AppConfig, AllowanceConfig, MatchRule, TimerConfig
from gtimer.models import WindowInfo
from gtimer.persistence import TimeStore


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
                credit_weekdays=(),
                credit_seconds=3600,
            )
        },
        ignore=MatchRule(title_contains=("gTimer",)),
    )


class AdminBalanceTests(unittest.TestCase):
    def test_balance_includes_open_matching_interval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            store.add_allowance_event(
                account_name="minecraft",
                event_type="adjustment",
                amount_seconds=3600,
                effective_date="2026-05-03",
                created_at=100.0,
                note="Initial correction",
                source_key="adjustment:minecraft:test",
            )
            store.add_allowance_event(
                account_name="minecraft",
                event_type="adjustment",
                amount_seconds=-300,
                effective_date="2026-05-03",
                created_at=101.0,
                note="Deduct",
                source_key="adjustment:minecraft:test-negative",
            )
            window_id = store.upsert_window(WindowInfo("Minecraft", "java", "launcher"), 100.0)
            closed = store.start_interval(window_id, 100.0)
            store.end_interval(closed, 700.0)
            store.start_interval(window_id, 1000.0)

            summary = calculate_balance(test_config(), store, "minecraft", now=1300.0)
            store.close()

        self.assertEqual(summary.credit_seconds, 3300.0)
        self.assertEqual(summary.adjustment_seconds, 3300.0)
        self.assertEqual(summary.usage_seconds, 900.0)
        self.assertEqual(summary.balance_seconds, 2400.0)


if __name__ == "__main__":
    unittest.main()
