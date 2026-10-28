# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

from event_bus import NormalizedEvent
from signal_extractor import ExtractedSignals


@dataclass
class AttentionDecision:
    focus: str
    should_reply: bool
    reason: str
    priority_score: float
    latency_mode: str = "normal"


class AttentionArbiter:
    """Выбирает, отвечать ли и чему отдать фокус."""

    SOURCE_WEIGHT = {
        "voice": 1.0,
        "text_input": 0.95,
        "telegram": 0.9,
        "donation": 0.88,
        "screen": 0.65,
        "chat": 0.45,
        "proactive": 0.25,
        "association": 0.2,
    }

    def decide(self, event: NormalizedEvent, signals: ExtractedSignals, load: dict[str, int] | None = None) -> AttentionDecision:
        load = load or {}
        source_weight = self.SOURCE_WEIGHT.get(event.source, 0.4)
        score = source_weight + signals.urgency + min(0.4, event.priority / 250.0)
        if signals.direct_address:
            score += 0.25
        if signals.intent in {"interrupt", "thank_donation", "memory_recall"}:
            score += 0.35
        if event.source == "chat" and load.get("chat", 0) > 20 and not signals.direct_address and signals.toxicity < 0.8:
            return AttentionDecision("chat_noise", False, "чат шумный, сообщение не достаточно важное", score, "drop")
        if event.source == "chat" and load.get("chat", 0) > 8 and score < 1.15 and not signals.direct_address:
            return AttentionDecision("chat_backpressure", False, "чат разогнался, это сообщение лучше только учесть фоном", score, "drop")
        if signals.intent == "interrupt":
            return AttentionDecision("creator_interrupt", True, "жёсткий стоп важнее контекста", 2.0, "fast")
        if event.source == "donation":
            return AttentionDecision("donation", True, "донат требует отдельной реакции", score, "fast")
        if event.source == "screen" and load.get("voice", 0) > 0:
            return AttentionDecision("voice_over_screen", False, "голос Дункана важнее экрана", score, "drop")
        return AttentionDecision(event.source or "dialogue", score >= 0.8, "достаточная релевантность", score)
