from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from gtimer.config import AppConfig, MatchRule, TimerConfig
from gtimer.models import WindowInfo
from gtimer.persistence import TimeStore
from gtimer.tracker import FocusTracker


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
        ignore=MatchRule(title_contains=("gTimer",)),
    )


class TrackerTests(unittest.TestCase):
    def test_active_window_contributes_live_time_to_prominent_timer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            tracker = FocusTracker(test_config(), store)

            tracker.focus_changed(WindowInfo("Minecraft", "java", "launcher"), 1000.0, 20.0)
            snapshot = tracker.snapshot(now=1015.0, monotonic_now=35.0, since=0.0)
            tracker.shutdown(1015.0)
            store.close()

        self.assertEqual(snapshot.prominent_timer.total_seconds, 15.0)
        self.assertEqual(snapshot.total_tracked_seconds, 15.0)

    def test_focus_change_closes_previous_interval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            tracker = FocusTracker(test_config(), store)

            tracker.focus_changed(WindowInfo("Minecraft", "java", "launcher"), 1000.0, 20.0)
            tracker.focus_changed(WindowInfo("Terminal", "Alacritty", "Alacritty"), 1010.0, 30.0)
            snapshot = tracker.snapshot(now=1020.0, monotonic_now=40.0, since=0.0)
            tracker.shutdown(1020.0)
            store.close()

        totals = {total.info.display_title: total.total_seconds for total in snapshot.window_totals}
        self.assertEqual(totals["Minecraft"], 10.0)
        self.assertEqual(totals["Terminal"], 10.0)
        self.assertEqual(snapshot.prominent_timer.total_seconds, 10.0)

    def test_ignored_window_is_not_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TimeStore(Path(tmpdir) / "gtimer.db")
            tracker = FocusTracker(test_config(), store)

            tracker.focus_changed(WindowInfo("gTimer", "gtimer", "gtimer"), 1000.0, 20.0)
            snapshot = tracker.snapshot(now=1010.0, monotonic_now=30.0, since=0.0)
            store.close()

        self.assertEqual(snapshot.total_tracked_seconds, 0.0)
        self.assertEqual(snapshot.window_totals, ())


if __name__ == "__main__":
    unittest.main()
