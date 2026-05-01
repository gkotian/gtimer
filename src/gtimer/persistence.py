from __future__ import annotations

import sqlite3
from pathlib import Path

from .identity import window_key
from .models import WindowInfo, WindowTotal


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

            CREATE INDEX IF NOT EXISTS idx_focus_intervals_window
              ON focus_intervals(window_id);
            CREATE INDEX IF NOT EXISTS idx_focus_intervals_started
              ON focus_intervals(started_at);
            CREATE INDEX IF NOT EXISTS idx_focus_intervals_open
              ON focus_intervals(ended_at)
              WHERE ended_at IS NULL;
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
