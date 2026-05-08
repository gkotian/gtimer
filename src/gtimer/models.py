from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class WindowInfo:
    title: str
    window_class: str | None = None
    instance: str | None = None

    @property
    def display_title(self) -> str:
        return self.title or self.window_class or self.instance or "Unknown window"

    @property
    def display_application(self) -> str:
        return self.window_class or self.instance or self.display_title


@dataclass(frozen=True)
class WindowTotal:
    key: str
    info: WindowInfo
    total_seconds: float
    last_focused_at: float | None


@dataclass(frozen=True)
class WindowActivityBounds:
    info: WindowInfo
    first_started_at: float
    last_started_at: float


@dataclass(frozen=True)
class FocusIntervalRecord:
    info: WindowInfo
    started_at: float
    ended_at: float


@dataclass(frozen=True)
class TimerTotal:
    name: str
    label: str
    total_seconds: float
    prominent: bool


@dataclass(frozen=True)
class TrackerSnapshot:
    timers: dict[str, TimerTotal]
    prominent_timer: TimerTotal
    window_totals: tuple[WindowTotal, ...]
    total_tracked_seconds: float
    active_window: WindowInfo | None
    active_window_started_at: float | None


@dataclass(frozen=True)
class AllowanceSummary:
    account_name: str
    timer_name: str
    usage_seconds: float
    credit_seconds: float
    scheduled_seconds: float
    adjustment_seconds: float
    balance_seconds: float


@dataclass(frozen=True)
class AllowanceEvent:
    account_name: str
    event_type: str
    amount_seconds: float
    effective_date: date
    created_at: float
    note: str | None


@dataclass(frozen=True)
class AllowanceLedgerEntry:
    effective_date: date
    timestamp: float
    label: str
    amount_seconds: float
    entry_type: str
