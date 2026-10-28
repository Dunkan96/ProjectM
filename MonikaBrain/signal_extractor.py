# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from dataclasses import dataclass, field

from event_bus import NormalizedEvent


@dataclass
class ExtractedSignals:
    topic: str = ""
    intent: str = "react"
    sentiment: float = 0.0
    urgency: float = 0.2
    toxicity: float = 0.0
    memory_intent: str = "none"
    mentions_people: bool = False
    direct_address: bool = False
    keywords: list[str] = field(default_factory=list)


class SignalExtractor:
    """Достаёт смысловые сигналы из события без генерации ответа."""

    TOPIC_HINTS = {
        "игры": ["игра", "elden", "dark souls", "warcraft", "wow", "киберпанк", "босс", "перекат"],
        "еда": ["пицц", "еда", "пиво", "шаурм", "суши"],
        "память": ["помни", "вспом", "знаешь обо", "кто тебе писал", "других людей"],
        "стрим": ["стрим", "чат", "донат", "зрител"],
        "история": ["история", "сцена", "мы идем", "мы идём", "персонаж", "продолжи"],
    }

    def extract(self, event: NormalizedEvent) -> ExtractedSignals:
        text = (event.text or "").lower().replace("ё", "е")
        signals = ExtractedSignals()
        signals.direct_address = any(x in text for x in ["моника", "monika", "ответь"])
        signals.mentions_people = any(x in text for x in [
            "кто тебе писал", "других людей", "другие люди", "людей помнишь", "зрителей", "кто был",
            "кого ты знаешь", "кого помнишь", "знаешь людей", "viewer", "пользователь", "человек", "донатер",
        ])
        signals.memory_intent = self._memory_intent(text)
        signals.intent = self._intent(text, event)
        signals.topic = self._topic(text)
        signals.sentiment = self._sentiment(text)
        signals.toxicity = 1.0 if any(x in text for x in ["тупая", "дура", "заткнись", "сдохни"]) else 0.0
        signals.urgency = self._urgency(text, event)
        signals.keywords = re.findall(r"[a-zа-я0-9]{4,}", text)[:12]
        return signals

    def _topic(self, text: str) -> str:
        for topic, hints in self.TOPIC_HINTS.items():
            if any(hint in text for hint in hints):
                return topic
        return ""

    def _intent(self, text: str, event: NormalizedEvent) -> str:
        if event.source == "donation":
            return "thank_donation"
        if event.source == "screen":
            return "react_screen"
        if any(x in text for x in ["стоп", "остановись", "не продолжай"]):
            return "interrupt"
        if any(x in text for x in ["помни", "вспом", "что знаешь", "кто тебе писал"]):
            return "memory_recall"
        if any(x in text for x in ["расскажи", "объясни", "почему"]):
            return "explain"
        if "?" in text:
            return "answer_question"
        return "react"

    def _memory_intent(self, text: str) -> str:
        if any(x in text for x in [
            "кто тебе писал", "других людей", "другие люди", "каких людей", "зрителей помнишь",
            "кого ты знаешь", "кого помнишь", "знаешь людей", "помнишь людей",
        ]):
            return "people"
        if any(x in text for x in ["помни", "вспом", "что знаешь обо мне", "мы обсуждали"]):
            return "facts"
        return "none"

    def _sentiment(self, text: str) -> float:
        score = 0.0
        if any(x in text for x in ["спасибо", "круто", "ахах", "люблю", "кайф"]):
            score += 0.45
        if any(x in text for x in ["устал", "плохо", "грустно", "бесит", "тупая", "врешь", "врёшь"]):
            score -= 0.55
        return max(-1.0, min(1.0, score))

    def _urgency(self, text: str, event: NormalizedEvent) -> float:
        if event.source in {"voice", "text_input", "telegram"} and any(x in text for x in ["сейчас", "быстро", "срочно", "не отвлекай"]):
            return 0.9
        if event.source == "donation":
            return 0.85
        if event.source == "screen":
            return 0.65
        if event.priority >= 90:
            return 0.8
        return 0.25
