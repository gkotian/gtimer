from __future__ import annotations

from datetime import date
import sqlite3
from pathlib import Path

from .identity import window_key
from .models import (
    AllowanceEvent,
    FocusIntervalRecord,
    WindowActivityBounds,
    WindowInfo,
    WindowTotal,
)


class TimeStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self.connection.close()

    def _ensure_schema(self) -> None:
        self.connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS windows (
              id INTEGER PRIMARY KEY,
              key TEXT NOT NULL UNIQUE,
              title TEXT NOT NULL,
              window_class TEXT,
              instance TEXT,
              first_seen REAL NOT NULL,
              last_seen REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS focus_intervals (
              id INTEGER PRIMARY KEY,
              window_id INTEGER NOT NULL REFERENCES windows(id),
              started_at REAL NOT NULL,
              ended_at REAL,
              abandoned INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS allowance_events (
              id INTEGER PRIMARY KEY,
              account_name TEXT NOT NULL,
              event_type TEXT NOT NULL,
              amount_seconds REAL NOT NULL,
              effective_date TEXT NOT NULL,
              created_at REAL NOT NULL,
              note TEXT,
              source_key TEXT NOT NULL UNIQUE
            );

            CREATE INDEX IF NOT EXISTS idx_focus_intervals_window
              ON focus_intervals(window_id);
            CREATE INDEX IF NOT EXISTS idx_focus_intervals_started
              ON focus_intervals(started_at);
            CREATE INDEX IF NOT EXISTS idx_focus_intervals_open
              ON focus_intervals(ended_at)
              WHERE ended_at IS NULL;
            CREATE INDEX IF NOT EXISTS idx_allowance_events_account
              ON allowance_events(account_name);
            CREATE INDEX IF NOT EXISTS idx_allowance_events_effective_date
              ON allowance_events(effective_date);
            """
        )
        self.connection.commit()

    def abandon_open_intervals(self) -> int:
        cursor = self.connection.execute(
            """
            UPDATE focus_intervals
               SET abandoned = 1,
                   ended_at = started_at
             WHERE ended_at IS NULL
            """
        )
        self.connection.commit()
        return cursor.rowcount

    def upsert_window(self, window: WindowInfo, seen_at: float) -> int:
        key = window_key(window)
        self.connection.execute(
            """
            INSERT INTO windows(key, title, window_class, instance, first_seen, last_seen)
                 VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                 title = excluded.title,
                 window_class = excluded.window_class,
                 instance = excluded.instance,
                 last_seen = excluded.last_seen
            """,
            (
                key,
                window.title,
                window.window_class,
                window.instance,
                seen_at,
                seen_at,
            ),
        )
        self.connection.commit()
        row = self.connection.execute("SELECT id FROM windows WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise RuntimeError("Failed to upsert window")
        return int(row["id"])

    def start_interval(self, window_id: int, started_at: float) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO focus_intervals(window_id, started_at)
                 VALUES (?, ?)
            """,
            (window_id, started_at),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def end_interval(self, interval_id: int, ended_at: float) -> None:
        self.connection.execute(
            """
            UPDATE focus_intervals
               SET ended_at = ?
             WHERE id = ?
               AND ended_at IS NULL
            """,
            (ended_at, interval_id),
        )
        self.connection.commit()

    def window_totals(self, since: float | None = None) -> tuple[WindowTotal, ...]:
        if since is None:
            rows = self.connection.execute(
                """
                SELECT w.key,
                       w.title,
                       w.window_class,
                       w.instance,
                       COALESCE(SUM(
                         CASE
                           WHEN fi.ended_at IS NOT NULL AND fi.abandoned = 0
                           THEN MAX(0, fi.ended_at - fi.started_at)
                           ELSE 0
                         END
                       ), 0) AS total_seconds,
                       MAX(fi.started_at) AS last_focused_at
                  FROM windows w
                  LEFT JOIN focus_intervals fi ON fi.window_id = w.id
                 GROUP BY w.id
                 ORDER BY total_seconds DESC, w.last_seen DESC
                """
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT w.key,
                       w.title,
                       w.window_class,
                       w.instance,
                       COALESCE(SUM(
                         CASE
                           WHEN fi.ended_at IS NOT NULL
                            AND fi.abandoned = 0
                            AND fi.ended_at > ?
                           THEN MAX(
                             0,
                             fi.ended_at -
                             CASE
                               WHEN fi.started_at < ? THEN ?
                               ELSE fi.started_at
                             END
                           )
                           ELSE 0
                         END
                       ), 0) AS total_seconds,
                       MAX(fi.started_at) AS last_focused_at
                  FROM windows w
                  LEFT JOIN focus_intervals fi ON fi.window_id = w.id
                 GROUP BY w.id
                HAVING total_seconds > 0
                 ORDER BY total_seconds DESC, w.last_seen DESC
                """,
                (since, since, since),
            ).fetchall()

        totals: list[WindowTotal] = []
        for row in rows:
            totals.append(
                WindowTotal(
                    key=row["key"],
                    info=WindowInfo(
                        title=row["title"],
                        window_class=row["window_class"],
                        instance=row["instance"],
                    ),
                    total_seconds=float(row["total_seconds"]),
                    last_focused_at=row["last_focused_at"],
                )
            )
        return tuple(totals)

    def window_activity_bounds(self) -> tuple[WindowActivityBounds, ...]:
        rows = self.connection.execute(
            """
            SELECT w.title,
                   w.window_class,
                   w.instance,
                   MIN(fi.started_at) AS first_started_at,
                   MAX(fi.started_at) AS last_started_at
              FROM windows w
              JOIN focus_intervals fi ON fi.window_id = w.id
             WHERE fi.abandoned = 0
             GROUP BY w.id
            """
        ).fetchall()
        return tuple(
            WindowActivityBounds(
                info=WindowInfo(
                    title=row["title"],
                    window_class=row["window_class"],
                    instance=row["instance"],
                ),
                first_started_at=float(row["first_started_at"]),
                last_started_at=float(row["last_started_at"]),
            )
            for row in rows
        )

    def focus_intervals(self, open_ended_at: float | None = None) -> tuple[FocusIntervalRecord, ...]:
        rows = self.connection.execute(
            """
            SELECT w.title,
                   w.window_class,
                   w.instance,
                   fi.started_at,
                   COALESCE(fi.ended_at, ?) AS ended_at
              FROM focus_intervals fi
              JOIN windows w ON w.id = fi.window_id
             WHERE fi.abandoned = 0
               AND (fi.ended_at IS NOT NULL OR ? IS NOT NULL)
             ORDER BY fi.started_at DESC
            """,
            (open_ended_at, open_ended_at),
        ).fetchall()
        return tuple(
            FocusIntervalRecord(
                info=WindowInfo(
                    title=row["title"],
                    window_class=row["window_class"],
                    instance=row["instance"],
                ),
                started_at=float(row["started_at"]),
                ended_at=float(row["ended_at"]),
            )
            for row in rows
        )

    def add_allowance_event(
        self,
        account_name: str,
        event_type: str,
        amount_seconds: float,
        effective_date: str,
        created_at: float,
        note: str | None,
        source_key: str,
    ) -> bool:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO allowance_events(
              account_name,
              event_type,
              amount_seconds,
              effective_date,
              created_at,
              note,
              source_key
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_name,
                event_type,
                amount_seconds,
                effective_date,
                created_at,
                note,
                source_key,
            ),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def allowance_totals(self, account_name: str) -> dict[str, float]:
        row = self.connection.execute(
            """
            SELECT COALESCE(SUM(amount_seconds), 0) AS total,
                   COALESCE(SUM(
                     CASE WHEN event_type = 'scheduled' THEN amount_seconds ELSE 0 END
                   ), 0) AS scheduled,
                   COALESCE(SUM(
                     CASE WHEN event_type = 'adjustment' THEN amount_seconds ELSE 0 END
                   ), 0) AS adjustment
              FROM allowance_events
             WHERE account_name = ?
            """,
            (account_name,),
        ).fetchone()
        if row is None:
            return {"total": 0.0, "scheduled": 0.0, "adjustment": 0.0}
        return {
            "total": float(row["total"]),
            "scheduled": float(row["scheduled"]),
            "adjustment": float(row["adjustment"]),
        }

    def earliest_allowance_event_date(self, account_name: str) -> str | None:
        row = self.connection.execute(
            """
            SELECT MIN(effective_date) AS effective_date
              FROM allowance_events
             WHERE account_name = ?
            """,
            (account_name,),
        ).fetchone()
        if row is None:
            return None
        return row["effective_date"]

    def allowance_events(self, account_name: str) -> tuple[AllowanceEvent, ...]:
        rows = self.connection.execute(
            """
            SELECT account_name,
                   event_type,
                   amount_seconds,
                   effective_date,
                   created_at,
                   note
              FROM allowance_events
             WHERE account_name = ?
             ORDER BY effective_date DESC, created_at DESC, id DESC
            """,
            (account_name,),
        ).fetchall()
        return tuple(
            AllowanceEvent(
                account_name=row["account_name"],
                event_type=row["event_type"],
                amount_seconds=float(row["amount_seconds"]),
                effective_date=date.fromisoformat(row["effective_date"]),
                created_at=float(row["created_at"]),
                note=row["note"],
            )
            for row in rows
        )
