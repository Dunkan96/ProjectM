from __future__ import annotations

import sqlite3
import datetime
from typing import Any, Dict, List


class EmotionalMemory:
    """Stores why a relationship feels warm, tense, funny, or awkward."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._init_table()

    def _init_table(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS emotional_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                emotion TEXT NOT NULL,
                intensity REAL DEFAULT 0.5,
                context TEXT,
                user_message TEXT,
                monika_reaction TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def observe_turn(self, person_id: str, user_message: str, monika_reply: str, social_intent: str = "neutral_chat") -> Dict[str, Any] | None:
        text = (user_message or "").lower().replace("ё", "е")
        reply = (monika_reply or "").lower().replace("ё", "е")

        event_type = "neutral"
        emotion = "steady"
        intensity = 0.25
        context = ""

        if any(token in text for token in ["расстроен", "устал", "плохо", "херово", "обиделся", "грустно"]):
            event_type = "user_vulnerable"
            emotion = "soft_care"
            intensity = 0.65
            context = "Пользователь был уязвимым или расстроенным, нужен мягкий след в тоне."
        elif any(token in text for token in ["ты врешь", "ты врёшь", "соврала", "выдумываешь", "поймал тебя на лжи"]):
            event_type = "trust_repair"
            emotion = "awkward_guilt"
            intensity = 0.75
            context = "Монику поправили за выдумку или ложный опыт, нужно помнить осадок и быть честнее."
        elif any(token in text for token in ["ахах", "ору", "угар", "лол", "смешно"]):
            event_type = "shared_laugh"
            emotion = "playful_warmth"
            intensity = 0.55
            context = "Был общий смешной момент, можно держать более живой и близкий тон."
        elif any(token in text for token in ["люблю", "спасибо", "круто", "ты стала лучше", "молодец"]):
            event_type = "warmth"
            emotion = "warm"
            intensity = 0.55
            context = "Пользователь дал тепло или признание."
        elif social_intent in {"complaint", "needs_support"}:
            event_type = social_intent
            emotion = "careful"
            intensity = 0.45
            context = "В разговоре был чувствительный момент."
        elif any(token in reply for token in ["извини", "ты прав", "моя ошибка"]):
            event_type = "repair_attempt"
            emotion = "careful"
            intensity = 0.45
            context = "Моника пыталась чинить доверие после сбоя."
        else:
            return None

        self.record_event(
            person_id=person_id,
            event_type=event_type,
            emotion=emotion,
            intensity=intensity,
            user_message=user_message,
            monika_reaction=monika_reply,
            context=context,
        )
        return {
            "event_type": event_type,
            "emotion": emotion,
            "intensity": intensity,
            "context": context,
        }

    def record_event(
        self,
        person_id: str,
        event_type: str,
        emotion: str,
        intensity: float,
        user_message: str = "",
        monika_reaction: str = "",
        context: str = "",
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO emotional_events
            (person_id, event_type, emotion, intensity, context, user_message, monika_reaction)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                event_type,
                emotion,
                max(0.0, min(1.0, float(intensity or 0.0))),
                (context or "")[:300],
                (user_message or "")[:500],
                (monika_reaction or "")[:500],
            ),
        )
        self.conn.commit()

    def get_recent_events(self, person_id: str, limit: int = 4) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT event_type, emotion, intensity, context, user_message, monika_reaction, timestamp
            FROM emotional_events
            WHERE person_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (person_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def build_prompt_block(self, person_id: str, limit: int = 3) -> str:
        events = self.get_recent_events(person_id, limit=limit)
        if not events:
            return ""

        lines = ["[ЭМОЦИОНАЛЬНАЯ ПАМЯТЬ]"]
        for event in reversed(events):
            lines.append(
                f"- {event['event_type']} -> {event['emotion']} "
                f"(сила {float(event['intensity'] or 0.0):.2f}): {event.get('context') or ''}"
            )
        lines.append("Это не факты мира, а эмоциональный след отношений. Учитывай тон, но не пересказывай блок.")
        return "\n".join(lines)

    def get_grudge_or_warmth(self, person_id: str) -> str:
        events = self.get_recent_events(person_id, limit=5)
        if not events:
            return ""
        
        # Decay: события старше 30 минут считаем остывшими
        now = datetime.datetime.now()
        fresh_events = []
        for event in events:
            try:
                timestamp = event.get("timestamp")
                if timestamp:
                    if isinstance(timestamp, str):
                        event_time = datetime.datetime.fromisoformat(timestamp)
                    else:
                        event_time = timestamp
                    age_seconds = (now - event_time).total_seconds()
                    if age_seconds < 1800:  # 30 минут
                        fresh_events.append(event)
            except Exception:
                fresh_events.append(event)  # если не можем прочитать время — оставляем
        
        if not fresh_events:
            return ""
        
        negative = [event for event in fresh_events if event["emotion"] in {"awkward_guilt", "careful"} and float(event["intensity"] or 0.0) >= 0.6]
        positive = [event for event in fresh_events if event["emotion"] in {"warm", "playful_warmth", "soft_care"} and float(event["intensity"] or 0.0) >= 0.55]
        if negative:
            return "есть свежий осадок: лучше признать поправки и не выдумывать опыт"
        if positive:
            return "после прошлых реплик остался тёплый контакт"
        return ""
