# -*- coding: utf-8 -*-
from __future__ import annotations
import sqlite3
from pathlib import Path


def get_db_path() -> Path:
    try:
        import config  # type: ignore
        for name in ("KNOWLEDGE_DB_PATH", "KNOWLEDGE_DB", "DB_PATH", "DATABASE_PATH"):
            value = getattr(config, name, None)
            if value: return Path(value)
    except Exception:
        pass
    return Path("knowledge.db")


def scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else 0


def main():
    from autonomous_memory import AutonomousMemoryGovernor
    db = get_db_path()
    conn = sqlite3.connect(str(db)); conn.row_factory = sqlite3.Row
    AutonomousMemoryGovernor(conn).init_schema()
    cur = conn.cursor()
    summary = {
        "db": str(db),
        "autonomous_memory_items": scalar(cur, "SELECT COUNT(*) FROM autonomous_memory_items"),
        "social_nicknames": scalar(cur, "SELECT COUNT(*) FROM social_nicknames"),
        "memory_corrections": scalar(cur, "SELECT COUNT(*) FROM memory_corrections"),
        "monika_experience_journal": scalar(cur, "SELECT COUNT(*) FROM monika_experience_journal"),
        "memory_action_log": scalar(cur, "SELECT COUNT(*) FROM memory_action_log"),
        "nickname_statuses": {},
    }
    cur.execute("SELECT status, COUNT(*) AS c FROM social_nicknames GROUP BY status ORDER BY status")
    summary["nickname_statuses"] = {r["status"]: r["c"] for r in cur.fetchall()}
    print("Autonomous memory summary:"); print(summary)
    print("\nRecent social nicknames:")
    cur.execute("SELECT person_id,nickname,status,positive_reactions,negative_reactions,created_at FROM social_nicknames ORDER BY id DESC LIMIT 20")
    rows = cur.fetchall()
    print("  <empty>" if not rows else "", end="" if not rows else "\n")
    for r in rows: print(f"- [{r['status']}] {r['person_id']}: {r['nickname']} (+{r['positive_reactions']}/-{r['negative_reactions']}) {r['created_at']}")
    print("\nRecent autonomous items:")
    cur.execute("SELECT person_id,kind,subject,stance,status,confidence,source_text,created_at FROM autonomous_memory_items ORDER BY id DESC LIMIT 20")
    rows = cur.fetchall(); print("  <empty>" if not rows else "", end="" if not rows else "\n")
    for r in rows:
        print(f"- [{r['status']}] {r['person_id']} {r['kind']} {r['subject']} stance={r['stance']} conf={r['confidence']}")
        if r['source_text']: print(f"  source: {r['source_text'][:180]}")
    print("\nRecent corrections:")
    cur.execute("SELECT person_id,correction_type,status,text,created_at FROM memory_corrections ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall(); print("  <empty>" if not rows else "", end="" if not rows else "\n")
    for r in rows: print(f"- [{r['status']}] {r['person_id']} {r['correction_type']}: {r['text'][:220]}")
    print("\nRecent experience journal:")
    cur.execute("SELECT person_id,event_type,status,stage,cringe_score,summary,created_at FROM monika_experience_journal ORDER BY id DESC LIMIT 15")
    rows = cur.fetchall(); print("  <empty>" if not rows else "", end="" if not rows else "\n")
    for r in rows: print(f"- [{r['status']}/{r['event_type']}] {r['person_id']} stage={r['stage']} cringe={r['cringe_score']} :: {r['summary'][:240]} {r['created_at']}")
    print("\nRecent action log:")
    cur.execute("SELECT action_type,person_id,target,status,detail,created_at FROM memory_action_log ORDER BY id DESC LIMIT 15")
    rows = cur.fetchall(); print("  <empty>" if not rows else "", end="" if not rows else "\n")
    for r in rows: print(f"- [{r['status']}] {r['action_type']} {r['person_id']} target={r['target']} :: {r['detail'][:160]}")
    conn.close()

if __name__ == "__main__": main()
