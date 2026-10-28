from __future__ import annotations

import json
import sqlite3

from attention_layer import DIGEST_FILE, AttentionLayer, default_db_path


def main() -> None:
    AttentionLayer()
    conn = sqlite3.connect(str(default_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM attention_events").fetchone()["n"]
        selected = conn.execute("SELECT COUNT(*) AS n FROM attention_selected").fetchone()["n"]
        pending = conn.execute("SELECT COUNT(*) AS n FROM attention_selected WHERE status='pending'").fetchone()["n"]
        by_bucket = {row["bucket"]: row["n"] for row in conn.execute("SELECT bucket, COUNT(*) AS n FROM attention_events GROUP BY bucket")}
        by_source = {row["source"]: row["n"] for row in conn.execute("SELECT source, COUNT(*) AS n FROM attention_events GROUP BY source")}

        print("Attention summary:")
        print({"attention_events": total, "attention_selected": selected, "pending_selected": pending, "by_bucket": by_bucket, "by_source": by_source})

        print()
        print("Pending selected events:")
        rows = conn.execute("""
            SELECT e.*
            FROM attention_selected s
            JOIN attention_events e ON e.event_id = s.event_id
            WHERE s.status='pending'
            ORDER BY e.priority DESC, e.score DESC, e.created_ts ASC
            LIMIT 10
        """).fetchall()
        if not rows:
            print("  <empty>")
        else:
            for row in rows:
                try:
                    reasons = json.loads(row["reasons_json"] or "[]")
                except Exception:
                    reasons = []
                text = row["safe_text"] or row["text"] or ""
                print(f"- [{row['action']}] score={row['score']} prio={row['priority']} {row['source']}/{row['event_type']} {row['user_name']}: {text} ({', '.join(reasons)})")

        print()
        print("Current digest:")
        if DIGEST_FILE.exists():
            digest = DIGEST_FILE.read_text(encoding="utf-8").strip()
            print(digest if digest else "  <empty>")
        else:
            print("  <empty>")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
