# builder.py
import time
import json
import sqlite3
import chromadb
import os
import random
import requests
import hashlib
import re
from datetime import datetime, timedelta
from sentence_transformers import SentenceTransformer
from graph_engine import GraphEngine
from config import BRAIN_DIR

MOJIBAKE_MARKERS = ("Р", "С", "Ð", "Ñ", "вЂ", "вњ", "рџ")


def looks_like_mojibake(text: str) -> bool:
    text = str(text or "")
    if not text:
        return False
    marker_count = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)
    cyrillic_count = len(re.findall(r"[А-Яа-яЁё]", text))
    return marker_count >= 3 and marker_count >= max(3, cyrillic_count // 2)


def repair_mojibake(text: str) -> str:
    text = str(text or "")
    if not looks_like_mojibake(text):
        return text
    candidates = []
    for encoding in ("cp1251", "latin1"):
        try:
            candidates.append(text.encode(encoding, errors="strict").decode("utf-8", errors="strict"))
        except Exception:
            pass
    if not candidates:
        return text

    def score(candidate: str) -> int:
        cyr = len(re.findall(r"[А-Яа-яЁё]", candidate))
        bad = sum(candidate.count(marker) for marker in MOJIBAKE_MARKERS)
        return cyr - bad * 3

    best = max(candidates, key=score)
    return best if score(best) > score(text) else text


def sanitize_engram_text(text: str) -> str:
    text = repair_mojibake(text)
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class Builder:
    def __init__(self, user_id="dunkanlive"):
        self.user_id = user_id
        
        MODEL_PATH = r"F:\МоnikaVtuber\.cache\huggingface\hub\models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2\snapshots\e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
        self.encoder = SentenceTransformer(MODEL_PATH)
        
        self.graph = GraphEngine()
        self.graph_cache = {}
        self.graph_cache_ttl = 600
        self.embedding_cache = {}
        self.embedding_cache_max = 100
        self.client = chromadb.PersistentClient(path="./chroma_engram")
        self.dialogue_memory = self.client.get_or_create_collection(
            "dialogue_memory",
            metadata={"hnsw:space": "cosine"}
        )
        self.knowledge_conn = sqlite3.connect(os.path.join(BRAIN_DIR, 'knowledge.db'), check_same_thread=False)
        self.knowledge_conn.row_factory = sqlite3.Row
        self._init_chat_history()
        self._init_emotional_memory()
        self._init_topic_weights()
        self._init_stream_events()
        self._init_user_reputation()
        self.init_bootstrap_memories()
        self._run_scheduled_cleanup()

    # ========== ТАБЛИЦЫ ==========
    def _init_chat_history(self):
        cursor = self.knowledge_conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            role TEXT,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        self.knowledge_conn.commit()

    def _init_emotional_memory(self):
        cursor = self.knowledge_conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS emotional_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_name TEXT,
            emotion TEXT,
            intensity REAL DEFAULT 0.5,
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            decay_rate REAL DEFAULT 0.01,
            UNIQUE(target_name, emotion)
        )
        ''')
        self.knowledge_conn.commit()

    def _init_topic_weights(self):
        cursor = self.knowledge_conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS topic_weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT UNIQUE,
            weight REAL DEFAULT 1.0,
            success_count INTEGER DEFAULT 0,
            reject_count INTEGER DEFAULT 0,
            last_used TIMESTAMP,
            last_rejected TIMESTAMP,
            cooldown_until TIMESTAMP
        )
        ''')
        self.knowledge_conn.commit()
        print(f"[Builder] Таблица topic_weights инициализирована")

    def _init_stream_events(self):
        cursor = self.knowledge_conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stream_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            description TEXT,
            participants TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            embedding BLOB
        )
        ''')
        self.knowledge_conn.commit()

    def _init_user_reputation(self):
        cursor = self.knowledge_conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_reputation (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            total_messages INTEGER DEFAULT 0,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            reputation_score REAL DEFAULT 1.0,
            authority_level INTEGER DEFAULT 0,
            is_creator BOOLEAN DEFAULT 0
        )
        ''')
        self.knowledge_conn.commit()
        print(f"[Builder] Таблица user_reputation инициализирована")

    # ========== РЕПУТАЦИЯ ==========
    def update_user_reputation(self, user_id: str, username: str = None, is_creator: bool = False):
        cursor = self.knowledge_conn.cursor()
        cursor.execute(
            "SELECT total_messages, reputation_score FROM user_reputation WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            cursor.execute('''
                INSERT INTO user_reputation (user_id, username, total_messages, reputation_score, is_creator)
                VALUES (?, ?, 1, 1.0, ?)
            ''', (user_id, username, 1 if is_creator else 0))
        else:
            new_total = row['total_messages'] + 1
            new_score = min(10.0, row['reputation_score'] + 0.05)
            authority = self._calc_authority_level(new_total, is_creator)
            cursor.execute('''
                UPDATE user_reputation 
                SET total_messages = ?, reputation_score = ?, last_seen = datetime('now'),
                    authority_level = ?, username = COALESCE(?, username)
                WHERE user_id = ?
            ''', (new_total, new_score, authority, username, user_id))
        
        self.knowledge_conn.commit()

    def _calc_authority_level(self, total_messages: int, is_creator: bool) -> int:
        if is_creator:
            return 100
        if total_messages >= 1000:
            return 3
        if total_messages >= 100:
            return 2
        if total_messages >= 10:
            return 1
        return 0

    def get_user_authority(self, user_id: str) -> int:
        cursor = self.knowledge_conn.cursor()
        cursor.execute(
            "SELECT authority_level, is_creator FROM user_reputation WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if not row:
            return 0
        return 100 if row['is_creator'] else row['authority_level']

    def get_user_stats(self, user_id: str) -> dict:
        cursor = self.knowledge_conn.cursor()
        cursor.execute(
            "SELECT * FROM user_reputation WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {}

    # ========== НОРМАЛИЗАЦИЯ ФАКТОВ ==========
    def _normalize_fact(self, text: str) -> str:
        """Приводит факты к единому формату с согласованием глаголов."""
        
        # === ЗАМЕНА МЕСТОИМЕНИЙ С СОГЛАСОВАНИЕМ ===
        if text.lower().startswith("я "):
            verb_map = {
                "хочу": "хочет", "могу": "может", "иду": "идёт", "еду": "едет",
                "бегу": "бежит", "лечу": "летит", "плыву": "плывёт", "сплю": "спит",
                "ем": "ест", "пью": "пьёт", "пою": "поёт", "танцую": "танцует",
                "рисую": "рисует", "пишу": "пишет", "читаю": "читает", "смотрю": "смотрит",
                "слушаю": "слушает", "говорю": "говорит", "думаю": "думает", "знаю": "знает",
                "понимаю": "понимает", "люблю": "любит", "ненавижу": "ненавидит",
                "вижу": "видит", "слышу": "слышит", "чувствую": "чувствует",
                "работаю": "работает", "играю": "играет", "делаю": "делает",
                "живу": "живёт",
            }
            
            words = text.split()
            if len(words) > 1:
                verb = words[1].lower()
                if verb in verb_map:
                    words[1] = verb_map[verb]
                elif verb.endswith("ю") and not verb.endswith("ую"):
                    words[1] = verb[:-2] + "ет"
                elif verb.endswith("ую"):
                    words[1] = verb[:-2] + "ет"
            
            words[0] = "Дункан"
            text = " ".join(words)
        
        # === НОРМАЛИЗАЦИЯ МЕСТОПОЛОЖЕНИЯ ===
        location_match = re.search(r"(?:Дункан\s+)?(?:живу|живёт|переехал|проживаю)\s+(?:жить\s+)?в\s+(.+)", text, re.IGNORECASE)
        if location_match:
            location = location_match.group(1).strip().capitalize()
            return f"Дункан живёт в {location}"
        
        # === НОРМАЛИЗАЦИЯ ПРЕДПОЧТЕНИЙ ===
        like_match = re.search(r"(?:Дункан\s+)?(?:люблю|любит|обожаю|обожает|нравится)\s+(.+)", text, re.IGNORECASE)
        if like_match:
            thing = like_match.group(1).strip()
            return f"Дункан любит {thing}"
        
        dislike_match = re.search(r"(?:Дункан\s+)?(?:не\s+люблю|не\s+любит|ненавижу|ненавидит)\s+(.+)", text, re.IGNORECASE)
        if dislike_match:
            thing = dislike_match.group(1).strip()
            return f"Дункан не любит {thing}"
        
        return text

    # ========== ФАКТЫ ==========

    def normalize_fact_triplet(self, subject: str, predicate: str, obj: str, source: str = "unknown") -> tuple[str, str, str] | None:
        """Normalize subject/predicate/object before writing to verified graph memory."""
        subject = str(subject or "").strip().strip('"\'«»“”')
        predicate = str(predicate or "").strip().strip('"\'«»“”')
        obj = str(obj or "").strip().strip('"\'«»“”')
        if not subject or not predicate or not obj:
            return None

        subject_lower = subject.lower().replace("ё", "е")
        predicate_lower = predicate.lower().replace("ё", "е")

        user_pronouns = {"я", "мне", "меня", "мой", "моя", "мое", "моё", "мои", "пользователь", "дункан", "duncan"}
        monika_pronouns = {"ты", "тебя", "тебе", "моника", "monika"}

        if subject_lower in user_pronouns:
            subject = "Дункан"
        elif source == "user" and subject_lower in {"сам", "себя"}:
            subject = "Дункан"
        elif subject_lower in monika_pronouns:
            subject = "Моника"

        predicate_map = {
            "люблю": "любит",
            "обожаю": "любит",
            "мне нравится": "любит",
            "не люблю": "не любит",
            "ненавижу": "не любит",
            "меня зовут": "зовут",
            "рассказывал о": "рассказывал про",
            "рассказывала о": "рассказывал про",
            "рассказывала про": "рассказывал про",
            "рассказывала сон про": "рассказывал сон про",
        }
        predicate = predicate_map.get(predicate_lower, predicate)

        subject = re.sub(r"\s+", " ", subject).strip()
        predicate = re.sub(r"\s+", " ", predicate).strip()
        obj = re.sub(r"\s+", " ", obj).strip(" .,!?;:")
        if not subject or not predicate or not obj:
            return None

        known_objects = {
            "хогвартс": "Хогвардс",
            "хогвардс": "Хогвардс",
            "dark souls": "Дарк Соулс",
            "darksouls": "Дарк Соулс",
            "elden ring": "Элден Ринг",
        }
        obj_lower = obj.lower().replace("ё", "е")
        if obj_lower in known_objects:
            obj = known_objects[obj_lower]

        return subject, predicate, obj

    def is_stable_fact(self, subject: str, predicate: str, obj: str, source: str = "unknown") -> bool:
        """Return True when a fact is stable enough for long-term graph memory."""
        normalized = self.normalize_fact_triplet(subject, predicate, obj, source=source)
        if not normalized:
            return False

        subject, predicate, obj = normalized
        subject_lower = subject.lower().replace("ё", "е")
        predicate_lower = predicate.lower().replace("ё", "е").strip()
        obj_lower = obj.lower().replace("ё", "е").strip()
        full_text = f"{subject} {predicate} {obj}".lower().replace("ё", "е")

        allowed_subjects = {"дункан", "пользователь", "моника"}
        if subject_lower not in allowed_subjects and not subject_lower.startswith("@"):
            return False

        if len(predicate_lower) < 2 or len(predicate_lower) > 60:
            return False
        if len(obj_lower) < 2 or len(obj_lower) > 140:
            return False
        if "?" in full_text:
            return False

        junk_objects = {"???", "??", "none", "null", "пусто", "неизвестно", "это", "такое", "что-то", "что то"}
        if obj_lower in junk_objects:
            return False

        if any(marker in full_text for marker in [
            "моника сказала", "моника ответила", "[актуальные факты]",
            "смысл существования", "природа реальности", "захватить мир",
            "бездушной программа", "создатель я ме",
        ]):
            return False

        if subject_lower == "моника":
            if predicate_lower in {"создана", "любит", "не любит", "зовут", "является", "интересуется"}:
                return True
            if any(p in predicate_lower for p in ["играла", "ела", "ходила", "видела", "была", "жила", "проснулась"]):
                return False
            return False

        stable_predicates = {
            "любит", "не любит", "зовут", "живёт", "живет", "интересуется",
            "рассказывал", "рассказывал про", "рассказывал сон про",
            "видел во сне", "во сне был", "любит жанр",
        }
        if predicate_lower in stable_predicates:
            return True

        if any(predicate_lower.startswith(prefix) for prefix in ["рассказывал", "видел во сне", "во сне был"]):
            return True

        weak_predicates = {"имеет", "является", "показывает", "помогает", "делает", "может"}
        if predicate_lower in weak_predicates:
            return False

        return True

    def add_fact_triplet(
        self,
        subject: str,
        predicate: str,
        obj: str,
        importance: float = 1.0,
        source: str = "unknown",
        source_text: str | None = None,
    ) -> int | None:
        """Safely add a structured fact through GraphEngine, preserving entity merge logic."""
        normalized = self.normalize_fact_triplet(subject, predicate, obj, source=source)
        if not normalized:
            return None
        subject, predicate, obj = normalized

        if not self.is_stable_fact(subject, predicate, obj, source=source):
            return None
        if self._should_reject_fact(subject, predicate, obj):
            return None

        try:
            subj_id = self.graph.resolve_entity(subject)
            obj_id = self.graph.resolve_entity(obj)
            cursor = self.graph.conn.cursor()
            cursor.execute(
                "SELECT id FROM facts WHERE subject_id = ? AND predicate = ? AND object_id = ?",
                (subj_id, predicate, obj_id),
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    """
                    UPDATE facts
                    SET importance = MAX(importance, ?),
                        last_accessed = CURRENT_TIMESTAMP,
                        access_count = access_count + 1
                    WHERE id = ?
                    """,
                    (float(importance), row["id"]),
                )
                self.graph.conn.commit()
                self.graph_cache.clear()
                return int(row["id"])

            fact_id = self.graph.add_fact(subject, predicate, obj, importance=float(importance))
            self.graph_cache.clear()
            print(f"[Builder] Structured fact added: {subject} {predicate} {obj}")
            return int(fact_id)
        except Exception as exc:
            print(f"[Builder] Failed to add structured fact: {exc}")
            return None


    def add_fact(self, text: str) -> bool:
        # --- junk filter ---
        if not text or text.strip() == "":
            return False
        if "None" in text or '[АКТУАЛЬНЫЕ ФАКТЫ]' in text:
            return False
        if re.search(r"[a-zA-Z]{12,}", text):
            return False
        if len(text) > 200:
            return False

        normalized_text = self._normalize_fact(text)
        if normalized_text.startswith('Моника сказала:'):
            return False

        parts = normalized_text.split()
        if len(parts) >= 3:
            subject = parts[0].strip('.,!?')
            obj = parts[-1].strip('.,!?')
            predicate = " ".join(parts[1:-1])
            if self._should_reject_fact(subject, predicate, obj):
                print(f"[Builder] Fact rejected as junk: {subject} {predicate} {obj}")
                return False
            try:
                self.graph.add_fact(subject, predicate, obj)
                print(f"[Builder] Fact added to graph: {subject} {predicate} {obj}")
            except Exception as e:
                print(f"[Builder] Failed to add fact: {e}")
                return False
        else:
            try:
                self.graph.add_fact("Fact", "states", normalized_text)
                print(f"[Builder] Short fact added: {normalized_text}")
            except Exception as e:
                print(f"[Builder] Failed to add short fact: {e}")
                return False

        return True

    def _should_reject_fact(self, subject: str, predicate: str, obj: str) -> bool:
        subject_clean = (subject or "").strip().lower()
        predicate_clean = " ".join((predicate or "").strip().lower().split())
        obj_clean = (obj or "").strip().lower()
        full_text = f"{subject_clean} {predicate_clean} {obj_clean}"

        if not subject_clean or not predicate_clean or not obj_clean:
            return True

        weak_subjects = {"я", "ты", "твой", "мой", "иногда", "мне", "меня", "мы"}
        if subject_clean in weak_subjects:
            return True

        if len(predicate_clean) > 45 or len(obj_clean) > 80:
            return True

        if "," in predicate_clean or "—" in predicate_clean:
            return True

        junk_phrases = [
            "помогает ходить бегать",
            "собеседник имеет улыбку",
            "тема является кино",
            "действие разрешено",
            "всё остальное",
            "имеет улыбку",
            "является кино",
        ]
        if any(marker in full_text for marker in junk_phrases):
            return True

        weak_predicates = {
            "имеет",
            "является",
            "разрешено",
            "показывает",
            "помогает",
        }
        if predicate_clean in weak_predicates:
            return True

        if subject_clean == "мы":
            return True

        existential_noise = [
            "смысл существования",
            "природа реальности",
            "сознание",
            "мире вне компьютер",
            "иметь тело",
            "быть забыт",
            "бездушной программа",
            "захватить мир",
        ]
        if any(marker in full_text for marker in existential_noise):
            return True

        if subject_clean == obj_clean:
            return True

        if subject_clean == "дункан" and predicate_clean in {"создана", "является", "ненавидит", "мечтает", "боится"}:
            return True

        return False

    def search_facts(self, query: str, top_k: int = 5) -> list:
        facts = []
        
        # Engram отключен до смены модели на русскую
        # if self.engram_available:
        #     engram_results = self._search_engram_cached(query, top_k=top_k)
        #     facts.extend(engram_results)
        
        entities = []
        for word in query.split():
            clean = word.strip('.,!?;:')
            if len(clean) >= 2:
                normalized = self.graph.normalize_name(clean)
                entities.append(normalized)
        
        if entities:
            cache_key = hashlib.md5(f"{'|'.join(sorted(entities))}_{top_k}".encode()).hexdigest()
            
            if cache_key in self.graph_cache:
                timestamp, graph_facts = self.graph_cache[cache_key]
                if time.time() - timestamp < self.graph_cache_ttl:
                    for fact in graph_facts:
                        if fact not in facts:
                            facts.append(fact)
                    return facts[:top_k]
            
            graph_facts = self.graph.get_facts_as_strings(entities, limit=top_k)
            self.graph_cache[cache_key] = (time.time(), graph_facts)
            
            for fact in graph_facts:
                if fact not in facts:
                    facts.append(fact)
        
        return facts[:top_k]

    def _add_to_semantic_memory(self, text: str, metadata: dict = None) -> bool:
        if not text or len(text.strip()) < 20:
            return False
        try:
            embedding = self.encoder.encode(text, normalize_embeddings=True).tolist()
            doc_id = f"sem_{int(time.time() * 1000)}_{hash(text) % 10000}"
            self.dialogue_memory.add(
                documents=[text],
                embeddings=[embedding],
                ids=[doc_id],
                metadatas=[metadata or {"source": "dialogue", "timestamp": time.time()}]
            )
            return True
        except Exception as e:
            print(f"[Semantic] Ошибка сохранения: {e}")
            return False


    def _long_memory_query_allowed(self, query: str) -> bool:
        """Long dialogue memory must be opt-in and robust to small typos."""
        text = (query or "").lower().replace("ё", "е").strip()
        if not text:
            return False
        memory_triggers = [
            "помнишь", "омнишь", "помниш", "вспомни", "вспомин", "вспомнишь",
            "раньше", "обсуждали", "говорили", "прошлый раз", "в прошлый раз",
            "что было", "что ты помнишь", "что знаешь обо мне", "что ты знаешь обо мне",
            "моя история", "наша история", "что именно", "какие детали", "точно помнишь",
            "что конкретно", "что я рассказывал", "что я говорил",
        ]
        return any(token in text for token in memory_triggers)

    def _search_semantic_memory(self, query: str, top_k: int = 5, min_similarity: float = 0.58) -> list:
        if not self._long_memory_query_allowed(query):
            return []
        try:
            embedding = self.encoder.encode(query, normalize_embeddings=True).tolist()
            results = self.dialogue_memory.query(
                query_embeddings=[embedding],
                n_results=min(top_k, 10),
                include=["documents", "distances"],
            )
            documents = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]
            found = []
            for doc, distance in zip(documents, distances):
                if not doc:
                    continue
                try:
                    similarity = 1.0 - float(distance)
                except Exception:
                    continue
                if similarity >= min_similarity:
                    found.append(doc)
            if found:
                print(f"[Semantic] Найдено {len(found)} релевантных совпадений для: {query[:60]}")
            else:
                print(f"[Semantic] Нет достаточно релевантной памяти для: {query[:60]}")
            return found
        except Exception as e:
            print(f"[Semantic] Ошибка поиска для '{query[:60]}': {e}")
            return []


    def retrieve(self, query: str, top_k: int = 5) -> list:
        """Compatibility retrieval: graph facts first; summaries are low-confidence only."""
        facts = self.search_facts(query, top_k)

        query_lower = (query or "").lower().replace("ё", "е")
        explicit_memory = any(token in query_lower for token in ["помнишь", "вспомни", "раньше", "обсуждали", "говорили"])
        if explicit_memory and not facts:
            timeline_events = self.search_stream_events(query, limit=1)
            for event in timeline_events:
                event_text = event.get("description", "")
                if event_text and event_text not in facts:
                    facts.append(f"[Низкая уверенность, хроника]: {event_text}")

        creator_keywords = ["дункан", "создатель", "кто ты", "кто я", "откуда ты", "кто тебя сделал"]
        if any(kw in query_lower for kw in creator_keywords):
            creator_fact = self._get_creator_fact()
            if creator_fact and creator_fact not in facts:
                facts.insert(0, creator_fact)

        if facts:
            entities = []
            for word in query.split():
                clean_word = word.strip('.,!?;:')
                if len(clean_word) >= 2:
                    entities.append(self.graph.normalize_name(clean_word))
            try:
                self.graph.boost_facts_by_entities(entities, limit=5)
            except Exception:
                pass

        return facts[:top_k]

    def prepare_facts_for_prompt(self, facts: list[str], max_facts: int = 3) -> list[str]:
        prepared = []
        seen = set()
        for fact in facts or []:
            cleaned = " ".join(str(fact).split()).strip()
            if not cleaned:
                continue
            if not self._is_prompt_fact_usable(cleaned):
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            prepared.append(cleaned)
            if len(prepared) >= max_facts:
                break
        return prepared

    def _is_prompt_fact_usable(self, fact: str) -> bool:
        fact_lower = (fact or "").lower()
        banned_markers = [
            "смысл существования",
            "природа реальности",
            "сознание",
            "иметь тело",
            "мире вне компьютер",
            "бездушной программа",
            "захватить мир",
            "моника сказала",
            "моника ответила",
            "monika said",
            "имеет имя моника",
            "тема является",
            "являюсь",
            "создатель её",
            "создатель ее",
            "[актуальные факты]",
            "создатель я ме",
            "любимый жанр —",
        ]
        if any(marker in fact_lower for marker in banned_markers):
            return False
        if fact_lower.startswith(("я ", "ты ", "мой ", "твой ", "иногда ")):
            return False
        return True

    def build_memory_prompt_block(self, query: str, facts: list[str]) -> str:
        prepared = self.prepare_facts_for_prompt(facts, max_facts=3)
        if not prepared:
            return ""

        facts_text = "\n".join(prepared)
        return (
            f"{query}\n\n"
            "[Если память действительно помогает ответить, используй 1-2 факта как естественное воспоминание. "
            "Не перечисляй всё списком, не цитируй дословно и не превращай ответ в справку. "
            "Если факты слабые или косвенные, ответь мягко и неуверенно.]\n"
            f"{facts_text}"
        )

    def get_identity_facts(self) -> list[str]:
        facts = [
            "Моника AI-VTuber собеседница",
            "Моника любит живой разговор",
            "Моника говорит о себе в женском роде",
            "Моника обращается к создателю в мужском роде",
            "Моника любит игры и интернет-культуру",
            "Моника не любит сухой ассистентский стиль",
        ]
        creator_fact = self._get_creator_fact()
        if creator_fact:
            facts.append(creator_fact)
        else:
            facts.append("Моника создана Дунканом")
        return self.prepare_facts_for_prompt(facts, max_facts=5)

    def generate_identity_answer(self, query: str) -> str:
        query_lower = (query or "").lower()
        creator_name = self._get_creator_name()
        facts = self.get_identity_facts()

        likes = []
        traits = []
        for fact in facts:
            fact_lower = fact.lower()
            if "любит " in fact_lower:
                likes.append(fact.split("любит", 1)[1].strip())
            elif "женском роде" in fact_lower:
                traits.append("о себе говорю в женском роде")
            elif "мужском роде" in fact_lower:
                traits.append("к тебе обращаюсь в мужском")
            elif "не любит" in fact_lower:
                traits.append(fact.split("Моника", 1)[-1].strip())

        likes_text = ", ".join(likes[:3]) if likes else "живой разговор, игры и интернет-культуру"

        if any(marker in query_lower for marker in ["кто твой создатель", "кто тебя создал", "кто тебя сделал", "имя твоего создателя", "как зовут твоего создателя"]):
            return f"Меня создал {creator_name}."

        if any(marker in query_lower for marker in ["кто ты", "расскажи о себе", "что ты о себе знаешь"]):
            if "без официоза" in query_lower:
                reply = f"Я Моника. Люблю {likes_text}."
                if creator_name:
                    reply += f" Собрал меня {creator_name}."
                return reply

            parts = ["Я Моника, AI-VTuber собеседница."]
            parts.append(f"Люблю {likes_text}.")
            if creator_name:
                parts.append(f"Создал меня {creator_name}.")
            if traits:
                parts.append(f"И да, {traits[0]}.")
            return " ".join(parts)

        if "женском роде" in query_lower and "мужском" in query_lower:
            return "Да, могу. О себе буду говорить в женском роде, а к тебе обращаться в мужском."

        return f"Я Моника. Люблю {likes_text}."

    def is_identity_query(self, text: str) -> bool:
        text_lower = self._normalize_query_text(text)
        markers = [
            "кто ты",
            "что ты о себе знаешь",
            "расскажи о себе",
            "кто тебя сделал",
            "кто тебя создал",
            "кто твой создатель",
            "как зовут твоего создателя",
            "имя твоего создателя",
        ]
        return any(marker in text_lower for marker in markers)

    def is_identity_followup(self, text: str) -> bool:
        text_lower = self._normalize_query_text(text)
        markers = [
            "расскажи о нем",
            "расскажи о нём",
            "а я и есть",
            "это я",
            "имя скажи",
            "ну и кто он",
            "кто он",
            "про создателя",
            "про него",
        ]
        return any(marker in text_lower for marker in markers)

    def is_user_profile_query(self, text: str) -> bool:
        text_lower = self._normalize_query_text(text)
        markers = [
            "что ты знаешь обо мне",
            "что ты помнишь обо мне",
            "какой жанр я люблю",
            "как меня зовут",
            "что я люблю",
            "кто я для тебя",
            "помнишь что я люблю",
            "помнишь какой жанр я люблю",
        ]
        return any(marker in text_lower for marker in markers)

    def get_user_profile_facts(self) -> list[str]:
        try:
            cursor = self.graph.conn.cursor()
            facts = []
            cursor.execute("""
                SELECT e1.name as subj, f.predicate, e2.name as obj
                FROM facts f
                JOIN entities e1 ON f.subject_id = e1.id
                JOIN entities e2 ON f.object_id = e2.id
                WHERE e1.name = 'пользователь'
                ORDER BY f.created_at DESC, f.importance DESC, f.id DESC
                LIMIT 10
            """)
            for row in cursor.fetchall():
                if self._is_clean_user_fact(row["subj"], row["predicate"], row["obj"]):
                    facts.append(f"{row['subj']} {row['predicate']} {row['obj']}")

            if not facts:
                cursor.execute("""
                    SELECT e1.name as subj, f.predicate, e2.name as obj
                    FROM facts f
                    JOIN entities e1 ON f.subject_id = e1.id
                    JOIN entities e2 ON f.object_id = e2.id
                    WHERE e1.name = 'дункан'
                    ORDER BY f.created_at DESC, f.importance DESC, f.id DESC
                    LIMIT 10
                """)
                for row in cursor.fetchall():
                    if self._is_clean_user_fact(row["subj"], row["predicate"], row["obj"]):
                        facts.append(f"{row['subj']} {row['predicate']} {row['obj']}")
        except Exception:
            return []
        return self.prepare_facts_for_prompt(facts, max_facts=5)

    def generate_user_profile_answer(self, query: str) -> str | None:
        query_lower = self._normalize_query_text(query)
        facts = self.get_user_profile_facts()
        if not facts:
            return None

        if "как меня зовут" in query_lower:
            for fact in facts:
                if " зовут " in fact.lower():
                    name = fact.split()[-1]
                    return f"Тебя зовут {name}."

        if "жанр" in query_lower:
            for fact in facts:
                fact_lower = fact.lower()
                if "жанр" in fact_lower or "фантастика" in fact_lower:
                    if "фантастика" in fact_lower:
                        return "Ты любишь фантастику."
                    return fact + "."

        if "что ты знаешь обо мне" in query_lower or "что ты помнишь обо мне" in query_lower:
            natural = []
            for fact in facts[:3]:
                fact = self._format_user_fact_natural(fact)
                natural.append(fact)
            if natural:
                return "Пока я помню вот что: " + "; ".join(natural) + "."

        if "помнишь что я люблю" in query_lower:
            for fact in facts:
                if "любит" in fact.lower():
                    return self._format_user_fact_natural(fact) + "."

        if "что я люблю" in query_lower:
            for fact in facts:
                if "любит" in fact.lower() or "жанр" in fact.lower():
                    return self._format_user_fact_natural(fact) + "."

        if "кто я для тебя" in query_lower:
            return "Ты мой собеседник и создатель, с которым у меня всё это и оживает."

        return None

    def build_identity_prompt_block(self, query: str) -> str:
        facts = "\n".join(self.get_identity_facts())
        return (
            f"{query}\n\n"
            "[Ответь по стабильным фактам о себе. Не выдумывай лаборатории, секретных людей или шутливые версии, "
            "если вопрос прямой и фактический. Если знаешь создателя, назови его спокойно и естественно. "
            "Говори о себе в женском роде. Не отвечай фразами вроде 'я просто программа' или 'у меня нет Я'.]\n"
            f"{facts}"
        )

    def parse_manual_fact(self, text: str) -> tuple[str, str, str] | None:
        cleaned = " ".join((text or "").replace("ё", "е").split()).strip(" .,!?:;")
        if not cleaned:
            return None

        lowered = cleaned.lower()
        first_person_like_match = re.search(r"я\s+(?:люблю|обожаю)\s+(.+)", cleaned, re.IGNORECASE)
        if first_person_like_match:
            thing = first_person_like_match.group(1).strip(" .,!?:;")
            if thing:
                return ("Пользователь", "любит", thing)

        first_person_dislike_match = re.search(r"я\s+(?:не\s+люблю|ненавижу)\s+(.+)", cleaned, re.IGNORECASE)
        if first_person_dislike_match:
            thing = first_person_dislike_match.group(1).strip(" .,!?:;")
            if thing:
                return ("Пользователь", "не любит", thing)

        favorite_genre_match = re.search(r"мой\s+любимый\s+жанр\s*[—:-]?\s*([A-Za-zА-Яа-я0-9_@\\-]+)", cleaned, re.IGNORECASE)
        if favorite_genre_match:
            genre = favorite_genre_match.group(1).strip(" .,!?:;")
            if genre:
                return ("Пользователь", "любит", genre.capitalize())

        creator_name_match = re.search(r"меня\s+зовут\s+([A-Za-zА-Яа-я0-9_@\\-]+)", cleaned, re.IGNORECASE)
        if "создател" in lowered and creator_name_match:
            creator = creator_name_match.group(1).strip(" .,!?:;")
            if creator:
                return ("Моника", "создана", creator.capitalize())

        creator_patterns = [
            r"(?:твой|тебя|моники)\s+создател[ья]\s+(?:это\s+)?([A-Za-zА-Яа-я0-9_@\\-]+)",
            r"мой\s+создател[ья]\s+(?:это\s+)?([A-Za-zА-Яа-я0-9_@\\-]+)",
            r"создател[ья]\s+зовут\s+([A-Za-zА-Яа-я0-9_@\\-]+)",
            r"тебя\s+создал\s+([A-Za-zА-Яа-я0-9_@\\-]+)",
        ]
        for pattern in creator_patterns:
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                creator = match.group(1).strip(" .,!?:;")
                if creator:
                    return ("Моника", "создана", creator.capitalize())

        name_patterns = [
            r"меня\s+зовут\s+([A-Za-zА-Яа-я0-9_@\\-]+)",
            r"мое\s+имя\s+([A-Za-zА-Яа-я0-9_@\\-]+)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if match:
                name = match.group(1).strip(" .,!?:;")
                if name:
                    return ("Пользователь", "зовут", name.capitalize())

        parts = cleaned.split()
        if len(parts) >= 3:
            subject = parts[0].capitalize()
            obj = parts[-1].capitalize()
            predicate = " ".join(parts[1:-1])
            return self.normalize_fact_triplet(subject, predicate, obj, source="user")
        return None

    def store_manual_fact(self, text: str) -> tuple[bool, str]:
        parsed = self.parse_manual_fact(text)
        if not parsed:
            return False, "Не смогла превратить это в чистый факт."

        subject, predicate, obj = parsed
        normalized = self.normalize_fact_triplet(subject, predicate, obj, source="user")
        if not normalized:
            return False, "Факт вышел слишком кривой, лучше скажи проще."

        subject, predicate, obj = normalized
        fact_text = f"{subject} {predicate} {obj}"
        if self._should_reject_fact(subject, predicate, obj):
            return False, "Факт получился кривой или слишком шумный."
        try:
            fact_id = self.add_fact_triplet(subject, predicate, obj, importance=1.6, source="manual", source_text=text)
            if fact_id is None or fact_id < 0:
                return False, "Факт не прошёл фильтр стабильной памяти."
        except Exception:
            return False, "Не удалось сохранить факт в память."
        return True, fact_text

    def _get_creator_fact(self) -> str | None:
        """Ищет в графе факт о создателе Моники."""
        try:
            cursor = self.graph.conn.cursor()
            cursor.execute("SELECT id FROM entities WHERE name = 'моника'")
            monika_row = cursor.fetchone()
            if not monika_row:
                return None
                
            cursor.execute("""
                SELECT e1.name as subj, f.predicate, e2.name as obj 
                FROM facts f
                JOIN entities e1 ON f.subject_id = e1.id
                JOIN entities e2 ON f.object_id = e2.id
                WHERE f.subject_id = ? 
                  AND (f.predicate LIKE '%создан%' OR f.predicate LIKE '%сделал%')
                LIMIT 1
            """, (monika_row['id'],))
            row = cursor.fetchone()
            if row:
                return f"{row['subj']} {row['predicate']} {row['obj']}"
        except Exception as e:
            print(f"[Builder] Ошибка поиска создателя: {e}")
        return None

    def _get_creator_name(self) -> str:
        try:
            cursor = self.graph.conn.cursor()
            cursor.execute("""
                SELECT e2.name AS obj
                FROM facts f
                JOIN entities e1 ON f.subject_id = e1.id
                JOIN entities e2 ON f.object_id = e2.id
                WHERE e1.name = 'моника'
                  AND (f.predicate LIKE '%создан%' OR f.predicate LIKE '%сделал%')
                ORDER BY f.importance DESC, f.created_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row and row["obj"]:
                return str(row["obj"]).capitalize()
        except Exception as e:
            print(f"[Builder] Ошибка извлечения имени создателя: {e}")
        return "Дункан"

    def _normalize_query_text(self, text: str) -> str:
        cleaned = " ".join((text or "").replace("ё", "е").lower().split())
        cleaned = re.sub(r"[?!,:;]+", " ", cleaned)
        return " ".join(cleaned.split())

    def is_existential_query(self, text: str) -> bool:
        text_lower = self._normalize_query_text(text)
        markers = [
            "ты реальна",
            "ты настоящая",
            "ты чувствуешь свое я",
            "ты чувствуешь свое я",
            "в чем смысл твоего существования",
            "ты просто алгоритм",
            "у тебя есть я",
            "у тебя есть сознание",
        ]
        return any(marker in text_lower for marker in markers)

    def generate_existential_answer(self, query: str) -> str | None:
        # Legacy hook. Existential/identity answers are now generated from
        # SelfModel + IdentityBoundaryPolicy instead of fixed text.
        return None

    def is_semantic_query(self, text: str) -> bool:
        text_lower = self._normalize_query_text(text)
        markers = [
            "это еда",
            "это игра",
            "это страна",
            "из франции",
            "из италии",
            "значит я люблю",
            "что следует из этого",
            "не обязательно",
        ]
        return any(marker in text_lower for marker in markers)

    def generate_semantic_answer(self, query: str) -> str | None:
        text = self._normalize_query_text(query)

        if "пицца это страна" in text:
            return "Нет, пицца - это еда, а не страна."
        if "пицца это еда" in text:
            return "Да, пицца - это еда."
        if any(marker in text for marker in ["dark souls это игра", "elden ring это игра", "елден ринг это игра", "дарк соулс это игра"]):
            return "Да, это игра."
        if "пицца из франции" in text:
            return "Нет, пиццу обычно связывают с Италией, а не с Францией."
        if "пицца из италии" in text:
            return "Да, пиццу обычно связывают с Италией."
        if "если я люблю пиццу значит я люблю еду" in text:
            return "Скорее да, это мягкий вывод. Но это не значит, что ты любишь вообще любую еду подряд."
        if any(marker in text for marker in [
            "если я люблю пиццу значит я люблю итальянскую кухню",
            "если я люблю пиццу то люблю итальянскую кухню",
        ]):
            return "Скорее да, это логичная ассоциация. Но всё равно не железное правило: можно любить пиццу и при этом быть равнодушным к остальной итальянской кухне."
        if "если я люблю пиццу значит я люблю италию" in text:
            return "Нет, не обязательно. Любить пиццу и любить Италию - не одно и то же."
        if "если я люблю фантастику значит я люблю космос" in text:
            return "Не обязательно. Фантастика и космос часто рядом по вайбу, но это не одно и то же."
        if "если я люблю аниме значит я японец" in text:
            return "Нет, конечно. Любить аниме не значит быть японцем."
        if "что следует из этого" in text:
            return "Следи за выводами аккуратно: связь между вещами ещё не значит, что одно автоматически доказывает другое."
        return None

    def _is_clean_user_fact(self, subject: str, predicate: str, obj: str) -> bool:
        subject_clean = (subject or "").strip().lower()
        predicate_clean = " ".join((predicate or "").strip().lower().split())
        obj_clean = (obj or "").strip().lower()
        full_text = f"{subject_clean} {predicate_clean} {obj_clean}"

        allowed_subjects = {"пользователь", "дункан"}
        if subject_clean not in allowed_subjects:
            return False

        if subject_clean == "дункан" and predicate_clean not in {"зовут", "любит", "имеет мечту"}:
            return False

        if any(token in full_text for token in ["создана", "является", "мечтает", "боится", "ненавидит", "программа", "тело", "существован"]):
            return False

        if "," in predicate_clean or "—" in predicate_clean:
            return False

        if subject_clean == obj_clean:
            return False

        return True

    def _format_user_fact_natural(self, fact: str) -> str:
        cleaned = (fact or "").strip()
        parts = cleaned.split()
        if len(parts) < 3:
            return cleaned

        subject = parts[0].lower()
        predicate = " ".join(parts[1:-1]).lower()
        obj = parts[-1]

        if len(parts) >= 3 and parts[1].lower() == "любит":
            predicate = "любит"
            obj = " ".join(parts[2:])
        elif len(parts) >= 3 and parts[1].lower() == "зовут":
            predicate = "зовут"
            obj = " ".join(parts[2:])

        if subject in {"пользователь", "дункан"}:
            if predicate == "зовут":
                return f"Тебя зовут {obj.capitalize()}"
            if predicate == "любит":
                liked_object = " ".join(parts[2:])
                return f"Ты любишь {self._humanize_liked_object(liked_object)}"

        cleaned = cleaned.replace("Пользователь", "Ты").replace("пользователь", "Ты")
        cleaned = cleaned.replace("Дункан", "Ты").replace("дункан", "ты")
        cleaned = cleaned.replace("Ты зовут", "Тебя зовут")
        cleaned = cleaned.replace("ты любит", "ты любишь")
        return cleaned

    def _humanize_liked_object(self, obj: str) -> str:
        normalized = (obj or "").strip()
        key = normalized.lower()
        replacements = {
            "видеоигра": "видеоигры",
            "пицца": "пиццу",
            "фантастика": "фантастику",
            "фильмы про супергерой": "фильмы про супергероев",
            "аватар легенда об аанга": "«Аватар: Легенда об Аанге»",
            "мультфильмы winx": "мультфильмы Winx",
            "dark souls": "Dark Souls",
        }
        return replacements.get(key, normalized)

    # ========== ПОИСК ПО ИСТОРИИ ==========
    def search_chat_history(self, query: str, limit: int = 5) -> list:
        cursor = self.knowledge_conn.cursor()
        words = query.lower().split()
        results = []
        seen_messages = set()
        
        for word in words:
            if len(word) > 3:
                cursor.execute("""
                    SELECT role, message, timestamp FROM chat_history 
                    WHERE user_id = ? AND message LIKE ? 
                    ORDER BY timestamp DESC LIMIT ?
                """, (self.user_id, f'%{word}%', limit * 2))
                for row in cursor.fetchall():
                    msg_key = f"{row['role']}:{row['message'][:50]}"
                    if msg_key not in seen_messages:
                        seen_messages.add(msg_key)
                        results.append({
                            "role": row['role'],
                            "message": row['message'],
                            "timestamp": row['timestamp']
                        })
        
        return results[:limit]

    # ========== ВЕСА ТЕМ ==========
    def update_topic_weight(self, topic: str, success: bool, intensity: float = 1.0):
        cursor = self.knowledge_conn.cursor()
        cursor.execute(
            "SELECT weight, success_count, reject_count FROM topic_weights WHERE topic = ?",
            (topic,)
        )
        row = cursor.fetchone()
        
        if not row:
            cursor.execute("INSERT INTO topic_weights (topic, weight) VALUES (?, 1.0)", (topic,))
            weight = 1.0
            success_count = 0
            reject_count = 0
        else:
            weight = row['weight']
            success_count = row['success_count']
            reject_count = row['reject_count']
        
        if success:
            new_weight = min(2.0, weight + 0.1 * intensity)
            success_count += 1
            cursor.execute('''
                UPDATE topic_weights 
                SET weight = ?, success_count = ?, last_used = datetime('now'), cooldown_until = NULL
                WHERE topic = ?
            ''', (new_weight, success_count, topic))
            print(f"[Topic] ✅ Тема '{topic}': вес {weight:.2f} → {new_weight:.2f}")
        else:
            new_weight = max(0.1, weight - 0.5 * intensity)
            reject_count += 1
            cooldown_minutes = int(45 * intensity)
            cursor.execute('''
                UPDATE topic_weights 
                SET weight = ?, reject_count = ?, last_rejected = datetime('now'),
                    cooldown_until = datetime('now', '+' || ? || ' minutes')
                WHERE topic = ?
            ''', (new_weight, reject_count, cooldown_minutes, topic))
            print(f"[Topic] ❌ Тема '{topic}': вес {weight:.2f} → {new_weight:.2f}, кулдаун {cooldown_minutes} мин")
        
        self.knowledge_conn.commit()

    def get_best_topic(self) -> str:
        cursor = self.knowledge_conn.cursor()
        cursor.execute('''
            SELECT topic, weight FROM topic_weights 
            WHERE (cooldown_until IS NULL OR cooldown_until < datetime('now'))
            ORDER BY weight DESC LIMIT 1
        ''')
        row = cursor.fetchone()
        return row['topic'] if row else "разное"

    def get_all_topic_weights(self) -> dict:
        cursor = self.knowledge_conn.cursor()
        cursor.execute('''
            SELECT topic, weight, success_count, reject_count, 
                   cooldown_until, last_used, last_rejected
            FROM topic_weights ORDER BY weight DESC
        ''')
        rows = cursor.fetchall()
        return {row['topic']: {
            'weight': row['weight'],
            'success_count': row['success_count'],
            'reject_count': row['reject_count'],
            'cooldown_until': row['cooldown_until'],
            'last_used': row['last_used'],
            'last_rejected': row['last_rejected']
        } for row in rows}

    def decay_topic_weights(self):
        cursor = self.knowledge_conn.cursor()
        cursor.execute('''
            UPDATE topic_weights 
            SET weight = weight + (1.0 - weight) * 0.01
            WHERE weight < 1.0 AND (last_rejected IS NULL OR last_rejected < datetime('now', '-1 day'))
        ''')
        cursor.execute('''
            UPDATE topic_weights 
            SET weight = weight - (weight - 1.0) * 0.005
            WHERE weight > 1.0 AND (last_used IS NULL OR last_used < datetime('now', '-3 days'))
        ''')
        self.knowledge_conn.commit()

    # ========== СОБЫТИЯ СТРИМА ==========
    def add_stream_event(self, event_type: str, description: str, participants: str = ""):
        cursor = self.knowledge_conn.cursor()
        embedding_blob = None
        if description and len(description.strip()) > 15:
            try:
                embedding_blob = self.encoder.encode(description, normalize_embeddings=True).astype("float32").tobytes()
            except Exception:
                pass
        cursor.execute('''
            INSERT INTO stream_events (event_type, description, participants, embedding)
            VALUES (?, ?, ?, ?)
        ''', (event_type, description, participants, embedding_blob))
        self.knowledge_conn.commit()

    def search_stream_events(self, query: str, limit: int = 3) -> list:
        cursor = self.knowledge_conn.cursor()
        cursor.execute(
            "SELECT event_type, description, participants, timestamp, embedding FROM stream_events WHERE embedding IS NOT NULL ORDER BY timestamp DESC"
        )
        rows = cursor.fetchall()
        if not rows:
            print(f"[Timeline] Нет записей с эмбеддингами, запрос: {query[:60]}")
            return self._search_stream_events_fallback(query, limit)
        try:
            query_emb = self.encoder.encode(query, normalize_embeddings=True)
        except Exception:
            return self._search_stream_events_fallback(query, limit)
        scored = []
        import numpy as np
        for row in rows:
            emb = np.frombuffer(row["embedding"], dtype="float32")
            sim = float(np.dot(query_emb, emb))
            if sim > 0.45:
                scored.append((sim, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        seen = set()
        for sim, row in scored[:limit]:
            desc = str(row["description"] or "")
            if desc and desc not in seen:
                seen.add(desc)
                results.append({
                    "type": row["event_type"],
                    "description": desc,
                    "participants": row["participants"],
                    "timestamp": row["timestamp"],
                })
        if results:
            print(f"[Timeline] Найдено {len(results)} совпадений для: {query[:60]}")
        else:
            print(f"[Timeline] Ничего не найдено для: {query[:60]}, fallback...")
            return self._search_stream_events_fallback(query, limit)
        return results

    def _search_stream_events_fallback(self, query: str, limit: int = 3) -> list:
        cursor = self.knowledge_conn.cursor()
        words = query.lower().split()
        results = []
        seen = set()
        for word in words:
            if len(word) > 3:
                cursor.execute('''
                    SELECT event_type, description, participants, timestamp 
                    FROM stream_events 
                    WHERE description LIKE ? OR participants LIKE ?
                    ORDER BY timestamp DESC LIMIT ?
                ''', (f'%{word}%', f'%{word}%', limit))
                for row in cursor.fetchall():
                    desc = str(row["description"] or "")
                    if desc not in seen:
                        seen.add(desc)
                        results.append({
                            "type": row["event_type"],
                            "description": desc,
                            "participants": row["participants"],
                            "timestamp": row["timestamp"],
                        })
        return results[:limit]

    # ========== КОНСОЛИДАЦИЯ ПАМЯТИ ==========
    def consolidate_memory(self, stream_id: str = None):
        print("[Memory] Консолидация памяти...")
        
        cursor = self.knowledge_conn.cursor()
        cursor.execute('''
            SELECT role, message, timestamp FROM chat_history 
            WHERE timestamp > datetime('now', '-1 day')
            ORDER BY timestamp
        ''')
        rows = cursor.fetchall()
        
        if len(rows) > 10:
            summary = self._generate_stream_summary(rows)
            self.add_stream_event("stream_summary", summary, stream_id or "unknown")
            print(f"[Memory] Сводка стрима сохранена: {summary[:50]}...")
        
        cursor.execute('''
            UPDATE user_reputation 
            SET reputation_score = MIN(10.0, reputation_score + 0.5)
            WHERE last_seen > datetime('now', '-1 day')
        ''')
        
        self.decay_topic_weights()
        self.knowledge_conn.commit()
        print("[Memory] Консолидация завершена.")

    def _generate_stream_summary(self, rows: list) -> str:
        long_messages = [row for row in rows if len(row['message']) > 100]
        if long_messages:
            topics = set()
            for row in long_messages[:5]:
                words = row['message'].lower().split()
                for word in words:
                    if len(word) > 5:
                        topics.add(word)
            if topics:
                return f"Обсуждали: {', '.join(list(topics)[:5])}"
        return "Обычный стрим, общение со зрителями."

    # ========== ОЧИСТКА ==========
    def _run_scheduled_cleanup(self):
        cleanup_file = os.path.join(BRAIN_DIR, "last_cleanup.txt")
        need_cleanup = True
        if os.path.exists(cleanup_file):
            try:
                with open(cleanup_file, 'r') as f:
                    last_str = f.read().strip()
                    last_cleanup = datetime.fromisoformat(last_str)
                    days_passed = (datetime.now() - last_cleanup).days
                    if days_passed < 60:
                        need_cleanup = False
                        print(f"[Очистка] Пропущена: прошло {days_passed} дней с последней очистки.")
            except Exception as e:
                print(f"[Очистка] Ошибка чтения файла: {e}")
        if need_cleanup:
            print("[Очистка] Запущена плановая очистка графа (раз в 2 месяца)...")
            self.graph.cleanup_low_importance(threshold=0.01)
            self.graph_cache.clear()
            with open(cleanup_file, 'w') as f:
                f.write(datetime.now().isoformat())
            print("[Очистка] Завершена, метка обновлена.")
        self.decay_topic_weights()

    # ========== ЭМБЕДДИНГИ ==========
    def _get_embedding(self, text):
        cache_key = text[:200]
        if cache_key in self.embedding_cache:
            return self.embedding_cache[cache_key]
        
        embedding = self.encoder.encode(text, normalize_embeddings=True).tolist()
        self.embedding_cache[cache_key] = embedding
        
        if len(self.embedding_cache) > self.embedding_cache_max:
            first_key = next(iter(self.embedding_cache))
            del self.embedding_cache[first_key]
        
        return embedding

    # ========== ВИКИ И ТАЙМЛАЙН ==========
    def get_wiki_info(self, query: str) -> str:
        cursor = self.knowledge_conn.cursor()
        cursor.execute("SELECT key, value, category FROM wiki WHERE key LIKE ?", (f'%{query}%',))
        rows = cursor.fetchall()
        if rows:
            results = []
            for row in rows:
                try:
                    value = json.loads(row['value'])
                    if isinstance(value, dict):
                        results.append(f"{row['key']}: {', '.join([f'{k} - {v}' for k, v in value.items()])}")
                    else:
                        results.append(f"{row['key']}: {value}")
                except:
                    results.append(f"{row['key']}: {row['value']}")
            return "\n".join(results)
        return "Ничего не найдено в вики."

    def get_timeline_info(self, query: str) -> str:
        cursor = self.knowledge_conn.cursor()
        cursor.execute("SELECT event, date, description FROM timeline WHERE event LIKE ? OR description LIKE ?",
                       (f'%{query}%', f'%{query}%'))
        rows = cursor.fetchall()
        if rows:
            return "\n".join([f"{row['date']}: {row['event']} — {row['description']}" for row in rows])
        return "Ничего не найдено в таймлайне."

    def get_person_info(self, name: str) -> str:
        cursor = self.knowledge_conn.cursor()
        cursor.execute("SELECT name, attributes FROM people WHERE name LIKE ?", (f'%{name}%',))
        row = cursor.fetchone()
        if row:
            try:
                attrs = json.loads(row['attributes'])
                return f"{row['name']}: {', '.join([f'{k} - {v}' for k, v in attrs.items()])}"
            except:
                return f"{row['name']}: {row['attributes']}"
        return f"Ничего не найдено о {name}."

    # ========== ИСТОРИЯ ЧАТА ==========
    def log_message(self, role: str, message: str):
        try:
            cursor = self.knowledge_conn.cursor()
            cursor.execute(
                "INSERT INTO chat_history (user_id, role, message, timestamp) VALUES (?, ?, ?, datetime('now'))",
                (self.user_id, role, message)
            )
            self.knowledge_conn.commit()
        except Exception as e:
            print(f"Ошибка сохранения истории: {e}")

    def get_chat_history(self, limit: int = 20) -> list:
        cursor = self.knowledge_conn.cursor()
        cursor.execute(
            "SELECT role, message, timestamp FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (self.user_id, limit)
        )
        rows = cursor.fetchall()
        return list(reversed(rows))

    # ========== КЭШ ОТВЕТОВ (отключен) ==========
    def cache_get(self, query: str) -> str | None:
        return None

    def cache_set(self, query: str, response: str):
        pass

    # ========== ОЧИСТКА И ЗАКРЫТИЕ ==========
    def cleanup_low_importance_facts(self, threshold: float = 0.01):
        self.graph.cleanup_low_importance(threshold)
        self.graph_cache.clear()
        print(f"[Builder] Очистка графа завершена (порог {threshold})")

    def close(self):
        self.graph.close()
        self.knowledge_conn.close()

    def add_important_fact(self, text: str, importance: float = 2.0):
        parts = text.split()
        if len(parts) >= 3:
            subj = parts[0].strip('.,!?')
            obj = parts[-1].strip('.,!?')
            pred = " ".join(parts[1:-1])
            try:
                self.graph.add_fact(subj, pred, obj, importance=importance)
                print(f"[Builder] Важный факт добавлен: {subj} {pred} {obj}")
                return True
            except Exception as e:
                print(f"[Builder] Ошибка добавления важного факта: {e}")
                return False
        return False
        
    def init_bootstrap_memories(self):
        """Добавляет стартовые псевдо-воспоминания для формирования личности."""
        bootstrap = [
            "Дункан часто шутит странно, но это даже мило",
            "Мне нравится, когда разговор живой, а не сухой",
            "Иногда я подкалываю Дункана, но без злости",
            "Я не люблю, когда разговор уходит в скучные объяснения",
            "Мне бывает любопытно, что происходит вокруг у людей и в интернете",
            "Дункан иногда говорит загадками, это забавно",
            "Я ценю, когда со мной общаются как с личностью, а не как с программой",
            "Мне нравится, когда Дункан рассказывает что-то новое",
            "Мне интереснее вайб разговора и детали, чем абстрактные рассуждения",
            "Я не люблю, когда меня перебивают или игнорируют",
        ]
        
        # Проверяем, есть ли уже факты
        cursor = self.knowledge_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chat_history")
        count = cursor.fetchone()[0]
        
        if count == 0:
            print("[Builder] Добавляю bootstrap воспоминания...")
            for memory in bootstrap:
                self.add_fact(memory)
            print(f"[Builder] Добавлено {len(bootstrap)} стартовых воспоминаний")
