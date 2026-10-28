from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional


class DialogueContinuity:
    """Stores coarse session continuity between launches."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._init_table()

    def _init_table(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dialogue_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL,
                session_start DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_end DATETIME,
                summary TEXT,
                key_topics TEXT,
                emotional_arc TEXT,
                last_message TEXT,
                monika_last_words TEXT
            )
            """
        )
        self.conn.commit()

    def start_session(self, person_id: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO dialogue_sessions (person_id) VALUES (?)", (person_id,))
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_session(self, session_id: int, messages: List[Dict[str, str]]) -> None:
        if not session_id or not messages:
            return
        summary, topics = self.generate_session_summary(messages)
        last_user = ""
        last_monika = ""
        for msg in reversed(messages):
            if not last_monika and msg.get("role") == "assistant":
                last_monika = msg.get("content", "")
            if not last_user and msg.get("role") == "user":
                last_user = msg.get("content", "")
            if last_user and last_monika:
                break
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE dialogue_sessions
            SET session_end = CURRENT_TIMESTAMP,
                summary = ?,
                key_topics = ?,
                last_message = ?,
                monika_last_words = ?
            WHERE id = ?
            """,
            (summary[:500], json.dumps(topics, ensure_ascii=False), last_user[:500], last_monika[:500], session_id),
        )
        self.conn.commit()

    def get_last_session_context(self, person_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT summary, key_topics, last_message, monika_last_words, session_start, session_end
            FROM dialogue_sessions
            WHERE person_id = ? AND summary IS NOT NULL
            ORDER BY session_start DESC, id DESC
            LIMIT 1
            """,
            (person_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "summary": row["summary"],
            "key_topics": json.loads(row["key_topics"] or "[]"),
            "last_message": row["last_message"],
            "monika_last_words": row["monika_last_words"],
            "session_start": row["session_start"],
            "session_end": row["session_end"],
        }

    def build_prompt_block(self, person_id: str) -> str:
        last = self.get_last_session_context(person_id)
        if not last:
            return ""
        lines = ["[МЕЖСЕССИОННАЯ НЕПРЕРЫВНОСТЬ]"]
        if last.get("summary"):
            lines.append(f"- Прошлый разговор: {last['summary']}")
        topics = last.get("key_topics") or []
        if topics:
            lines.append(f"- Последние темы: {', '.join(topics[:4])}")
        if last.get("last_message"):
            lines.append(f"- Последняя реплика пользователя: «{last['last_message'][:120]}»")
        lines.append("Используй это только если пользователь возвращается к прошлой линии. Не навязывай старую тему.")
        return "\n".join(lines)

    def generate_session_summary(self, messages: List[Dict[str, str]]) -> tuple[str, List[str]]:
        topic_hits: Dict[str, int] = {}
        vocabulary = {
            "пицца": ["пицц", "еда", "сыр", "соус"],
            "игры": ["игр", "cyberpunk", "dark souls", "elden ring", "босс"],
            "стрим": ["стрим", "чат", "донат", "зрител"],
            "личность": ["кто ты", "мама", "реальна", "создатель", "френдзон"],
            "настройка": ["код", "передел", "ошибка", "лог", "модель"],
            "мемы": ["мем", "кринж", "ахах", "ору"],
        }
        text = " ".join(msg.get("content", "") for msg in messages[-24:]).lower()
        for topic, markers in vocabulary.items():
            topic_hits[topic] = sum(1 for marker in markers if marker in text)
        topics = [topic for topic, score in sorted(topic_hits.items(), key=lambda item: item[1], reverse=True) if score > 0][:5]
        if topics:
            return "обсуждали " + ", ".join(topics[:4]), topics
        return "короткий живой разговор без устойчивой темы", []
