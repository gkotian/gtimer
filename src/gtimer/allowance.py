from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .config import AllowanceConfig, AppConfig
from .matching import matches_rule
from .models import AllowanceLedgerEntry, AllowanceSummary
from .persistence import TimeStore


class AllowanceManager:
    def __init__(self, config: AppConfig, store: TimeStore) -> None:
        self.config = config
        self.store = store
        self._last_reconciled: dict[str, date] = {}

    def for_timer(
        self,
        timer_name: str,
        usage_seconds: float,
        now: float,
    ) -> AllowanceSummary | None:
        allowance = self._allowance_for_timer(timer_name)
        if allowance is None or not allowance.enabled:
            return None
        self.reconcile(now)
        totals = self.store.allowance_totals(allowance.name)
        credit_seconds = totals["total"]
        return AllowanceSummary(
            account_name=allowance.name,
            timer_name=timer_name,
            usage_seconds=usage_seconds,
            credit_seconds=credit_seconds,
            scheduled_seconds=totals["scheduled"],
            adjustment_seconds=totals["adjustment"],
            balance_seconds=credit_seconds - usage_seconds,
        )

    def reconcile(self, now: float) -> None:
        today = datetime.fromtimestamp(now).date()
        for allowance in self.config.allowances.values():
            if not allowance.enabled:
                continue
            if self._last_reconciled.get(allowance.name) == today:
                continue
            self._reconcile_allowance(allowance, today, now)
            self._last_reconciled[allowance.name] = today

    def recent_entries(
        self,
        timer_name: str,
        daily_usage: dict[date, float],
        now: float,
        limit: int = 10,
    ) -> tuple[AllowanceLedgerEntry, ...]:
        allowance = self._allowance_for_timer(timer_name)
        if allowance is None or not allowance.enabled:
            return ()
        self.reconcile(now)

        ordered: list[tuple[float, AllowanceLedgerEntry]] = []
        for event in self.store.allowance_events(allowance.name):
            if event.event_type == "scheduled":
                label = "Scheduled allowance"
            else:
                label = event.note or ""
            ordered.append(
                (
                    event.created_at,
                    AllowanceLedgerEntry(
                        effective_date=event.effective_date,
                        timestamp=event.created_at,
                        label=label,
                        amount_seconds=event.amount_seconds,
                        entry_type="credit" if event.amount_seconds >= 0 else "debit",
                    ),
                )
            )

        for usage_date, usage_seconds in daily_usage.items():
            if usage_seconds <= 0:
                continue
            sort_ts = datetime.combine(usage_date, time.max).timestamp()
            ordered.append(
                (
                    sort_ts,
                    AllowanceLedgerEntry(
                        effective_date=usage_date,
                        timestamp=sort_ts,
                        label="Minecraft time used",
                        amount_seconds=-usage_seconds,
                        entry_type="debit",
                    ),
                )
            )

        ordered.sort(key=lambda item: item[0], reverse=True)
        return tuple(entry for _, entry in ordered[:limit])

    def _reconcile_allowance(
        self,
        allowance: AllowanceConfig,
        today: date,
        now: float,
    ) -> None:
        timer = self.config.timers.get(allowance.timer_name)
        if timer is None:
            return

        first_date = self._first_relevant_date(allowance, today)
        for credit_date in _date_range(first_date, today):
            if credit_date.weekday() not in allowance.credit_weekdays:
                continue
            self.store.add_allowance_event(
                account_name=allowance.name,
                event_type="scheduled",
                amount_seconds=allowance.credit_seconds,
                effective_date=credit_date.isoformat(),
                created_at=now,
                note="Scheduled allowance credit",
                source_key=f"scheduled:{allowance.name}:{credit_date.isoformat()}",
            )

    def _first_relevant_date(self, allowance: AllowanceConfig, today: date) -> date:
        timer = self.config.timers.get(allowance.timer_name)
        dates: list[date] = []
        if timer is not None:
            for bounds in self.store.window_activity_bounds():
                if matches_rule(bounds.info, timer.match):
                    dates.append(datetime.fromtimestamp(bounds.first_started_at).date())

        event_date = self.store.earliest_allowance_event_date(allowance.name)
        if event_date is not None:
            dates.append(date.fromisoformat(event_date))

        if not dates:
            return today
        return min(dates)

    def _allowance_for_timer(self, timer_name: str) -> AllowanceConfig | None:
        for allowance in self.config.allowances.values():
            if allowance.timer_name == timer_name:
                return allowance
        return None


def _date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
