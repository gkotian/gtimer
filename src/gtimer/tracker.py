from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .config import AppConfig
from .identity import window_key
from .matching import matches_rule
from .models import TimerTotal, TrackerSnapshot, WindowInfo, WindowTotal
from .persistence import TimeStore


def start_of_today(timestamp: float | None = None) -> float:
    current = datetime.fromtimestamp(timestamp) if timestamp is not None else datetime.now()
    return current.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


class FocusTracker:
    def __init__(self, config: AppConfig, store: TimeStore) -> None:
        self.config = config
        self.store = store
        self.active_window: WindowInfo | None = None
        self.active_interval_id: int | None = None
        self.active_started_at: float | None = None
        self.active_started_monotonic: float | None = None
        self.store.abandon_open_intervals()

    def focus_changed(self, window: WindowInfo | None, now: float, monotonic_now: float) -> None:
        self._close_active(now)
        if window is None or matches_rule(window, self.config.ignore):
            self.active_window = None
            self.active_interval_id = None
            self.active_started_at = None
            self.active_started_monotonic = None
            return

        window_id = self.store.upsert_window(window, now)
        self.active_interval_id = self.store.start_interval(window_id, now)
        self.active_window = window
        self.active_started_at = now
        self.active_started_monotonic = monotonic_now

    def shutdown(self, now: float) -> None:
        self._close_active(now)

    def snapshot(
        self,
        now: float,
        monotonic_now: float,
        since: float | None = None,
    ) -> TrackerSnapshot:
        since = start_of_today(now) if since is None else since
        totals_by_key = {total.key: total for total in self.store.window_totals(since)}

        if (
            self.active_window is not None
            and self.active_started_at is not None
            and self.active_started_monotonic is not None
        ):
            key = window_key(self.active_window)
            active_seconds = max(0.0, monotonic_now - self.active_started_monotonic)
            if self.active_started_at < since:
                active_seconds = max(0.0, now - since)
            existing = totals_by_key.get(key)
            if existing is None:
                totals_by_key[key] = WindowTotal(
                    key=key,
                    info=self.active_window,
                    total_seconds=active_seconds,
                    last_focused_at=self.active_started_at,
                )
            else:
                totals_by_key[key] = replace(
                    existing,
                    info=self.active_window,
                    total_seconds=existing.total_seconds + active_seconds,
                    last_focused_at=self.active_started_at,
                )

        window_totals = tuple(
            sorted(totals_by_key.values(), key=lambda total: total.total_seconds, reverse=True)
        )
        timer_totals: dict[str, TimerTotal] = {}
        for timer in self.config.timers.values():
            total_seconds = sum(
                total.total_seconds
                for total in window_totals
                if matches_rule(total.info, timer.match)
            )
            timer_totals[timer.name] = TimerTotal(
                name=timer.name,
                label=timer.label,
                total_seconds=total_seconds,
                prominent=timer.prominent,
            )

        prominent_config = self.config.prominent_timer()
        prominent = timer_totals[prominent_config.name]
        return TrackerSnapshot(
            timers=timer_totals,
            prominent_timer=prominent,
            window_totals=window_totals,
            total_tracked_seconds=sum(total.total_seconds for total in window_totals),
            active_window=self.active_window,
            active_window_started_at=self.active_started_at,
        )

    def _close_active(self, now: float) -> None:
        if self.active_interval_id is not None:
            self.store.end_interval(self.active_interval_id, now)
        self.active_window = None
        self.active_interval_id = None
        self.active_started_at = None
        self.active_started_monotonic = None
