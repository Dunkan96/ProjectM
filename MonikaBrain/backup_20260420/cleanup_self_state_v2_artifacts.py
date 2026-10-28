
from __future__ import annotations

import argparse
import shutil
import sqlite3
import time
from pathlib import Path
from config import BRAIN_DIR

ROOT = Path(BRAIN_DIR)
DB = ROOT / "knowledge.db"
STAMP = time.strftime("%Y%m%d_%H%M%S")

BAD_REPLY_MARKERS = [
    "Я чуть не повторила тебя попугаем",
    "Я чуть не ушла в повтор",
    "задай вопрос короче, и я отвечу прямо",
    "Стоп. Продолжай, я слушаю",
]

def row_hit(text: str) -> bool:
    lowered = (text or "").lower().replace("ё", "е")
    return any(marker.lower().replace("ё", "е") in lowered for marker in BAD_REPLY_MARKERS)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not DB.exists():
        raise SystemExit(f"[ERROR] missing {DB}")

    print("Mode:", "APPLY" if args.apply else "DRY-RUN")
    if args.apply:
        backup = DB.with_name(f"{DB.name}.bak_self_state_v2_cleanup_{STAMP}")
        shutil.copy2(DB, backup)
        print(f"[backup] {DB} -> {backup}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    bad_chat = []
    cur.execute("SELECT id, timestamp, role, message FROM chat_history ORDER BY id DESC")
    for row in cur.fetchall():
        if row["role"] == "assistant" and row_hit(row["message"]):
            bad_chat.append(row)
            print(f"[chat_history bad] #{row['id']} {row['timestamp']} {row['message']}")
    if args.apply and bad_chat:
        cur.executemany("DELETE FROM chat_history WHERE id=?", [(r["id"],) for r in bad_chat])
    print(f"[chat_history] bad rows: {len(bad_chat)}" + (" deleted" if args.apply else ""))

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dialogue_sessions'")
    if cur.fetchone():
        bad_sessions = []
        cur.execute("SELECT rowid AS _rowid, monika_last_words, last_message FROM dialogue_sessions")
        for row in cur.fetchall():
            combined = f"{row['monika_last_words'] or ''}\n{row['last_message'] or ''}"
            if row_hit(combined):
                bad_sessions.append(row)
                print(f"[dialogue_sessions bad] rowid={row['_rowid']}")
                print(f"  monika_last_words: {row['monika_last_words']}")
        if args.apply and bad_sessions:
            cur.executemany("DELETE FROM dialogue_sessions WHERE rowid=?", [(r["_rowid"],) for r in bad_sessions])
        print(f"[dialogue_sessions] bad rows: {len(bad_sessions)}" + (" deleted" if args.apply else ""))

    # Remove the arbitrary broccoli opinion seeded by v1. This does not ban
    # broccoli; v2 will create a fresh deterministic opinion only when asked.
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='monika_opinions'")
    if cur.fetchone():
        cur.execute("""
            SELECT id, subject, stance, source, basis
            FROM monika_opinions
            WHERE lower(subject)=lower(?) AND COALESCE(source,'')='self_state_seed'
        """, ("брокколи",))
        rows = cur.fetchall()
        for row in rows:
            print(f"[opinion seed cleanup] #{row['id']} {row['subject']} {row['stance']} source={row['source']}")
        if args.apply and rows:
            cur.executemany("DELETE FROM monika_opinions WHERE id=?", [(r["id"],) for r in rows])
        print(f"[monika_opinions] broccoli self_state_seed rows: {len(rows)}" + (" deleted" if args.apply else ""))

    if args.apply:
        conn.commit()
        print("Done.")
    else:
        print("Run with --apply to delete these rows.")
    conn.close()

if __name__ == "__main__":
    main()
