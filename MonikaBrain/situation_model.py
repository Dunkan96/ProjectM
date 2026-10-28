# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from event_bus import NormalizedEvent
from signal_extractor import ExtractedSignals


@dataclass
class SituationSnapshot:
    mode: str = "dialogue"
    topic: str = ""
    scene: str = ""
    tension: float = 0.0
    pace: str = "normal"
    recent_sources: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class SituationModel:
    """Краткая модель текущего момента, а не долговременная память."""

    def update(
        self,
        scene_state: dict[str, Any] | None,
        event: NormalizedEvent,
        signals: ExtractedSignals,
        source_counts: dict[str, int] | None = None,
    ) -> SituationSnapshot:
        scene_state = scene_state or {}
        source_counts = source_counts or {}
        mode = "stream" if event.source in {"chat", "donation", "screen", "voice"} else "dialogue"
        if scene_state.get("story_focus") or signals.topic == "история":
            mode = "story"
        topic = signals.topic or str(scene_state.get("topic") or "")
        scene = str(scene_state.get("ongoing_bit") or scene_state.get("continuity_anchor") or "")
        tension = 0.0
        if signals.toxicity:
            tension += 0.4
        if event.source == "screen":
            tension += 0.25
        if signals.sentiment < -0.3:
            tension += 0.2
        pace = "fast" if source_counts.get("chat", 0) > 15 or signals.urgency > 0.75 else "normal"
        notes = []
        if mode == "story":
            notes.append("держать текущую историю/сцену, не прыгать в старые темы")
        if event.source == "donation":
            notes.append("донат изолирован от предыдущего чата")
        return SituationSnapshot(mode=mode, topic=topic, scene=scene, tension=min(1.0, tension), pace=pace, recent_sources=source_counts, notes=notes)

