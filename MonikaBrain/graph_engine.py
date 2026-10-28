# graph_engine.py
import sqlite3
import json
import math
import time
import numpy as np
import pymorphy3
from datetime import datetime
from sentence_transformers import SentenceTransformer
from config import DB_PATH, HALF_LIFE_DAYS, STREAMER_ID

MODEL_PATH = r"F:\МоnikaVtuber\.cache\huggingface\hub\models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2\snapshots\e8f8c211226b894fcb81acc59f3b34ba3efd5f42"

class GraphEngine:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.encoder = SentenceTransformer(MODEL_PATH)
        self.morph = pymorphy3.MorphAnalyzer()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                type TEXT DEFAULT 'unknown',
                aliases TEXT,
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER,
                predicate TEXT,
                object_id INTEGER,
                importance REAL DEFAULT 1.0,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                embedding BLOB,
                FOREIGN KEY (subject_id) REFERENCES entities(id),
                FOREIGN KEY (object_id) REFERENCES entities(id)
            )
        ''')
        self.conn.commit()

    def _get_embedding(self, text: str) -> bytes:
        vec = self.encoder.encode(text, normalize_embeddings=True)
        return vec.astype(np.float32).tobytes()

    def _cosine_similarity(self, emb1: bytes, emb2: bytes) -> float:
        if emb1 is None or emb2 is None:
            return 0.0
        v1 = np.frombuffer(emb1, dtype=np.float32)
        v2 = np.frombuffer(emb2, dtype=np.float32)
        return float(np.dot(v1, v2))

    def normalize_name(self, name: str) -> str:
        """Приводит слово к именительному падежу единственного числа."""
        if len(name) <= 2 or name.lower() in ["я", "ты", "он", "она", "оно", "мы", "вы", "они"]:
            return name.lower()
        try:
            parsed = self.morph.parse(name)[0]
            return parsed.normal_form.lower()
        except:
            return name.lower()

    def find_similar_entity(self, name: str, threshold: float = 0.85):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, embedding FROM entities WHERE embedding IS NOT NULL")
        rows = cursor.fetchall()
        if not rows:
            return None
        new_emb = self._get_embedding(name)
        best_id = None
        best_sim = threshold
        for row in rows:
            sim = self._cosine_similarity(new_emb, row['embedding'])
            if sim > best_sim:
                best_sim = sim
                best_id = row['id']
        if best_id:
            return best_id, best_sim
        return None

    def merge_entities(self, primary_id: int, secondary_id: int):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE facts SET subject_id = ? WHERE subject_id = ?", (primary_id, secondary_id))
        cursor.execute("UPDATE facts SET object_id = ? WHERE object_id = ?", (primary_id, secondary_id))
        cursor.execute("SELECT aliases FROM entities WHERE id = ?", (secondary_id,))
        sec_aliases = json.loads(cursor.fetchone()['aliases'] or "[]")
        cursor.execute("SELECT name, aliases FROM entities WHERE id = ?", (primary_id,))
        prim_row = cursor.fetchone()
        prim_aliases = json.loads(prim_row['aliases'] or "[]")
        prim_name = prim_row['name']
        merged = list(set(prim_aliases + sec_aliases + [prim_name]))
        cursor.execute("UPDATE entities SET aliases = ? WHERE id = ?", (json.dumps(merged), primary_id))
        cursor.execute("DELETE FROM entities WHERE id = ?", (secondary_id,))
        self.conn.commit()
        print(f"[Graph] Сущности объединены: {secondary_id} -> {primary_id}")

    def resolve_entity(self, name: str, entity_type: str = "unknown") -> int:
        normalized = self.normalize_name(name)

        if len(normalized) > 50:
            normalized = f"Фраза_{abs(hash(normalized)) % 10000}"
            entity_type = "phrase"

        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM entities WHERE name = ?", (normalized,))
        row = cursor.fetchone()
        if row:
            return row['id']

        cursor.execute("SELECT id, aliases FROM entities")
        for r in cursor.fetchall():
            aliases = json.loads(r['aliases'] or "[]")
            if normalized in aliases or name.lower() in [a.lower() for a in aliases]:
                return r['id']

        is_phrase = len(normalized.split()) > 1
        similar = None if is_phrase else self.find_similar_entity(normalized, threshold=0.85)
        if similar:
            entity_id, sim = similar
            cursor.execute("SELECT aliases FROM entities WHERE id = ?", (entity_id,))
            aliases_json = cursor.fetchone()['aliases']
            aliases = json.loads(aliases_json) if aliases_json else []
            if name not in aliases:
                aliases.append(name)
                cursor.execute("UPDATE entities SET aliases = ? WHERE id = ?", (json.dumps(aliases), entity_id))
                self.conn.commit()
                print(f"[Graph] Сущность '{name}' добавлена как алиас к ID {entity_id} (сходство {sim:.2f})")
            return entity_id

        emb = self._get_embedding(normalized)
        aliases = [name] if name != normalized else []
        cursor.execute('''
            INSERT INTO entities (name, type, aliases, embedding)
            VALUES (?, ?, ?, ?)
        ''', (normalized, entity_type, json.dumps(aliases), emb))
        self.conn.commit()
        print(f"[Graph] Создана новая сущность: '{normalized}'" + (f" (алиас: {name})" if aliases else ""))
        return cursor.lastrowid

    def add_fact(self, subject: str, predicate: str, obj: str, importance: float = 1.0) -> int:
        subj_id = self.resolve_entity(subject)
        obj_id = self.resolve_entity(obj)
        fact_text = f"{subject} {predicate} {obj}"
        emb = self._get_embedding(fact_text)
        cursor = self.conn.cursor()

        # Exact duplicate: keep one fact and refresh its metadata.
        cursor.execute("""
            SELECT id, importance FROM facts
            WHERE subject_id = ? AND predicate = ? AND object_id = ?
            ORDER BY importance DESC, id DESC
            LIMIT 1
        """, (subj_id, predicate, obj_id))
        duplicate = cursor.fetchone()
        if duplicate:
            cursor.execute("""
                UPDATE facts
                SET importance = MAX(importance, ?), last_accessed = ?, embedding = COALESCE(embedding, ?)
                WHERE id = ?
            """, (importance, datetime.now(), emb, duplicate['id']))
            self.conn.commit()
            return int(duplicate['id'])

        # Conflict resolution is allowed only for functional predicates.
        # Multi-value predicates like "любит", "видел во сне", "рассказывал сон про"
        # must coexist; otherwise the graph overwrites real memories.
        predicate_key = " ".join((predicate or "").replace("ё", "е").lower().split())
        functional_predicates = {
            "зовут",
            "живет в",
            "живёт в",
            "родился",
            "родилась",
            "родился в",
            "родилась в",
            "создан",
            "создана",
            "создал",
            "создала",
        }
        should_resolve_conflict = predicate_key in functional_predicates

        if should_resolve_conflict and not (predicate_key == "сказала" and subject.lower() == "моника"):
            cursor.execute("""
                SELECT f.id, f.object_id, e.name as obj_name, f.importance, f.created_at
                FROM facts f
                JOIN entities e ON f.object_id = e.id
                WHERE f.subject_id = ? AND f.predicate = ? AND f.object_id != ?
                ORDER BY f.importance DESC, f.id DESC
                LIMIT 1
            """, (subj_id, predicate, obj_id))
            conflict = cursor.fetchone()
            if conflict:
                if importance >= conflict['importance']:
                    cursor.execute("DELETE FROM facts WHERE id = ?", (conflict['id'],))
                    print(f"[Graph] Разрешён функциональный конфликт: '{subject} {predicate} {conflict['obj_name']}' заменён на '{obj}'")
                else:
                    print("[Graph] Конфликт проигнорирован: новый факт менее важен")
                    return -1

        cursor.execute("""
            INSERT INTO facts (subject_id, predicate, object_id, importance, last_accessed, access_count, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (subj_id, predicate, obj_id, importance, datetime.now(), 0, emb))
        self.conn.commit()
        return cursor.lastrowid

    def access_fact(self, fact_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE facts
            SET last_accessed = ?, access_count = access_count + 1
            WHERE id = ?
        ''', (datetime.now(), fact_id))
        self.conn.commit()

    def _current_rating(self, fact_row) -> float:
        importance = fact_row['importance']
        last_accessed = datetime.fromisoformat(fact_row['last_accessed'])
        access_count = fact_row['access_count']
        now = datetime.now()
        delta_seconds = (now - last_accessed).total_seconds()
        half_life = HALF_LIFE_DAYS * 24 * 3600
        time_decay = math.exp(-delta_seconds / half_life) if half_life > 0 else 1.0
        freq_bonus = 1.0 / (1.0 + 0.1 * access_count)
        rating = importance * time_decay * freq_bonus
        if delta_seconds < 30:
            rating *= 0.1
        return rating

    def get_relevant_facts(self, entity_names: list, limit: int = 5) -> list:
        if not entity_names:
            return []
        placeholders = ','.join(['?'] * len(entity_names))
        cursor = self.conn.cursor()
        cursor.execute(f'''
            SELECT id FROM entities WHERE name IN ({placeholders})
        ''', entity_names)
        entity_ids = [row['id'] for row in cursor.fetchall()]
        if not entity_ids:
            return []
        placeholders_ids = ','.join(['?'] * len(entity_ids))
        cursor.execute(f'''
            SELECT f.id, f.subject_id, f.predicate, f.object_id,
                   f.importance, f.last_accessed, f.access_count,
                   e1.name AS subject_name, e2.name AS object_name
            FROM facts f
            JOIN entities e1 ON f.subject_id = e1.id
            JOIN entities e2 ON f.object_id = e2.id
            WHERE (f.subject_id IN ({placeholders_ids}) OR f.object_id IN ({placeholders_ids}))
            AND e1.type != 'phrase' AND e2.type != 'phrase'
        ''', entity_ids * 2)
        rows = cursor.fetchall()
        scored = []
        for row in rows:
            rating = self._current_rating(row)
            scored.append((rating, dict(row)))
        scored.sort(key=lambda x: x[0], reverse=True)
        for _, fact in scored[:limit]:
            self.access_fact(fact['id'])
        return [fact for _, fact in scored[:limit]]

    def get_relevant_facts_expanded(self, entity_names: list, limit: int = 5, expand_depth: int = 2, max_facts: int = 50) -> list:
        if not entity_names:
            return []

        normalized_names = [self.normalize_name(name) for name in entity_names]
        placeholders = ','.join(['?'] * len(normalized_names))
        cursor = self.conn.cursor()
        cursor.execute(f'''
            SELECT id FROM entities WHERE name IN ({placeholders})
        ''', normalized_names)
        seed_ids = set(row['id'] for row in cursor.fetchall())
        if not seed_ids:
            return []

        all_fact_ids = set()
        current_entity_ids = set(seed_ids)

        for _ in range(expand_depth + 1):
            if not current_entity_ids or len(all_fact_ids) >= max_facts:
                break

            placeholders_ids = ','.join(['?'] * len(current_entity_ids))
            cursor.execute(f'''
                SELECT f.id, f.subject_id, f.object_id,
                       f.importance, f.last_accessed, f.access_count,
                       e1.name AS subject_name, e2.name AS object_name
                FROM facts f
                JOIN entities e1 ON f.subject_id = e1.id
                JOIN entities e2 ON f.object_id = e2.id
                WHERE (f.subject_id IN ({placeholders_ids}) OR f.object_id IN ({placeholders_ids}))
                AND e1.type != 'phrase' AND e2.type != 'phrase'
                LIMIT ?
            ''', list(current_entity_ids) * 2 + [max_facts - len(all_fact_ids)])

            new_facts = cursor.fetchall()
            next_entity_ids = set()

            for fact in new_facts:
                all_fact_ids.add(fact['id'])
                if fact['subject_id'] not in seed_ids:
                    next_entity_ids.add(fact['subject_id'])
                if fact['object_id'] not in seed_ids:
                    next_entity_ids.add(fact['object_id'])

            current_entity_ids = next_entity_ids

        if not all_fact_ids:
            return []

        placeholders_facts = ','.join(['?'] * len(all_fact_ids))
        cursor.execute(f'''
            SELECT f.id, f.subject_id, f.predicate, f.object_id,
                   f.importance, f.last_accessed, f.access_count,
                   e1.name AS subject_name, e2.name AS object_name
            FROM facts f
            JOIN entities e1 ON f.subject_id = e1.id
            JOIN entities e2 ON f.object_id = e2.id
            WHERE f.id IN ({placeholders_facts})
        ''', list(all_fact_ids))

        rows = cursor.fetchall()
        scored = []
        for row in rows:
            rating = self._current_rating(row)
            scored.append((rating, dict(row)))

        scored.sort(key=lambda x: x[0], reverse=True)

        for _, fact in scored[:limit]:
            self.access_fact(fact['id'])

        return [fact for _, fact in scored[:limit]]

    def search_facts_semantic(self, query: str, limit: int = 5) -> list:
        query_emb = self._get_embedding(query)
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, subject_id, predicate, object_id, embedding FROM facts WHERE embedding IS NOT NULL"
        )
        rows = cursor.fetchall()
        if not rows:
            return []
        scored = []
        for row in rows:
            sim = self._cosine_similarity(query_emb, row["embedding"])
            if sim > 0.5:
                scored.append((sim, dict(row)))
        scored.sort(key=lambda x: x[0], reverse=True)
        result = []
        seen = set()
        for sim, fact in scored[:limit]:
            subj_name = self._get_entity_name(fact["subject_id"])
            obj_name = self._get_entity_name(fact["object_id"])
            if subj_name and obj_name:
                text = f"{subj_name} {fact['predicate']} {obj_name}"
                key = text.lower()
                if key not in seen:
                    seen.add(key)
                    result.append(text)
        return result

    def _get_entity_name(self, entity_id: int) -> str | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM entities WHERE id = ?", (entity_id,))
        row = cursor.fetchone()
        return row["name"] if row else None

    def get_facts_as_strings(self, entity_names: list, limit: int = 5, expand: bool = True) -> list:
        if expand:
            facts = self.get_relevant_facts_expanded(entity_names, limit=limit, expand_depth=2)
        else:
            facts = self.get_relevant_facts(entity_names, limit=limit)
        return [f"{f['subject_name']} {f['predicate']} {f['object_name']}" for f in facts]

    def cleanup_low_importance(self, threshold: float = 0.01):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM facts")
        ids = [row['id'] for row in cursor.fetchall()]
        deleted = 0
        for fid in ids:
            cursor.execute('''
                SELECT importance, last_accessed, access_count FROM facts WHERE id = ?
            ''', (fid,))
            row = cursor.fetchone()
            if row:
                rating = self._current_rating(row)
                if rating < threshold:
                    cursor.execute("DELETE FROM facts WHERE id = ?", (fid,))
                    deleted += 1
        self.conn.commit()
        print(f"[Graph] Очистка: удалено {deleted} фактов с рейтингом < {threshold}")

    def boost_facts_by_entities(self, entity_names: list, limit: int = 5):
        """Обновляет last_accessed для фактов, связанных с сущностями."""
        if not entity_names:
            return
            
        placeholders = ','.join(['?'] * len(entity_names))
        cursor = self.conn.cursor()
        
        # Находим ID сущностей по именам
        cursor.execute(f'''
            SELECT id FROM entities WHERE name IN ({placeholders})
        ''', entity_names)
        entity_ids = [row['id'] for row in cursor.fetchall()]
        
        if not entity_ids:
            return
            
        placeholders_ids = ','.join(['?'] * len(entity_ids))
        # Обновляем дату последнего доступа для фактов, где эти сущности есть
        cursor.execute(f'''
            UPDATE facts 
            SET last_accessed = CURRENT_TIMESTAMP,
                access_count = access_count + 1
            WHERE subject_id IN ({placeholders_ids}) OR object_id IN ({placeholders_ids})
        ''', entity_ids * 2)
        
        self.conn.commit()
        print(f"[Graph] Усилены факты для сущностей: {entity_names[:3]}...")
        
    def close(self):
        self.conn.close()