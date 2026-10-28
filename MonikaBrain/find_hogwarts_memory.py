import os
import sqlite3
from pathlib import Path

ROOT = Path(r"F:\МоnikaVtuber\MonikaBrain")

TERMS = [
    "хогв",
    "хогвард",
    "хогварт",
    "hogw",
    "сон",
]

def hit(text: str) -> bool:
    text = (text or "").lower().replace("ё", "е")
    return any(term in text for term in TERMS)

def print_row(title, text):
    print("\n" + "=" * 80)
    print(title)
    print("-" * 80)
    print(text)

def search_graph():
    db = ROOT / "monika_memory.db"
    if not db.exists():
        print(f"[skip] {db} not found")
        return

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            f.id,
            s.name AS subject,
            f.predicate,
            o.name AS object,
            f.importance,
            f.created_at,
            f.last_accessed,
            f.access_count
        FROM facts f
        JOIN entities s ON s.id = f.subject_id
        JOIN entities o ON o.id = f.object_id
        ORDER BY f.id DESC
    """)

    count = 0
    for r in cur.fetchall():
        text = f"{r['subject']} {r['predicate']} {r['object']}"
        if hit(text):
            count += 1
            print_row(
                f"[monika_memory.db / facts] id={r['id']} importance={r['importance']}",
                f"{text}\ncreated_at={r['created_at']} last_accessed={r['last_accessed']} access_count={r['access_count']}"
            )

    conn.close()
    print(f"\n[graph] found: {count}")

def search_knowledge():
    db = ROOT / "knowledge.db"
    if not db.exists():
        print(f"[skip] {db} not found")
        return

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    tables = {
        "chat_history": ["role", "message", "timestamp"],
        "stream_events": ["event_type", "description", "participants", "timestamp"],
        "dialogue_sessions": ["summary", "key_topics", "last_message", "monika_last_words", "session_start", "session_end"],
        "emotional_events": ["event_type", "emotion", "context", "user_message", "monika_reaction", "timestamp"],
        "monika_desires": ["target", "category", "desire_type", "note", "last_seen"],
        "monika_opinions": ["subject", "category", "stance", "basis", "last_seen"],
    }

    total = 0

    for table, cols in tables.items():
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cur.fetchone():
            continue

        cur.execute(f"PRAGMA table_info({table})")
        existing = {row["name"] for row in cur.fetchall()}
        use_cols = [c for c in cols if c in existing]
        if not use_cols:
            continue

        cur.execute(f"SELECT rowid AS _rowid, {', '.join(use_cols)} FROM {table} ORDER BY rowid DESC")
        count = 0

        for r in cur.fetchall():
            joined = "\n".join(f"{c}: {r[c]}" for c in use_cols)
            if hit(joined):
                count += 1
                total += 1
                print_row(f"[knowledge.db / {table}] rowid={r['_rowid']}", joined)

        print(f"[{table}] found: {count}")

    conn.close()
    print(f"\n[knowledge] total found: {total}")

def search_chroma():
    try:
        import chromadb
    except Exception as e:
        print(f"[skip] chromadb import failed: {e}")
        return

    path = str(ROOT / "chroma_engram")
    if not Path(path).exists():
        print(f"[skip] {path} not found")
        return

    client = chromadb.PersistentClient(path=path)

    try:
        col = client.get_collection("dialogue_memory")
    except Exception as e:
        print(f"[skip] dialogue_memory not found: {e}")
        return

    total = col.count()
    found = 0
    batch = 200

    for offset in range(0, total, batch):
        data = col.get(
            limit=batch,
            offset=offset,
            include=["documents", "metadatas"]
        )

        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []

        for doc_id, doc, meta in zip(ids, docs, metas):
            if hit(doc):
                found += 1
                print_row(
                    f"[chroma / dialogue_memory] id={doc_id}",
                    f"{doc}\nmetadata={meta}"
                )

    print(f"\n[chroma] total={total}, found={found}")

if __name__ == "__main__":
    print("Searching Hogwarts memory...\n")
    search_graph()
    search_knowledge()
    search_chroma()