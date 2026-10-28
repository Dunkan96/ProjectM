# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResponseDecision:
    mode: str = "reply"
    max_sentences: int = 2
    max_tokens: int = 220
    should_reply: bool = True
    allow_initiative: bool = True
    tts_style: str = "normal"
    latency_mode: str = "normal"
    constraints: list[str] = field(default_factory=list)

    def prompt_block(self) -> str:
        lines = [
            "[RESPONSE POLICY]",
            f"- mode={self.mode}, max_sentences={self.max_sentences}, max_tokens={self.max_tokens}, tts_style={self.tts_style}, latency={self.latency_mode}.",
            f"- should_reply={self.should_reply}, allow_initiative={self.allow_initiative}.",
            "- Это главный контракт формы ответа. Старые блоки ниже не должны его переопределять.",
        ]
        lines.extend(f"- {item}" for item in self.constraints)
        return "\n".join(lines)


class ResponsePolicy:
    """Отделяет 'что происходит' от 'как отвечать'."""

    def decide(self, cognitive_state: Any, behavior_plan: Any = None) -> ResponseDecision:
        event = cognitive_state.event
        attention = cognitive_state.attention
        signals = cognitive_state.signals
        constraints = []
        if not attention.should_reply:
            return ResponseDecision(
                mode="silent",
                max_sentences=0,
                max_tokens=0,
                should_reply=False,
                allow_initiative=False,
                latency_mode="drop",
                constraints=["не отвечать, только запомнить/наблюдать"],
            )
        if signals.intent == "interrupt":
            return ResponseDecision(mode="interrupt", max_sentences=1, max_tokens=90, allow_initiative=False, tts_style="short", latency_mode="fast", constraints=["остановить старую сцену"])
        if event.source == "donation":
            return ResponseDecision(mode="donation", max_sentences=2, max_tokens=180, tts_style="bright", latency_mode="fast", constraints=["поблагодарить за текущий донат, не мешать с прошлым чатом"])
        if cognitive_state.situation.mode == "story":
            return ResponseDecision(mode="story_continue", max_sentences=4, max_tokens=340, tts_style="dramatic", latency_mode="deep", constraints=["держать сцену 2-5 ходов", "не прыгать в старые темы"])
        if signals.memory_intent == "people":
            return ResponseDecision(mode="people_memory", max_sentences=3, max_tokens=260, constraints=["отвечать из People Model", "не выдумывать людей вне базы"])
        if cognitive_state.situation.pace == "fast":
            constraints.append("стримовый темп быстрый: короче и острее")
            return ResponseDecision(mode="fast_react", max_sentences=2, max_tokens=160, tts_style="quick", latency_mode="fast", constraints=constraints)
        return ResponseDecision(
            mode="reply",
            max_sentences=int(getattr(behavior_plan, "max_sentences", 2) or 2),
            max_tokens=int(getattr(behavior_plan, "max_tokens", 220) or 220),
            constraints=constraints,
        )

    def apply_to_behavior_plan(self, behavior_plan: Any, decision: ResponseDecision) -> None:
        if behavior_plan is None or decision is None:
            return
        if decision.max_sentences:
            try:
                behavior_plan.max_sentences = max(1, min(int(behavior_plan.max_sentences), int(decision.max_sentences)))
            except Exception:
                behavior_plan.max_sentences = int(decision.max_sentences)
        if decision.max_tokens:
            try:
                behavior_plan.max_tokens = max(80, min(int(behavior_plan.max_tokens), int(decision.max_tokens)))
            except Exception:
                behavior_plan.max_tokens = int(decision.max_tokens)
        try:
            behavior_plan.initiative_allowed = bool(decision.allow_initiative and getattr(behavior_plan, "initiative_allowed", False))
        except Exception:
            pass
        if decision.mode in {"interrupt", "silent", "fast_react", "donation"}:
            try:
                behavior_plan.allow_followup_question = False
            except Exception:
                pass
