# inspect_memory_health.py
from __future__ import annotations

import argparse
from config import STREAMER_ID
from builder import Builder
from memory_core import MemoryCore


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect graph + verified memory for a query.")
    parser.add_argument("query", nargs="*", default=["хогвардс"])
    args = parser.parse_args()
    query = " ".join(args.query).strip() or "хогвардс"

    builder = Builder(user_id=STREAMER_ID)
    core = MemoryCore(builder, person_id=STREAMER_ID, display_name="Дункан")

    print(f"Query: {query}\n")

    print("Graph search:")
    try:
        for fact in builder.search_facts(query, top_k=10):
            print(f"  - {fact}")
    except Exception as exc:
        print(f"  error: {exc}")

    print("\nVerified recall:")
    recall = core.recall(query, limit=10, person_id=STREAMER_ID)
    print(f"  confidence: {recall['confidence']}")
    print(f"  anchors: {recall['anchors']}")
    for fact in recall["facts"]:
        print(f"  - {fact}")

    print("\nProvenance rows:")
    cur = builder.knowledge_conn.cursor()
    anchors = recall.get("anchors") or [query]
    clauses = []
    params = []
    for anchor in anchors:
        clauses.append("(subject LIKE ? OR predicate LIKE ? OR object LIKE ? OR source_text LIKE ?)")
        params.extend([f"%{anchor}%", f"%{anchor}%", f"%{anchor}%", f"%{anchor}%"])
    params.append(STREAMER_ID)

    cur.execute(f"""
        SELECT id, subject, predicate, object, confidence, source_text, created_at, last_seen
        FROM verified_memory
        WHERE ({" OR ".join(clauses)}) AND person_id = ?
        ORDER BY last_seen DESC
        LIMIT 20
    """, params)

    for row in cur.fetchall():
        print(f"  #{row['id']} {row['subject']} {row['predicate']} {row['object']} conf={row['confidence']}")
        print(f"     source: {row['source_text']}")

    builder.close()


if __name__ == "__main__":
    main()
