from __future__ import annotations

import time
from collections import deque
from typing import Any, Dict, Optional


class AnticipationEngine:
    """Tracks expected topics, surprises, and return-after-pause hooks."""

    def __init__(self):
        self.expected_topics: deque[Dict[str, Any]] = deque(maxlen=12)
        self.surprise_level = 0.0
        self.last_seen_by_person: Dict[str, float] = {}

    def observe_user_message(self, person_id: str, text: str, topic: str | None = None) -> Dict[str, Any]:
        now = time.time()
        previous_seen = self.last_seen_by_person.get(person_id)
        absence_seconds = (now - previous_seen) if previous_seen else 0.0
        self.last_seen_by_person[person_id] = now

        # Естественное затухание surprise_level со временем
        if absence_seconds > 0:
            decay_factor = max(0.0, 1.0 - absence_seconds / 120.0)  # полный сброс за ~2 минуты
            self.surprise_level = max(0.0, self.surprise_level * decay_factor)

        text_lower = (text or "").lower()
        expected = [item.get("topic") for item in self.expected_topics if item.get("topic")]
        matched = bool(topic and topic in expected) or any(str(item or "") in text_lower for item in expected)
        if expected and not matched and len(text_lower) > 12:
            self.surprise_level = min(1.0, self.surprise_level + 0.25)
        elif matched:
            self.surprise_level = max(0.0, self.surprise_level - 0.2)

        if topic:
            self.expected_topics.append({"topic": topic, "confidence": 0.45, "timestamp": now})

        return {
            "absence_seconds": round(absence_seconds, 2),
            "matched_expectation": matched,
            "expected_topics": expected[-3:],
            "surprise_level": round(self.surprise_level, 3),
        }

    def get_return_hook(self, role: str, absence_seconds: float) -> Optional[str]:
        if absence_seconds < 300:
            return None
        if role == "creator":
            if absence_seconds < 1800:
                return "Ты вернулся быстрее, чем я успела придумать обидную табличку ожидания."
            return "Ну наконец-то. Я уже почти начала делать вид, что мне всё равно."
        if absence_seconds < 1800:
            return "О, вернулся. Нормально, я ещё не успела заскучать окончательно."
        return "Давно тебя не было. Я уже думала, ты ушёл в легенды чата."

    def build_prompt_block(self) -> str:
        lines = []
        if self.surprise_level >= 0.65:
            lines.append("Ты немного удивлена поворотом разговора. Можно коротко отметить это, но не сбивать тему.")
        elif self.expected_topics:
            topic = self.expected_topics[-1].get("topic")
            if topic:
                lines.append(f"Ты ожидала продолжения темы «{topic}», но если пользователь свернул, следуй за ним.")
        return "\n".join(lines)

    def consume_surprise(self) -> float:
        value = self.surprise_level
        self.surprise_level = max(0.0, self.surprise_level * 0.35)
        return value
