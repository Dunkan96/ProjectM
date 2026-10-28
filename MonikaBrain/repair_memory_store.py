# repair_memory_store.py
from __future__ import annotations

import argparse
from config import STREAMER_ID
from builder import Builder
from memory_core import MemoryCore


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill verified user facts from chat_history into graph memory.")
    parser.add_argument("--apply", action="store_true", help="Actually write facts. Default is dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run alias. This is the default mode.")
    parser.add_argument("--limit", type=int, default=0, help="Limit scanned user messages; 0 = all.")
    args = parser.parse_args()

    builder = Builder(user_id=STREAMER_ID)
    core = MemoryCore(builder, person_id=STREAMER_ID, display_name="Дункан")

    cur = builder.knowledge_conn.cursor()
    sql = """
        SELECT id, message, timestamp
        FROM chat_history
        WHERE user_id = ? AND role = 'user'
        ORDER BY id ASC
    """
    params = [STREAMER_ID]
    if args.limit and args.limit > 0:
        sql += " LIMIT ?"
        params.append(args.limit)

    cur.execute(sql, params)

    scanned = 0
    found = 0
    saved = 0
    for row in cur.fetchall():
        scanned += 1
        facts = core.extract_user_facts(row["message"])
        if not facts:
            continue

        found += len(facts)
        print(f"\n[chat_history id={row['id']} {row['timestamp']}] {row['message']}")
        for fact in facts:
            print(f"  -> {fact.as_text()}  confidence={fact.confidence:.2f}")
            if args.apply:
                graph_id = core.store_fact(fact, person_id=STREAMER_ID)
                if graph_id is not None:
                    saved += 1

    print("\nSummary")
    print(f"  scanned user messages: {scanned}")
    print(f"  extracted facts:       {found}")
    print(f"  saved facts:           {saved}")
    if not args.apply:
        print("  mode: DRY-RUN. Run with --apply to write facts.")

    builder.close()


if __name__ == "__main__":
    main()
