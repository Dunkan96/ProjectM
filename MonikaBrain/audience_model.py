# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

from event_bus import NormalizedEvent


@dataclass
class AudienceSnapshot:
    mood: str = "quiet"
    load: str = "low"
    chat_messages: int = 0
    toxic_pressure: float = 0.0


class AudienceModel:
    def build(self, recent_events: list[NormalizedEvent]) -> AudienceSnapshot:
        chat = [event for event in recent_events if event.source == "chat"]
        toxic = [event for event in chat if any(x in (event.text or "").lower() for x in ["туп", "дура", "затк", "бан"])]
        laughs = [event for event in chat if any(x in (event.text or "").lower() for x in ["ахах", "хаха", "ору", "кек"])]
        if len(chat) > 30:
            load = "high"
        elif len(chat) > 10:
            load = "medium"
        else:
            load = "low"
        mood = "toxic" if toxic else "playful" if laughs else "quiet"
        return AudienceSnapshot(mood=mood, load=load, chat_messages=len(chat), toxic_pressure=min(1.0, len(toxic) / 5.0))

