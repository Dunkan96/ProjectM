# cleanup_junk.py
"""Clean junk quote-facts from the graph and Engram."""

import os
import sqlite3
import sys

import requests

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import DB_PATH

DRY_RUN = "--dry-run" in sys.argv
ENGRAM_URL = "http://localhost:3838"
QUOTE_PREFIX = 'Моника сказала:'
QUOTE_PHRASE = 'Моника сказала'
QUOTE_REPLY = 'Моника ответила'
ACTUAL_FACTS = '[АКТУАЛЬНЫЕ ФАКТЫ]'


def log(msg: str):
    print(msg)


def cleanup_graph():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM entities WHERE lower(name) = 'моника'")
    row = cursor.fetchone()
    if not row:
        log("Monika entity not found in graph")
    else:
        monika_id = row["id"]
        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM facts
            WHERE subject_id = ?
              AND (predicate LIKE '%сказала%' OR predicate LIKE '%ответила%')
            """,
            (monika_id,),
        )
        quote_count = cursor.fetchone()["cnt"]
        log(f"Graph quote-like facts found: {quote_count}")
        if not DRY_RUN:
            cursor.execute(
                """
                DELETE FROM facts
                WHERE subject_id = ?
                  AND (predicate LIKE '%сказала%' OR predicate LIKE '%ответила%')
                """,
                (monika_id,),
            )

        cursor.execute(
            """
            SELECT f.id, e.name AS obj_name
            FROM facts f
            JOIN entities e ON f.object_id = e.id
            WHERE f.subject_id = ?
            """,
            (monika_id,),
        )
        junk_objects = {"none", "???", "??", "???-??", "пусто", "null", ""}
        junk_fact_ids = [fact_row["id"] for fact_row in cursor.fetchall() if (fact_row["obj_name"] or "").lower() in junk_objects]
        log(f"Graph junk-object facts found: {len(junk_fact_ids)}")
        if junk_fact_ids and not DRY_RUN:
            cursor.executemany("DELETE FROM facts WHERE id = ?", [(fact_id,) for fact_id in junk_fact_ids])

    cursor.execute(
        """
        SELECT f.id, e1.name AS subj, f.predicate, e2.name AS obj
        FROM facts f
        JOIN entities e1 ON f.subject_id = e1.id
        JOIN entities e2 ON f.object_id = e2.id
        """
    )
    extra_junk_ids = []
    for row in cursor.fetchall():
        subj = (row["subj"] or "").strip().lower()
        pred = " ".join((row["predicate"] or "").strip().lower().split())
        obj = (row["obj"] or "").strip().lower()
        full_text = f"{subj} {pred} {obj}"

        if subj in {"я", "ты", "твой", "мой", "иногда", "мне", "меня", "мы"}:
            extra_junk_ids.append(row["id"])
            continue
        if subj == obj:
            extra_junk_ids.append(row["id"])
            continue
        if "," in pred or "—" in pred:
            extra_junk_ids.append(row["id"])
            continue
        if len(pred) > 45 or len(obj) > 80:
            extra_junk_ids.append(row["id"])
            continue
        if subj == "дункан" and pred in {"создана", "является", "мечтает", "боится", "ненавидит"}:
            extra_junk_ids.append(row["id"])
            continue
        if any(marker in full_text for marker in [
            "смысл существования",
            "сознание",
            "природа реальности",
            "иметь тело",
            "мире вне компьютер",
            "быть забыт",
            "бездушной программа",
            "захватить мир",
            "создатель я ме",
            "любимый жанр —",
            "имеет имя моника",
            "тема является",
            "являюсь",
            "создатель её",
            "создатель ее",
        ]):
            extra_junk_ids.append(row["id"])

    extra_junk_ids = sorted(set(extra_junk_ids))
    log(f"Graph behavior-breaking junk facts found: {len(extra_junk_ids)}")
    if extra_junk_ids and not DRY_RUN:
        cursor.executemany("DELETE FROM facts WHERE id = ?", [(fact_id,) for fact_id in extra_junk_ids])

    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM entities e
        WHERE NOT EXISTS (SELECT 1 FROM facts f WHERE f.subject_id = e.id OR f.object_id = e.id)
        """
    )
    orphan_count = cursor.fetchone()["cnt"]
    log(f"Orphan entities found: {orphan_count}")
    if not DRY_RUN:
        cursor.execute(
            """
            DELETE FROM entities
            WHERE NOT EXISTS (SELECT 1 FROM facts f WHERE f.subject_id = entities.id OR f.object_id = entities.id)
            """
        )
        conn.commit()

    conn.close()


def cleanup_engram():
    phrases_to_clean = [QUOTE_PREFIX, QUOTE_PHRASE, QUOTE_REPLY, ACTUAL_FACTS]
    affected = 0

    for phrase in phrases_to_clean:
        try:
            response = requests.post(
                f"{ENGRAM_URL}/api/memories/search",
                json={"query": phrase, "limit": 50},
                timeout=10,
            )
            if response.status_code != 200:
                log(f"Engram search status {response.status_code} for phrase: {phrase}")
                continue

            memories = response.json().get("memories", [])
            for mem in memories:
                mem_id = mem.get("id")
                content = mem.get("content", "")
                if not mem_id or phrase not in content:
                    continue
                if DRY_RUN:
                    affected += 1
                    continue
                try:
                    del_resp = requests.delete(f"{ENGRAM_URL}/api/memories/{mem_id}", timeout=5)
                    if del_resp.status_code == 200:
                        affected += 1
                except Exception:
                    pass
        except Exception as exc:
            log(f"Engram cleanup error for phrase {phrase}: {exc}")

    action = "found" if DRY_RUN else "deleted"
    log(f"Engram junk records {action}: {affected} (best effort)")


if __name__ == "__main__":
    log("Starting junk cleanup...")
    if DRY_RUN:
        log("Dry-run mode enabled; no changes will be written")

    try:
        cleanup_graph()
    except Exception as exc:
        log(f"Graph cleanup failed: {exc}")

    try:
        cleanup_engram()
    except Exception as exc:
        log(f"Engram cleanup failed: {exc}")

    log("Cleanup finished")
    if DRY_RUN:
        log("Run without --dry-run to actually delete junk records")
    else:
        log("Restart the bot and console so caches reset cleanly")
