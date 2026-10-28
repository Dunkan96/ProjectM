# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


CURRENT_COGNITIVE_SCHEMA_VERSION = 1


@dataclass
class MigrationResult:
    old_version: int
    new_version: int
    changed: bool


class StateMigration:
    """Минимальный versioning для новых cognitive-слоёв."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def ensure(self) -> MigrationResult:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS brain_schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        old = self.version()
        if old < CURRENT_COGNITIVE_SCHEMA_VERSION:
            cur.execute(
                """
                INSERT OR REPLACE INTO brain_schema_meta (key, value, updated_at)
                VALUES ('cognitive_schema_version', ?, datetime('now'))
                """,
                (str(CURRENT_COGNITIVE_SCHEMA_VERSION),),
            )
            self.conn.commit()
            return MigrationResult(old, CURRENT_COGNITIVE_SCHEMA_VERSION, True)
        self.conn.commit()
        return MigrationResult(old, old, False)

    def version(self) -> int:
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT value FROM brain_schema_meta WHERE key = 'cognitive_schema_version'")
            row = cur.fetchone()
            if not row:
                return 0
            return int(row[0] if not hasattr(row, "keys") else row["value"])
        except Exception:
            return 0

