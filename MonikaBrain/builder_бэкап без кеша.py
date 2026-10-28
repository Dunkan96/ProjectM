# builder.py
import time
import json
import sqlite3
import chromadb
import os
import requests
from datetime import datetime, timedelta
from sentence_transformers import SentenceTransformer
from graph_engine import GraphEngine
from config import BRAIN_DIR

class Builder:
    def __init__(self, user_id="dunkanlive"):
        self.user_id = user_id
        
        MODEL_PATH = r"F:\МоnikaVtuber\.cache\huggingface\hub\models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2\snapshots\e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
        self.encoder = SentenceTransformer(MODEL_PATH)
        
        self.graph = GraphEngine()
        
        # Engram API
        self.engram_url = "http://localhost:3838"
        self.engram_available = False
        self._init_engram()
        
        self.client = chromadb.PersistentClient(path="./chroma_engram")
        self.cache_collection = self.client.get_or_create_collection(
            "response_cache",
            metadata={"hnsw:space": "cosine"}
        )
        self.cache_threshold = 0.9

        self.knowledge_conn = sqlite3.connect('knowledge.db', check_same_thread=False)
        self.knowledge_conn.row_factory = sqlite3.Row
        self._init_chat_history()
        self._init_emotional_memory()
        self._init_topic_weights()
        self._init_stream_events()
        self._init_user_reputation()

        self._run_scheduled_cleanup()

    # ========== ENGRAM ==========
    def _init_engram(self):
        try:
            response = requests.get(f"{self.engram_url}/health", timeout=2)
            if response.status_code == 200:
                data = response.json()
                print(f"[Engram] Подключен к {self.engram_url} (v{data.get('version', 'unknown')})")
                self.engram_available = True
            else:
                print(f"[Engram] ⚠️ Сервис недоступен (статус {response.status_code})")
        except Exception as e:
            print(f"[Engram] ⚠️ Ошибка подключения: {e}")

    def _add_to_engram(self, text: str, metadata: dict = None):
        if not self.engram_available:
            return False
        try:
            payload = {
                "content": text,
                "metadata": metadata or {"source": "monika", "type": "fact"}
            }
            response = requests.post(
                f"{self.engram_url}/api/memories",
                json=payload,
                timeout=5
            )
            if response.status_code in [200, 201]:
                print(f"[Engram] ✅ Добавлено: {text[:50]}...")
                return True
            else:
                print(f"[Engram] Ошибка добавления: {response.status_code}")
        except Exception as e:
            print(f"[Engram] Ошибка добавления: {e}")
        return False

    def _search_engram(self, query: str, top_k: int = 5) -> list:
        if not self.engram_available:
            return []
        try:
            response = requests.post(
                f"{self.engram_url}/api/memories/search",
                json={"query": query, "limit": top_k},
                timeout=5
            )
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'application/json' not in content_type:
                    print(f"[Engram] Ошибка: ответ не JSON")
                    return []
                data = response.json()
                if data.get("success"):
                    results = []
                    for item in data.get("memories", []):
                        content = item.get("content", "")
                        if content:
                            results.append(content)
                    if results:
                        print(f"[Engram] 🔍 Найдено {len(results)} совпадений")
                    return results
            return []
        except Exception as e:
            print(f"[Engram] Ошибка поиска: {e}")
        return []

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
        """Таблица репутации зрителей."""
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
        """Обновляет репутацию пользователя при каждом сообщении."""
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
        """Возвращает уровень доверия пользователя."""
        cursor = self.knowledge_conn.cursor()
        cursor.execute(
            "SELECT authority_level, is_creator FROM user_reputation WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if not row:
            return 0
        return 100 if row['is_creator'] else row['authority_level']

    def is_creator(self, user_id: str) -> bool:
        """Проверяет, является ли пользователь создателем."""
        cursor = self.knowledge_conn.cursor()
        cursor.execute(
            "SELECT is_creator FROM user_reputation WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        return row and row['is_creator']

    def get_user_stats(self, user_id: str) -> dict:
        """Возвращает статистику пользователя."""
        cursor = self.knowledge_conn.cursor()
        cursor.execute(
            "SELECT * FROM user_reputation WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {}

    # ========== КОНСОЛИДАЦИЯ ПАМЯТИ (Memory Consolidation) ==========
    def consolidate_memory(self, stream_id: str = None):
        """Обрабатывает накопленные данные после стрима (сон)."""
        print("[Memory] Консолидация памяти...")
        
        # 1. Извлекаем ключевые события из chat_history за последние 24 часа
        cursor = self.knowledge_conn.cursor()
        cursor.execute('''
            SELECT role, message, timestamp FROM chat_history 
            WHERE timestamp > datetime('now', '-1 day')
            ORDER BY timestamp
        ''')
        rows = cursor.fetchall()
        
        if len(rows) > 10:
            # Анализируем диалог и создаём summary
            summary = self._generate_stream_summary(rows)
            self.add_stream_event("stream_summary", summary, stream_id or "unknown")
            print(f"[Memory] Сводка стрима сохранена: {summary[:50]}...")
        
        # 2. Повышаем репутацию активным зрителям
        cursor.execute('''
            UPDATE user_reputation 
            SET reputation_score = MIN(10.0, reputation_score + 0.5)
            WHERE last_seen > datetime('now', '-1 day')
        ''')
        
        # 3. Декай весов тем
        self.decay_topic_weights()
        
        self.knowledge_conn.commit()
        print("[Memory] Консолидация завершена.")

    def _generate_stream_summary(self, rows: list) -> str:
        """Генерирует краткую сводку стрима."""
        # Упрощённо: берём самые длинные сообщения как важные
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

    # ========== СОБЫТИЯ СТРИМА ==========
    def add_stream_event(self, event_type: str, description: str, participants: str = ""):
        cursor = self.knowledge_conn.cursor()
        cursor.execute('''
            INSERT INTO stream_events (event_type, description, participants)
            VALUES (?, ?, ?)
        ''', (event_type, description, participants))
        self.knowledge_conn.commit()
        print(f"[Memory] Событие сохранено: {event_type} — {description[:50]}...")

    def search_stream_events(self, query: str, limit: int = 3) -> list:
        cursor = self.knowledge_conn.cursor()
        words = query.lower().split()
        results = []
        for word in words:
            if len(word) > 3:
                cursor.execute('''
                    SELECT event_type, description, participants, timestamp 
                    FROM stream_events 
                    WHERE description LIKE ? OR participants LIKE ?
                    ORDER BY timestamp DESC LIMIT ?
                ''', (f'%{word}%', f'%{word}%', limit))
                for row in cursor.fetchall():
                    results.append({
                        "type": row['event_type'],
                        "description": row['description'],
                        "participants": row['participants'],
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
            with open(cleanup_file, 'w') as f:
                f.write(datetime.now().isoformat())
            print("[Очистка] Завершена, метка обновлена.")
        self.decay_topic_weights()

    # ========== ЭМБЕДДИНГИ ==========
    def _get_embedding(self, text):
        return self.encoder.encode(text, normalize_embeddings=True).tolist()

    # ========== ФАКТЫ ==========
    def add_fact(self, text: str) -> bool:
        if text.startswith("Моника сказала:"):
            subject = "Моника"
            predicate = "сказала"
            obj = text[len("Моника сказала:"):].strip()
            try:
                self.graph.add_fact(subject, predicate, obj)
                print(f"[Builder] Факт добавлен в граф: {subject} {predicate} {obj[:50]}...")
            except Exception as e:
                print(f"[Builder] Ошибка добавления факта (Моника): {e}")
                return False
        else:
            parts = text.split()
            if len(parts) >= 3:
                subject = parts[0].strip('.,!?')
                obj = parts[-1].strip('.,!?')
                predicate = " ".join(parts[1:-1])
                try:
                    self.graph.add_fact(subject, predicate, obj)
                    print(f"[Builder] Факт добавлен в граф: {subject} {predicate} {obj}")
                except Exception as e:
                    print(f"[Builder] Ошибка добавления факта: {e}")
                    return False
            else:
                try:
                    self.graph.add_fact("Факт", "состоит в том, что", text)
                    print(f"[Builder] Факт добавлен в граф (короткий): {text}")
                except Exception as e:
                    print(f"[Builder] Ошибка добавления короткого факта: {e}")
                    return False
        
        self._add_to_engram(text, {"type": "fact"})
        return True

    def search_facts(self, query: str, top_k: int = 5) -> list:
        facts = []
        if self.engram_available:
            engram_results = self._search_engram(query, top_k=top_k)
            facts.extend(engram_results)
        
        entities = []
        for word in query.split():
            clean = word.strip('.,!?;:')
            if len(clean) >= 2:
                normalized = self.graph.normalize_name(clean)
                entities.append(normalized)
        
        if entities:
            graph_facts = self.graph.get_facts_as_strings(entities, limit=top_k)
            for fact in graph_facts:
                if fact not in facts:
                    facts.append(fact)
        
        return facts[:top_k]

    def retrieve(self, query: str, top_k: int = 5) -> list:
        return self.search_facts(query, top_k)

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

    # ========== КЭШ ==========
    def cache_get(self, query: str) -> str | None:
        query_emb = self._get_embedding(query)
        results = self.cache_collection.query(
            query_embeddings=[query_emb],
            n_results=1,
            where={"user_id": self.user_id}
        )
        if results['distances'] and results['distances'][0]:
            distance = results['distances'][0][0]
            similarity = 1.0 - distance
            if similarity >= self.cache_threshold:
                response = results['documents'][0][0]
                print(f"[Кэш] Найден похожий запрос (сходство {similarity:.2f})")
                return response
        return None

    def cache_set(self, query: str, response: str):
        query_emb = self._get_embedding(query)
        doc_id = f"cache_{self.user_id}_{int(time.time()*1000)}_{hash(query) % 10000}"
        self.cache_collection.add(
            documents=[response],
            embeddings=[query_emb],
            ids=[doc_id],
            metadatas=[{"user_id": self.user_id, "query": query, "timestamp": time.time()}]
        )
        print(f"[Кэш] Сохранён ответ для запроса: {query[:50]}...")

    def cleanup_low_importance_facts(self, threshold: float = 0.01):
        self.graph.cleanup_low_importance(threshold)
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
                self._add_to_engram(text, {"type": "fact", "importance": importance})
                return True
            except Exception as e:
                print(f"[Builder] Ошибка добавления важного факта: {e}")
                return False
        return False