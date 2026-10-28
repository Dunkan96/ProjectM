# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

from config import BRAIN_DIR
from reflection_curator import ReflectionCurator


def main() -> None:
    db = Path(BRAIN_DIR) / "knowledge.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    curator = ReflectionCurator(conn)
    print("Reflection summary:")
    print(curator.summary())

    cur = conn.cursor()
    print("\nRecent bad lines:")
    for row in cur.execute("SELECT id, stage_mode, score, reason, text FROM monika_bad_lines ORDER BY id DESC LIMIT 8"):
        print(f"#{row['id']} [{row['stage_mode']}] score={row['score']} reason={row['reason']}")
        print(" ", str(row['text'])[:180].replace("\n", " "))

    print("\nRecent good lines:")
    for row in cur.execute("SELECT id, stage_mode, score, reason, text FROM monika_good_lines ORDER BY id DESC LIMIT 8"):
        print(f"#{row['id']} [{row['stage_mode']}] score={row['score']} reason={row['reason']}")
        print(" ", str(row['text'])[:180].replace("\n", " "))

    conn.close()


if __name__ == "__main__":
    main()
