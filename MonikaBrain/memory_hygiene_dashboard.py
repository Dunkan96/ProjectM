# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from pathlib import Path


class MemoryHygieneDashboard:
    """Простой аудит мусора памяти без удаления данных."""

    BAD_PATTERNS = ["моя мама", "я ела", "я играла", "мне снились", "мамины рецепты", "киберпанк два месяца"]

    def __init__(self, db_path: str | Path = "knowledge.db"):
        self.db_path = Path(db_path)

    def scan(self) -> list[str]:
        if not self.db_path.exists():
            return [f"DB not found: {self.db_path}"]
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        findings: list[str] = []
        for table in ["facts", "verified_memory", "chat_history", "semantic_memory"]:
            if not self._table_exists(conn, table):
                continue
            cols = self._columns(conn, table)
            text_cols = [c for c in cols if c in {"subject", "predicate", "object", "source_text", "message", "content", "text"}]
            if not text_cols:
                continue
            query = f"SELECT rowid, {', '.join(text_cols)} FROM {table} LIMIT 5000"
            try:
                for row in conn.execute(query):
                    blob = " ".join(str(row[c] or "") for c in text_cols).lower().replace("ё", "е")
                    if any(p in blob for p in self.BAD_PATTERNS):
                        findings.append(f"{table}#{row['rowid']}: {blob[:180]}")
            except Exception as exc:
                findings.append(f"{table}: scan error {exc}")
        conn.close()
        return findings

    def _table_exists(self, conn, table: str) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return bool(row)

    def _columns(self, conn, table: str) -> list[str]:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


if __name__ == "__main__":
    for line in MemoryHygieneDashboard().scan():
        print(line)

