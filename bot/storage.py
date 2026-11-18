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
        self.db.commit()

    def get_request(self, source_id: int) -> RequestRoute | None:
        row = self.db.execute(
            "SELECT source_id, target_id, enabled FROM request_routes WHERE source_id=?",
            (source_id,),
        ).fetchone()
        return RequestRoute(row[0], row[1], bool(row[2])) if row else None

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
