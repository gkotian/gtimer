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


if __name__ == "__main__":
    unittest.main()
