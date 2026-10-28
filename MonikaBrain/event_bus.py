# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedEvent:
    """Единый формат события для голоса, чата, доната, экрана и Telegram."""

    source: str
    text: str
    person_id: str = ""
    display_name: str = ""
    role: str = "viewer"
    priority: int = 50
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - float(self.timestamp or time.time()))


class EventBus:
    """Лёгкий журнал событий. Пока без брокера: достаточно для cognitive state."""

    def __init__(self, max_events: int = 120):
        self.events: deque[NormalizedEvent] = deque(maxlen=max_events)

    def publish(self, event: NormalizedEvent) -> NormalizedEvent:
        self.events.append(event)
        return event

    def recent(self, limit: int = 20, source: str | None = None) -> list[NormalizedEvent]:
        items = list(self.events)
        if source:
            items = [event for event in items if event.source == source]
        return items[-limit:]

    def source_counts(self, seconds: float = 60.0) -> dict[str, int]:
        now = time.time()
        counts: dict[str, int] = {}
        for event in self.events:
            if now - event.timestamp <= seconds:
                counts[event.source] = counts.get(event.source, 0) + 1
        return counts

