"""Per-group persistent relay settings, stored in SQLite."""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Route:
    source_id: int
    target_id: int
    tags: tuple[str, ...]
    enabled: bool


@dataclass(frozen=True)
class RequestRoute:
    source_id: int
    target_id: int
    enabled: bool
    daily_limit: int
    start_minute: int | None
    end_minute: int | None


class RouteStore:
    def __init__(self, path: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(p))
        self.db.execute("PRAGMA busy_timeout = 5000")
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS routes (
                source_id INTEGER PRIMARY KEY,
                target_id INTEGER NOT NULL,
                tags TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_by INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS request_routes (
                source_id INTEGER PRIMARY KEY,
                target_id INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_by INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK (source_id <> target_id)
            )"""
        )
        # Preserve existing request routes and their destinations during upgrade.
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(request_routes)")}
        for name, definition in (
            ("daily_limit", "INTEGER NOT NULL DEFAULT 1"),
            ("start_minute", "INTEGER"),
            ("end_minute", "INTEGER"),
        ):
            if name not in columns:
                self.db.execute(f"ALTER TABLE request_routes ADD COLUMN {name} {definition}")

        self.db.execute(
            """CREATE TABLE IF NOT EXISTS request_usage (
                source_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                day_key TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('reserved', 'delivered')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_id, message_id)
            )"""
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_request_usage_quota "
            "ON request_usage(source_id, user_id, day_key, status)"
        )
        # Only one polling instance is supported. Release claims orphaned by a
        # previous crash; see README's at-least-once caveat.
        self.db.execute("DELETE FROM request_usage WHERE status='reserved'")
        self.db.commit()

    def get_request(self, source_id: int) -> RequestRoute | None:
        row = self.db.execute(
            """SELECT source_id, target_id, enabled, daily_limit,
                      start_minute, end_minute FROM request_routes WHERE source_id=?""",
            (source_id,),
        ).fetchone()
        return RequestRoute(row[0], row[1], bool(row[2]), row[3], row[4], row[5]) if row else None

    def save_request(self, source_id: int, target_id: int, user_id: int) -> None:
        if source_id == target_id:
            raise ValueError("Talep hedefi kaynak gruptan farklı olmalıdır.")
        with self.db:
            self.db.execute(
                """INSERT INTO request_routes(source_id, target_id, enabled, updated_by)
                   VALUES (?, ?, 1, ?)
                   ON CONFLICT(source_id) DO UPDATE SET
                   target_id=excluded.target_id,
                   enabled=1,
                   updated_by=excluded.updated_by,
                   updated_at=CURRENT_TIMESTAMP""",
                (source_id, target_id, user_id),
            )

    def set_request_enabled(self, source_id: int, enabled: bool, user_id: int) -> bool:
        with self.db:
            cur = self.db.execute(
                """UPDATE request_routes SET enabled=?, updated_by=?,
                   updated_at=CURRENT_TIMESTAMP WHERE source_id=?""",
                (int(enabled), user_id, source_id),
            )
        return cur.rowcount > 0

    def set_request_limit(self, source_id: int, limit: int, user_id: int) -> bool:
        if not 1 <= limit <= 20:
            raise ValueError("Günlük limit 1 ile 20 arasında olmalıdır.")
        with self.db:
            cur = self.db.execute(
                """UPDATE request_routes SET daily_limit=?, updated_by=?,
                   updated_at=CURRENT_TIMESTAMP WHERE source_id=?""",
                (limit, user_id, source_id),
            )
        return cur.rowcount > 0

    def set_request_hours(self, source_id: int, start: int | None, end: int | None, user_id: int) -> bool:
        if (start is None) != (end is None):
            raise ValueError("Saat aralığı eksik.")
        if start is not None and (not 0 <= start < 1440 or not 0 <= end < 1440 or start == end):
            raise ValueError("Geçerli ve farklı başlangıç/bitiş saatleri girin.")
        with self.db:
            cur = self.db.execute(
                """UPDATE request_routes SET start_minute=?, end_minute=?,
                   updated_by=?, updated_at=CURRENT_TIMESTAMP WHERE source_id=?""",
                (start, end, user_id, source_id),
            )
        return cur.rowcount > 0

    def claim_request(self, source_id: int, user_id: int, day_key: str,
                      message_id: int) -> str:
        """Atomically reserve daily capacity. Returns accepted/limit/duplicate/disabled."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT enabled, daily_limit FROM request_routes WHERE source_id=?",
                (source_id,),
            ).fetchone()
            if row is None or not row[0]:
                result = "disabled"
            elif self.db.execute(
                "SELECT 1 FROM request_usage WHERE source_id=? AND message_id=?",
                (source_id, message_id),
            ).fetchone():
                result = "duplicate"
            else:
                count = self.db.execute(
                    """SELECT COUNT(*) FROM request_usage
                       WHERE source_id=? AND user_id=? AND day_key=?""",
                    (source_id, user_id, day_key),
                ).fetchone()[0]
                if count >= row[1]:
                    result = "limit"
                else:
                    self.db.execute(
                        """INSERT INTO request_usage(source_id, user_id, day_key, message_id, status)
                           VALUES (?, ?, ?, ?, 'reserved')""",
                        (source_id, user_id, day_key, message_id),
                    )
                    result = "accepted"
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def finish_request(self, source_id: int, message_id: int, delivered: bool) -> None:
        with self.db:
            if delivered:
                self.db.execute(
                    """UPDATE request_usage SET status='delivered'
                       WHERE source_id=? AND message_id=? AND status='reserved'""",
                    (source_id, message_id),
                )
            else:
                self.db.execute(
                    """DELETE FROM request_usage
                       WHERE source_id=? AND message_id=? AND status='reserved'""",
                    (source_id, message_id),
                )

    def disable_request(self, source_id: int, user_id: int) -> bool:
        with self.db:
            cur = self.db.execute(
                """UPDATE request_routes SET enabled=0, updated_by=?,
                   updated_at=CURRENT_TIMESTAMP WHERE source_id=?""",
                (user_id, source_id),
            )
        return cur.rowcount > 0

    def get(self, source_id: int) -> Route | None:
        row = self.db.execute(
            "SELECT source_id, target_id, tags, enabled FROM routes WHERE source_id=?",
            (source_id,),
        ).fetchone()
        if row is None:
            return None
        return Route(row[0], row[1], tuple(json.loads(row[2])), bool(row[3]))

    def save(self, source_id: int, target_id: int, tags: list[str], user_id: int) -> None:
        with self.db:
            self.db.execute(
                """INSERT INTO routes(source_id, target_id, tags, enabled, updated_by)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(source_id) DO UPDATE SET
                   target_id=excluded.target_id,
                   tags=excluded.tags,
                   enabled=1,
                   updated_by=excluded.updated_by,
                   updated_at=CURRENT_TIMESTAMP""",
                (source_id, target_id, json.dumps(tags, ensure_ascii=False), user_id),
            )

    def set_tags(self, source_id: int, tags: list[str], user_id: int) -> bool:
        with self.db:
            cur = self.db.execute(
                """UPDATE routes SET tags=?, updated_by=?, updated_at=CURRENT_TIMESTAMP
                   WHERE source_id=?""",
                (json.dumps(tags, ensure_ascii=False), user_id, source_id),
            )
        return cur.rowcount > 0

    def disable(self, source_id: int, user_id: int) -> bool:
        with self.db:
            cur = self.db.execute(
                """UPDATE routes SET enabled=0, updated_by=?, updated_at=CURRENT_TIMESTAMP
                   WHERE source_id=?""",
                (user_id, source_id),
            )
        return cur.rowcount > 0

    def close(self) -> None:
        self.db.close()
