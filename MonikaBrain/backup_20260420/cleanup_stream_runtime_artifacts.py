from __future__ import annotations

import argparse
import shutil
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "knowledge.db"

BAD_MARKERS = [
    "я чуть не повторила",
    "я чуть не ушла",
    "повторила тебя попугаем",
    "задай вопрос короче",
    "продолжай, я слушаю",
    "давай заново: задай вопрос",
    "он не спрашивал почему",
]


def bad(text: str) -> bool:
    t = (text or "").lower().replace("ё", "е")
    return any(m in t for m in BAD_MARKERS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not DB.exists():
        raise SystemExit(f"knowledge.db not found: {DB}")

    print("Mode:", "APPLY" if args.apply else "DRY-RUN")
    if args.apply:
        backup = DB.with_name(f"knowledge.db.bak_stream_runtime_cleanup_{time.strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(DB, backup)
        print(f"[backup] {DB} -> {backup}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    total = 0
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_history'")
    if cur.fetchone():
        cur.execute("SELECT id, role, message, timestamp FROM chat_history ORDER BY id DESC")
        rows = cur.fetchall()
        ids = []
        for row in rows:
            if row["role"] == "assistant" and bad(row["message"]):
                ids.append(row["id"])
                total += 1
                print(f"[chat_history bad] #{row['id']} {row['timestamp']} {row['message']}")
        if args.apply and ids:
            cur.executemany("DELETE FROM chat_history WHERE id=?", [(i,) for i in ids])

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dialogue_sessions'")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(dialogue_sessions)")
        cols = {r["name"] for r in cur.fetchall()}
        check_cols = [c for c in ["summary", "key_topics", "last_message", "monika_last_words"] if c in cols]
        if check_cols:
            cur.execute(f"SELECT rowid AS _rowid, {', '.join(check_cols)} FROM dialogue_sessions")
            ids = []
            for row in cur.fetchall():
                joined = "\n".join(str(row[c] or "") for c in check_cols)
                if bad(joined):
                    ids.append(row["_rowid"])
                    total += 1
                    print(f"[dialogue_sessions bad] rowid={row['_rowid']}")
            if args.apply and ids:
                cur.executemany("DELETE FROM dialogue_sessions WHERE rowid=?", [(i,) for i in ids])

    if args.apply:
        conn.commit()
    conn.close()

    print(f"bad rows found: {total}")
    if not args.apply:
        print("Run with --apply to delete these rows.")


if __name__ == "__main__":
    main()
