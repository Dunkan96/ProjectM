# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sqlite3

from config import BRAIN_DIR
from reflection_curator import ReflectionCurator


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write updated quality/stage labels and rebuild good/bad tables")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    db = Path(BRAIN_DIR) / "knowledge.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    curator = ReflectionCurator(conn)
    cur = conn.cursor()
    cur.execute("SELECT id, user_input, monika_reply, stage_mode, quality, score, reasons FROM reflection_events ORDER BY id ASC")
    rows = cur.fetchall()

    changes = []
    for row in rows:
        new = curator.classify_reply(row["user_input"], row["monika_reply"], stage_mode=row["stage_mode"] or "")
        old_quality = row["quality"]
        old_stage = row["stage_mode"] or ""
        new_quality = new["quality"]
        new_stage = new.get("stage_mode") or old_stage
        if old_quality != new_quality or old_stage != new_stage:
            changes.append((row, new))

    print(f"Reflection events: {len(rows)}")
    print(f"Changes: {len(changes)}")
    for row, new in changes[: args.limit]:
        print(f"#{row['id']} {row['quality']}->{new['quality']} stage={row['stage_mode'] or ''}->{new.get('stage_mode') or ''} score={new['score']} reasons={new['reasons']}")
        print(" U:", str(row["user_input"])[:140].replace("\n", " "))
        print(" M:", str(row["monika_reply"])[:180].replace("\n", " "))

    if args.apply:
        stats = curator.rebuild_line_tables()
        print("Applied rebuild:", stats)
    else:
        print("Mode: DRY-RUN. Run with --apply to rewrite reflection labels and rebuild good/bad tables.")

    conn.close()


if __name__ == "__main__":
    main()
