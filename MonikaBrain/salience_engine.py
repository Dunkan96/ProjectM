# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from event_bus import NormalizedEvent
from signal_extractor import ExtractedSignals


@dataclass
class SalienceItem:
    kind: str
    text: str
    score: float
    reason: str


@dataclass
class SalienceSnapshot:
    items: list[SalienceItem] = field(default_factory=list)


class SalienceEngine:
    """Решает, что само всплывает в голове Моники."""

    def rank(
        self,
        event: NormalizedEvent,
        signals: ExtractedSignals,
        memory_facts: list[str],
        known_people: list[Any],
        active_desires: list[dict[str, Any]],
    ) -> SalienceSnapshot:
        items: list[SalienceItem] = []
        if signals.memory_intent == "people":
            items.append(SalienceItem("people", "пользователь спрашивает о людях, которых Моника знает", 0.95, "people_memory_intent"))
        if event.source == "donation":
            items.append(SalienceItem("donation", "донат важнее обычного чата", 0.9, "stream_priority"))
        if signals.topic:
            items.append(SalienceItem("topic", signals.topic, 0.65, "current_topic"))
        for fact in memory_facts[:4]:
            items.append(SalienceItem("memory", fact, 0.55, "retrieved_fact"))
        for person in known_people[:3]:
            name = getattr(person, "display_name", "")
            if name:
                items.append(SalienceItem("person", name, 0.45, "known_person"))
        for desire in active_desires[:2]:
            target = desire.get("target") or desire.get("category")
            if target:
                items.append(SalienceItem("desire", str(target), 0.35, "soft_desire"))
        items.sort(key=lambda x: x.score, reverse=True)
        return SalienceSnapshot(items=items[:8])

    def prompt_block(self, snapshot: SalienceSnapshot) -> str:
        if not snapshot.items:
            return "[SALIENCE]\n- Нет сильного всплывающего контекста. Держи текущую реплику."
        lines = ["[SALIENCE]"]
        for item in snapshot.items:
            lines.append(f"- {item.kind}: {item.text} ({item.reason}, {item.score:.2f})")
        return "\n".join(lines)

