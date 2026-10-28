# memory_core.py
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from config import STREAMER_ID
except Exception:
    STREAMER_ID = "Duncan"


@dataclass(frozen=True)
class MemoryFact:
    subject: str
    predicate: str
    object: str
    confidence: float = 0.75
    source_text: str = ""
    source_role: str = "user"

    def as_text(self) -> str:
        return f"{self.subject} {self.predicate} {self.object}"


class MemoryCore:
    MEMORY_TRIGGERS = (
        "помнишь", "вспомни", "вспоминай", "раньше", "обсуждали", "говорили",
        "рассказывал", "рассказывала", "что ты помнишь", "что знаешь",
        "омнишь", "помниш", "вспомнишь", "что именно", "какие детали",
        "точно помнишь", "что конкретно", "что я рассказывал", "что я говорил",
    )

    STOP_QUERY_WORDS = {
        "помнишь", "омнишь", "помниш", "вспомни", "вспоминай", "вспомнишь", "раньше", "обсуждали", "говорили", "рассказывал",
        "рассказывала", "про", "что", "как", "это", "было", "именно", "детали", "точно", "конкретно", "тебе", "тебя",
        "мне", "меня", "моем", "моём", "мой", "моя", "мои", "там", "тут",
        "ты", "я", "мы", "оно", "его", "её", "еще", "ещё", "сегодня",
    }

    def __init__(self, builder, person_id: str | None = None, display_name: str | None = None):
        self.builder = builder
        self.conn: sqlite3.Connection = builder.knowledge_conn
        self.person_id = person_id or STREAMER_ID or "Duncan"
        self.display_name = display_name or "Дункан"
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS verified_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL,
                source_role TEXT NOT NULL,
                source_text TEXT NOT NULL,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                confidence REAL DEFAULT 0.75,
                graph_fact_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(person_id, subject, predicate, object)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_verified_memory_person ON verified_memory(person_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_verified_memory_spo ON verified_memory(subject, predicate, object)")
        self.conn.commit()

    @staticmethod
    def normalize_text(text: str) -> str:
        text = str(text or "").replace("ё", "е")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _clean_object(text: str, limit: int = 120) -> str:
        text = MemoryCore.normalize_text(text)
        text = re.sub(r"^[,.:;!\-\s]+", "", text)
        text = re.sub(r"[,.:;!\-\s]+$", "", text)
        text = re.sub(r"\b(ну|типа|короче|в общем|вообще)\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit].strip()

    @staticmethod
    def _canonical_known(text: str) -> str:
        if not text:
            return text
        replacements = {
            "хогвартс": "Хогвардс",
            "хогвардс": "Хогвардс",
            "hogwarts": "Хогвардс",
            "darksouls": "Дарк Соулс",
            "dark souls": "Дарк Соулс",
            "elden ring": "Элден Ринг",
        }
        low = text.lower().replace("ё", "е")
        for key, value in replacements.items():
            low = low.replace(key, value)
        return low[:1].upper() + low[1:] if low else text

    def _subject_user(self) -> str:
        return self.display_name or "Дункан"

    def _strip_remember_prefix(self, text: str) -> str:
        return re.sub(r"^\s*запомни\s*[:\-—]?\s*", "", text, flags=re.IGNORECASE).strip()

    def _looks_like_question_or_meta_memory_request(self, lower: str, original: str) -> bool:
        # Questions should not create new long-term facts. Recall handles them separately.
        if "?" in original:
            return True
        if lower.startswith(("если ", "а если ")) or " значит " in lower:
            return True
        memory_request_markers = (
            "помнишь", "вспомни", "вспоминай", "давай вспоминай",
            "что я рассказывал", "что я говорил", "посмотри в памяти",
        )
        return any(marker in lower for marker in memory_request_markers)

    def extract_user_facts(self, text: str) -> List[MemoryFact]:
        text = self.normalize_text(text)
        if not text:
            return []

        if text.lstrip().startswith(("!", "/")):
            return []

        explicit_remember = bool(re.match(r"^\s*запомни\s*[:\-—]?\s*", text, flags=re.IGNORECASE))
        text = self._strip_remember_prefix(text)
        if not text:
            return []

        lower = text.lower()
        if any(x in lower for x in ["не выдум", "ты выдум", "детали ты выдум", "не ври", "соврала", "врешь", "врёшь"]):
            return []
        if not explicit_remember and self._looks_like_question_or_meta_memory_request(lower, text):
            return []

        subject = self._subject_user()
        facts: List[MemoryFact] = []

        def add(predicate: str, obj: str, confidence: float = 0.78):
            obj = self._canonical_known(self._clean_object(obj))
            if self._valid_extracted_fact(subject, predicate, obj):
                facts.append(MemoryFact(subject, predicate, obj, confidence, text, "user"))

        for pattern in [
            r"\bменя\s+зовут\s+([A-Za-zА-Яа-я0-9_@\-\s]{2,40})",
            r"\bмое\s+имя\s+([A-Za-zА-Яа-я0-9_@\-\s]{2,40})",
            r"\bмоё\s+имя\s+([A-Za-zА-Яа-я0-9_@\-\s]{2,40})",
        ]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                add("зовут", m.group(1), 0.9)

        preference_patterns = [
            (r"\bя\s+(?:очень\s+)?(?:люблю|обожаю)\s+(.+)", "любит", 0.82),
            (r"\bмне\s+(?:очень\s+)?нравится\s+(.+)", "любит", 0.78),
            (r"\bя\s+(?:не\s+люблю|ненавижу)\s+(.+)", "не любит", 0.82),
            (r"\bмой\s+любимый\s+жанр\s*[—:\-]?\s*(.+)", "любит жанр", 0.86),
        ]
        for pattern, predicate, confidence in preference_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                obj = m.group(1)
                obj = re.split(r"[.?!;]|,\s*значит|\s+значит\s+|\s+но\s+|\s+потому\s+что\s+", obj, maxsplit=1, flags=re.IGNORECASE)[0]
                add(predicate, obj, confidence)

        has_dream = any(marker in lower for marker in ("сон", "снился", "приснился", "во сне"))
        if has_dream:
            if re.search(r"хогвар[дт]с|hogwarts", lower):
                add("рассказывал сон про", "Хогвардс", 0.9)
                if re.search(r"\bколдун\w*|\bмаг\w*|\bволшебник\w*", lower):
                    add("во сне был", "колдуном в Хогвардсе", 0.88)
                if re.search(r"спрятанн\w*\s+комнат|комнат\w*\s+спрятанн", lower):
                    add("видел во сне", "много спрятанных комнат в Хогвардсе", 0.88)
            else:
                m = re.search(r"(?:мне\s+)?(?:снился|приснился)\s+(.+)", text, re.IGNORECASE)
                if m:
                    add("рассказывал сон про", re.split(r"[.?!;]", m.group(1), maxsplit=1)[0], 0.78)
                m = re.search(r"во\s+сне\s+я\s+(?:попал|оказался|был)\s+(.+)", text, re.IGNORECASE)
                if m:
                    add("рассказывал сон про", re.split(r"[.?!;]", m.group(1), maxsplit=1)[0], 0.76)

        if not self._looks_like_question_or_meta_memory_request(lower, text):
            m = re.search(r"\bя\s+(?:тебе\s+)?рассказывал\w*\s+(?:про|о|об)\s+(.+)", text, re.IGNORECASE)
            if m:
                obj = self._clean_object(re.split(r"[.?!;]", m.group(1), maxsplit=1)[0])
                if obj:
                    add("рассказывал про", obj, 0.68)

        unique: Dict[tuple[str, str, str], MemoryFact] = {}
        for fact in facts:
            key = (fact.subject.lower(), fact.predicate.lower(), fact.object.lower())
            prev = unique.get(key)
            if not prev or fact.confidence > prev.confidence:
                unique[key] = fact
        return list(unique.values())

    def _valid_extracted_fact(self, subject: str, predicate: str, obj: str) -> bool:
        if not subject or not predicate or not obj:
            return False
        obj_low = self.normalize_text(obj).lower()
        pred_low = self.normalize_text(predicate).lower()
        low = f"{subject} {predicate} {obj}".lower()
        if "?" in low:
            return False
        if len(obj) < 2 or len(obj) > 120:
            return False
        bad_objects = {
            "это", "такое", "что-то", "что то", "ничего", "none", "null", "???",
            "тебя", "тебе", "меня", "его", "ее", "её", "нас", "вас", "ты", "я",
        }
        if obj_low in bad_objects:
            return False
        if pred_low in {"любит", "не любит", "любит жанр"}:
            if obj_low.startswith(("тебя", "тебе", "меня", "его", "ее", "её", "нас", "вас", "моник")):
                return False
            if any(marker in obj_low for marker in [" значит ", "если ", " я люблю ", " моника "]):
                return False
        if any(marker in low for marker in ["моника сказала", "моника ответила", "[актуальные факты]"]):
            return False
        return True

    def observe_user_message(self, text: str, person_id: str | None = None) -> List[Dict[str, Any]]:
        saved = []
        for fact in self.extract_user_facts(text):
            graph_id = self.store_fact(fact, person_id=person_id or self.person_id)
            if graph_id is not None:
                saved.append({
                    "subject": fact.subject,
                    "predicate": fact.predicate,
                    "object": fact.object,
                    "confidence": fact.confidence,
                    "graph_fact_id": graph_id,
                })
        return saved

    def store_fact(self, fact: MemoryFact, person_id: str | None = None) -> Optional[int]:
        normalized = self.builder.normalize_fact_triplet(fact.subject, fact.predicate, fact.object, source=fact.source_role)
        if not normalized:
            return None
        subject, predicate, obj = normalized
        if not self.builder.is_stable_fact(subject, predicate, obj, source=fact.source_role):
            return None
        graph_id = self.builder.add_fact_triplet(
            subject, predicate, obj,
            importance=max(1.0, float(fact.confidence) * 2.0),
            source=fact.source_role,
            source_text=fact.source_text,
        )
        if graph_id is None or int(graph_id) < 0:
            return None

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO verified_memory (
                person_id, source_role, source_text, subject, predicate, object,
                confidence, graph_fact_id, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(person_id, subject, predicate, object)
            DO UPDATE SET
                source_text = excluded.source_text,
                confidence = MAX(verified_memory.confidence, excluded.confidence),
                graph_fact_id = COALESCE(excluded.graph_fact_id, verified_memory.graph_fact_id),
                last_seen = CURRENT_TIMESTAMP
        """, (
            person_id or self.person_id,
            fact.source_role,
            fact.source_text,
            subject,
            predicate,
            obj,
            float(fact.confidence),
            int(graph_id),
        ))
        self.conn.commit()
        return int(graph_id)

    def _query_anchors(self, query: str) -> List[str]:
        q = self.normalize_text(query).lower()
        aliases = []
        if re.search(r"хогвар[дт]с|hogwarts", q):
            aliases += ["хогвардс", "хогвартс", "Хогвардс"]
        if re.search(r"dark\s*souls|darksouls|дарк\s*соул", q):
            aliases += ["dark souls", "darksouls", "Дарк Соулс"]
        if re.search(r"elden\s*ring|элден", q):
            aliases += ["elden ring", "Элден Ринг"]
        words = re.findall(r"[A-Za-zА-Яа-яЁё0-9_@\-]{4,}", q)
        for word in words:
            if word not in self.STOP_QUERY_WORDS:
                aliases.append(word)
        result, seen = [], set()
        for alias in aliases:
            key = alias.lower()
            if key not in seen:
                seen.add(key)
                result.append(alias)
        return result[:8]

    def _matches_anchors(self, text: str, anchors: List[str]) -> bool:
        if not anchors:
            return False
        low = self.normalize_text(text).lower()
        for anchor in anchors:
            ak = anchor.lower()
            if ak in low:
                return True
            if ak.startswith("хогвар") and ("хогвардс" in low or "хогвартс" in low):
                return True
        return False

    def recall(self, query: str, limit: int = 3, person_id: str | None = None) -> Dict[str, Any]:
        anchors = self._query_anchors(query)
        facts: List[str] = []
        sources: List[Dict[str, Any]] = []
        confidence = "none"

        try:
            graph_facts = self.builder.search_facts(query, top_k=max(limit, 5))
        except Exception:
            graph_facts = []
        for fact in graph_facts:
            fact_text = str(fact or "").strip()
            if fact_text and self._matches_anchors(fact_text, anchors):
                item = f"[Проверенная память]: {fact_text}"
                if item not in facts:
                    facts.append(item)
                    sources.append({"source": "graph", "text": fact_text})
                    confidence = "high"

        cur = self.conn.cursor()
        if anchors:
            clauses, params = [], []
            for anchor in anchors:
                like = f"%{anchor}%"
                clauses.append("(subject LIKE ? OR predicate LIKE ? OR object LIKE ? OR source_text LIKE ?)")
                params.extend([like, like, like, like])
            params.append(person_id or self.person_id)
            cur.execute(f"""
                SELECT subject, predicate, object, confidence, source_text, created_at
                FROM verified_memory
                WHERE ({" OR ".join(clauses)}) AND person_id = ?
                ORDER BY confidence DESC, last_seen DESC
                LIMIT ?
            """, params + [limit * 2])
            for row in cur.fetchall():
                text = f"{row['subject']} {row['predicate']} {row['object']}"
                item = f"[Проверенная память]: {text}"
                if item not in facts:
                    facts.append(item)
                    sources.append({"source": "verified_memory", "text": text, "source_text": row["source_text"]})
                    if confidence == "none":
                        confidence = "high" if float(row["confidence"] or 0) >= 0.75 else "medium"

        if len(facts) < limit and anchors:
            clauses, params = [], [person_id or self.person_id]
            for anchor in anchors:
                clauses.append("message LIKE ?")
                params.append(f"%{anchor}%")
            cur.execute(f"""
                SELECT id, message, timestamp
                FROM chat_history
                WHERE user_id = ? AND role = 'user' AND ({" OR ".join(clauses)})
                ORDER BY id DESC
                LIMIT ?
            """, params + [20])
            for row in cur.fetchall():
                for fact in self.extract_user_facts(row["message"]):
                    text = fact.as_text()
                    if self._matches_anchors(text, anchors):
                        item = f"[Память из слов пользователя]: {text}"
                        if item not in facts:
                            facts.append(item)
                            sources.append({"source": "chat_history:user", "text": text, "rowid": row["id"]})
                            if confidence == "none":
                                confidence = "medium"
                if len(facts) >= limit:
                    break

        facts = facts[:limit]
        if not facts:
            confidence = "low" if any(t in self.normalize_text(query).lower() for t in self.MEMORY_TRIGGERS) else "none"

        return {"facts": facts, "sources": sources, "confidence": confidence, "anchors": anchors}
