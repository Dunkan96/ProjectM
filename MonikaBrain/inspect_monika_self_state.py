from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from config import BRAIN_DIR
from monika_self_state import MonikaSelfState


def main() -> None:
    query = " ".join(sys.argv[1:]).strip()
    db_path = Path(BRAIN_DIR) / "knowledge.db"
    if not db_path.exists():
        raise SystemExit(f"knowledge.db not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    state = MonikaSelfState(conn)

    if query:
        state.observe_user_message(query, relationship_role="creator")
        print("Prompt block:")
        print(state.build_prompt_block(query, relationship_role="creator"))
        print()

    print("Self snapshot:")
    for k, v in state.snapshot().items():
        print(f"  {k}: {v}")

    print("\nRelevant opinions:")
    cur = conn.cursor()
    if query:
        topic = state.extract_opinion_topic(query) or query
        cur.execute(
            """
            SELECT subject, category, stance, polarity, confidence, source, basis, times_seen, last_seen
            FROM monika_opinions
            WHERE lower(subject) LIKE lower(?)
               OR lower(basis) LIKE lower(?)
            ORDER BY confidence DESC, last_seen DESC
            LIMIT 10
            """,
            (f"%{topic}%", f"%{topic}%"),
        )
    else:
        cur.execute(
            """
            SELECT subject, category, stance, polarity, confidence, source, basis, times_seen, last_seen
            FROM monika_opinions
            ORDER BY last_seen DESC
            LIMIT 15
            """
        )

    rows = cur.fetchall()
    if not rows:
        print("  no rows")
    for row in rows:
        print(f"  - {row['subject']} | {row['stance']} | polarity={row['polarity']} | conf={row['confidence']} | seen={row['times_seen']}")
        print(f"    basis: {row['basis']}")
        print(f"    source: {row['source']} | last_seen={row['last_seen']}")


if __name__ == "__main__":
    main()
