import logging
import math
import random
import time
from typing import Dict


class AffectionState:
    """Lightweight social state for a single user."""

    def __init__(self):
        self.value = 0.0
        self.trust = 0.0
        self.familiarity = 0.0

        self.mood = "neutral"  # irritated, warm, soft, neutral
        self.intensity = 0.0

        self.total_messages = 0
        self.last_interaction = time.time()
        self.decay_rate = 0.01

    def update(self, sentiment_score: float, event_type: str = "neutral"):
        """
        Update relationship state after a message.
        sentiment_score: [-1.0, +1.0]
        event_type: insult, praise, personal, neutral
        """
        self.total_messages += 1
        now = time.time()

        time_passed = max(0.0, now - self.last_interaction)
        safe_time_passed = min(time_passed, 3600.0)
        safe_decay_rate = max(0.0, float(self.decay_rate))

        try:
            decay_factor = math.exp(-safe_decay_rate * safe_time_passed)
        except OverflowError:
            logging.warning(
                "[Affection] Overflow in decay: last_interaction=%s now=%s decay_rate=%s",
                self.last_interaction,
                now,
                self.decay_rate,
            )
            decay_factor = 1.0

        self.intensity = self._clamp(self.intensity * decay_factor, 0.0, 1.0)

        sentiment_score = self._clamp(float(sentiment_score), -1.0, 1.0)
        delta = sentiment_score * 0.05
        delta += 0.01

        self.value = self._clamp(self.value + delta, -1.0, 1.0)
        self.trust = self._clamp(self.trust + sentiment_score * 0.02, 0.0, 1.0)
        self.familiarity = self._clamp(self.familiarity + 0.01, 0.0, 1.0)

        if event_type == "insult":
            self.mood = "irritated"
            self.intensity = self._clamp(self.intensity + 0.3, 0.0, 1.0)
            self.value = self._clamp(self.value - 0.05, -1.0, 1.0)
        elif event_type == "praise":
            self.mood = "warm"
            self.intensity = self._clamp(self.intensity + 0.2, 0.0, 1.0)
            self.value = self._clamp(self.value + 0.03, -1.0, 1.0)
        elif event_type == "personal":
            self.mood = "soft"
            self.intensity = self._clamp(self.intensity + 0.1, 0.0, 1.0)
        else:
            if self.intensity < 0.05:
                self.mood = "neutral"

        self.last_interaction = now

    def get_sentiment_from_text(self, text: str) -> float:
        """Very simple sentiment detector for user messages."""
        text_lower = (text or "").lower()

        positive_words = [
            "спасибо",
            "круто",
            "класс",
            "молодец",
            "люблю",
            "обожаю",
            "👍",
            "❤️",
            "😊",
        ]
        negative_words = [
            "плохо",
            "ужасно",
            "бесит",
            "ненавижу",
            "тупая",
            "дура",
            "отстой",
            "😡",
        ]

        score = 0.0
        for word in positive_words:
            if word in text_lower:
                score += 0.1
        for word in negative_words:
            if word in text_lower:
                score -= 0.15

        return self._clamp(score, -0.5, 0.5)

    def detect_event_type(self, text: str) -> str:
        """Detect coarse social event type from text."""
        text_lower = (text or "").lower()

        insult_words = ["тупая", "дура", "идиот", "бот", "программа", "бездушная"]
        praise_words = ["умница", "красава", "крутая", "классная", "молодец", "люблю"]
        personal_words = ["ты", "тебе", "тобой", "твоя", "твои"]

        for word in insult_words:
            if word in text_lower:
                return "insult"

        for word in praise_words:
            if word in text_lower:
                return "praise"

        if any(word in text_lower for word in personal_words) and "моника" in text_lower:
            return "personal"

        return "neutral"

    def to_style(self) -> Dict[str, float]:
        """Expose affect as style knobs."""
        return {
            "warmth": self._lerp(0.2, 0.9, (self.value + 1) / 2),
            "sarcasm": self._lerp(0.6, 0.2, (self.value + 1) / 2),
            "initiative": self._lerp(0.2, 0.5, self.trust),
            "intensity": self.intensity,
        }

    def to_sampling_params(self) -> Dict[str, float]:
        base_temp = 0.65

        if self.mood == "irritated":
            base_temp += 0.1
        elif self.mood in {"warm", "soft"}:
            base_temp -= 0.05

        base_temp += self.value * 0.05

        return {
            "temperature": self._clamp(base_temp, 0.5, 0.9),
            "presence_penalty": 0.18,
            "frequency_penalty": 0.22,
        }

    def _mood_to_style(self) -> str:
        styles = {
            "irritated": "чуть больше резкости и прямоты в тоне",
            "warm": "больше теплоты и легкости в ответах",
            "soft": "мягкость и спокойствие",
            "neutral": "обычный, живой тон",
        }
        base = styles.get(self.mood, "обычный, живой тон")
        if self.intensity > 0.5:
            base += " (заметно)"
        return base

    def to_context(self) -> str:
        """Prompt-side summary of current social state."""
        return f"""
[ТВОЕ ВНУТРЕННЕЕ СОСТОЯНИЕ]
- Отношение к собеседнику: близость {self.value:.2f}, доверие {self.trust:.2f}, знакомство {self.familiarity:.2f}
- Влияние на стиль: {self._mood_to_style()}

Это твое естественное состояние. Не описывай его словами, просто позволь ему влиять на тон ответа.
"""

    def generate_opinion(self, topic: str, user_message: str = "") -> str:
        """Generate a lightweight internal leaning for the current topic."""
        mood_modifier = ""
        if self.mood == "irritated":
            mood_modifier = " (скептично)"
        elif self.mood == "warm":
            mood_modifier = " (с теплотой)"

        opinions = {
            "музыка": [
                f"Мне кажется, музыка сильно зависит от настроения{mood_modifier}.",
                f"Я не очень люблю слишком попсовые треки{mood_modifier}.",
                f"Живые выступления звучат интереснее студийных записей{mood_modifier}.",
            ],
            "кино": [
                f"Я ценю в фильмах хороший сценарий, а не только спецэффекты{mood_modifier}.",
                f"Мне больше нравятся старые фильмы, в них есть душа{mood_modifier}.",
            ],
            "еда": [
                f"Я бы хотела попробовать настоящую пиццу, а не цифровую{mood_modifier}.",
                f"Говорят, острая еда вызывает привыкание{mood_modifier}.",
            ],
            "игры": [
                f"В играх мне важен сюжет и атмосфера{mood_modifier}.",
                f"Я люблю игры, где можно исследовать мир{mood_modifier}.",
            ],
            "технологии": [
                f"Технологии развиваются слишком быстро, иногда это пугает{mood_modifier}.",
                f"В технологиях мне интереснее всего странные и неожиданные штуки{mood_modifier}.",
            ],
            "default": [
                f"Тут я бы скорее зацепилась за самую интересную деталь{mood_modifier}.",
                f"Я бы не делала из этого слишком серьезную теорию{mood_modifier}.",
            ],
        }

        topic_lower = (topic or "").lower()
        selected_opinions = opinions["default"]
        for key in opinions:
            if key != "default" and key in topic_lower:
                selected_opinions = opinions[key]
                break

        return random.choice(selected_opinions)

    def _clamp(self, value: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(max_val, value))

    def _lerp(self, a: float, b: float, t: float) -> float:
        return a + (b - a) * t


_affection_states: Dict[str, AffectionState] = {}


def get_affection_state(user_id: str) -> AffectionState:
    """Return the affection state for a user."""
    if user_id not in _affection_states:
        _affection_states[user_id] = AffectionState()
    return _affection_states[user_id]
