from __future__ import annotations

import sqlite3

from moderation_governor import ModerationGovernor, default_db_path


def main() -> None:
    ModerationGovernor()
    conn = sqlite3.connect(str(default_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM moderation_actions").fetchone()["n"]
        by_status = {row["status"]: row["n"] for row in conn.execute("SELECT status, COUNT(*) AS n FROM moderation_actions GROUP BY status")}
        by_action = {row["action"]: row["n"] for row in conn.execute("SELECT action, COUNT(*) AS n FROM moderation_actions GROUP BY action")}
        print("Moderation summary:")
        print({"moderation_actions": total, "by_status": by_status, "by_action": by_action})

        print()
        print("Recent moderation actions:")
        rows = conn.execute("SELECT * FROM moderation_actions ORDER BY created_ts DESC LIMIT 10").fetchall()
        if not rows:
            print("  <empty>")
        else:
            for row in rows:
                print(f"- [{row['status']}] {row['action']} user={row['user_name']} confidence={row['confidence']} reason={row['reason']}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
