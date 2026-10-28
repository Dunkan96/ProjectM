# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field

from signal_extractor import ExtractedSignals


@dataclass
class MemoryContext:
    facts: list[str] = field(default_factory=list)
    include_people: bool = False
    confidence: str = "none"
    budget: int = 6
    notes: list[str] = field(default_factory=list)


class MemoryReadPolicy:
    """Решает, какую память давать LLM, а не ждёт слова 'вспомни'."""

    def decide(self, signals: ExtractedSignals, memory_facts: list[str], topic: str = "") -> MemoryContext:
        include_people = signals.memory_intent == "people" or signals.mentions_people
        budget = 8 if signals.memory_intent != "none" else 4
        facts = list(memory_facts or [])[:budget]
        confidence = "high" if len(facts) >= 2 else "medium" if facts else "low" if signals.memory_intent != "none" else "none"
        notes = []
        if include_people:
            notes.append("подмешать обзор известных людей")
        if signals.memory_intent == "facts" and not facts:
            notes.append("не выдумывать прошлые события")
        return MemoryContext(facts=facts, include_people=include_people, confidence=confidence, budget=budget, notes=notes)

    def prompt_block(self, context: MemoryContext) -> str:
        lines = ["[MEMORY POLICY]", f"- confidence={context.confidence}, budget={context.budget}."]
        if context.notes:
            lines.extend(f"- {note}" for note in context.notes)
        if context.facts:
            lines.append("[MEMORY FACTS]")
            lines.extend(f"- {fact}" for fact in context.facts[:context.budget])
        else:
            lines.append("- Подходящих фактов мало или нет: не придумывай.")
        return "\n".join(lines)


class MemoryWritePolicy:
    """Пока только классифицирует, что потенциально стоит записывать после ответа."""

    def classify(self, user_text: str, reply: str) -> dict[str, bool]:
        low = (user_text or "").lower().replace("ё", "е")
        return {
            "stable_fact_candidate": any(x in low for x in ["запомни", "меня зовут", "я люблю", "мой любимый"]),
            "social_event": any(x in low for x in ["спасибо", "тупая", "ахах", "донат", "чат"]),
            "scene_event": any(x in low for x in ["сцена", "история", "босс", "экран"]),
        }

