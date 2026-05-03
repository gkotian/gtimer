from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from gtimer.models import WindowInfo
from gtimer.persistence import TimeStore


class PersistenceTests(unittest.TestCase):
    def test_persists_intervals_and_derives_totals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            window_id = store.upsert_window(WindowInfo("Minecraft", "java", "launcher"), 100.0)
            interval_id = store.start_interval(window_id, 100.0)
            store.end_interval(interval_id, 130.0)

            totals = store.window_totals()
            store.close()

        self.assertEqual(len(totals), 1)
        self.assertEqual(totals[0].total_seconds, 30.0)

    def test_abandoned_open_intervals_do_not_accumulate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            window_id = store.upsert_window(WindowInfo("Minecraft", "java", "launcher"), 100.0)
            store.start_interval(window_id, 100.0)

            abandoned = store.abandon_open_intervals()
            totals = store.window_totals()
            store.close()

        self.assertEqual(abandoned, 1)
        self.assertEqual(totals[0].total_seconds, 0.0)

    def test_totals_can_be_limited_since_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            window_id = store.upsert_window(WindowInfo("Minecraft", "java", "launcher"), 100.0)
            interval_id = store.start_interval(window_id, 100.0)
            store.end_interval(interval_id, 130.0)

            totals = store.window_totals(since=120.0)
            store.close()

        self.assertEqual(totals[0].total_seconds, 10.0)

    def test_focus_intervals_can_include_open_interval_for_read_only_balance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            window_id = store.upsert_window(WindowInfo("Minecraft", "java", "launcher"), 100.0)
            store.start_interval(window_id, 100.0)

            closed_only = store.focus_intervals()
            with_open = store.focus_intervals(open_ended_at=130.0)
            store.close()

        self.assertEqual(closed_only, ())
        self.assertEqual(len(with_open), 1)
        self.assertEqual(with_open[0].started_at, 100.0)
        self.assertEqual(with_open[0].ended_at, 130.0)

    def test_allowance_events_are_deduplicated_by_source_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            first = store.add_allowance_event(
                account_name="minecraft",
                event_type="scheduled",
                amount_seconds=3600,
                effective_date="2026-05-01",
                created_at=100.0,
                note="Scheduled",
                source_key="scheduled:minecraft:2026-05-01",
            )
            second = store.add_allowance_event(
                account_name="minecraft",
                event_type="scheduled",
                amount_seconds=3600,
                effective_date="2026-05-01",
                created_at=101.0,
                note="Scheduled",
                source_key="scheduled:minecraft:2026-05-01",
            )
            totals = store.allowance_totals("minecraft")
            store.close()

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(totals["total"], 3600.0)

    def test_allowance_totals_include_negative_adjustments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            store.add_allowance_event(
                account_name="minecraft",
                event_type="adjustment",
                amount_seconds=1800,
                effective_date="2026-05-03",
                created_at=100.0,
                note="Add",
                source_key="adjustment:minecraft:add",
            )
            store.add_allowance_event(
                account_name="minecraft",
                event_type="adjustment",
                amount_seconds=-300,
                effective_date="2026-05-03",
                created_at=101.0,
                note="Deduct",
                source_key="adjustment:minecraft:deduct",
            )

            totals = store.allowance_totals("minecraft")
            store.close()

        self.assertEqual(totals["total"], 1500.0)
        self.assertEqual(totals["adjustment"], 1500.0)


if __name__ == "__main__":
    unittest.main()
