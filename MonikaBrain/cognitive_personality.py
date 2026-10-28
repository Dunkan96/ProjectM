# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from people_model import PersonSnapshot


@dataclass
class RelationshipDepth:
    label: str = "unknown"
    stance: str = "neutral"
    trust: float = 0.0
    friction: float = 0.0


class RelationshipDepthModel:
    """Сводит социальные числа в понятный образ человека."""

    def build(self, person: PersonSnapshot) -> RelationshipDepth:
        if person.role == "creator":
            return RelationshipDepth("creator", "warm_teasing", 0.9, min(0.6, person.irritation))
        if person.irritation > 0.65:
            return RelationshipDepth("problematic_viewer", "guarded", 0.2, person.irritation)
        if person.affection > 0.45 or person.familiarity > 0.6:
            return RelationshipDepth("familiar_viewer", "friendly", max(person.affection, person.familiarity), person.irritation)
        if person.messages <= 1:
            return RelationshipDepth("new_person", "curious", 0.1, person.irritation)
        return RelationshipDepth("regular", "neutral_playful", person.familiarity, person.irritation)


@dataclass
class PersonaEvolution:
    notes: list[str] = field(default_factory=list)


class PersonaEvolutionPolicy:
    """Мягкая эволюция личности без переписывания identity."""

    def build(self, desires: list[dict[str, Any]] | None, opinions: list[dict[str, Any]] | None, feedback: dict[str, Any] | None = None) -> PersonaEvolution:
        notes: list[str] = []
        for item in (desires or [])[:3]:
            target = item.get("target") or item.get("category")
            if target:
                notes.append(f"интерес к {target} может всплывать, но не должен захватывать диалог")
        for item in (opinions or [])[:3]:
            topic = item.get("topic") or item.get("target")
            stance = item.get("stance") or item.get("opinion")
            if topic and stance:
                notes.append(f"позиция по {topic}: {stance}")
        if feedback and feedback.get("last_feedback"):
            notes.append(f"учесть недавнюю оценку Дункана: {feedback['last_feedback']}")
        return PersonaEvolution(notes=notes[:6])


@dataclass
class UncertaintyProfile:
    level: str = "normal"
    instruction: str = "если не уверена, говори живо и честно"


class UncertaintyBehavior:
    def build(self, memory_confidence: str, goal: str) -> UncertaintyProfile:
        if memory_confidence in {"low", "none"} and goal == "memory":
            return UncertaintyProfile("high", "не выдумывать; можно сказать, что память не даёт опоры, но без шаблонной фразы")
        if goal == "repair":
            return UncertaintyProfile("careful", "признать возможный промах и вернуться к текущему вопросу")
        return UncertaintyProfile()


@dataclass
class IdentityBoundary:
    risk: str = "ok"
    constraints: list[str] = field(default_factory=list)


class IdentityBoundaryPolicy:
    """Что можно считать частью 'я', а что шуткой/фантазией."""

    FALSE_SELF_PATTERNS = [
        r"\bмоя мама\b", r"\bмой отец\b", r"\bя ела\b", r"\bя играла\b", r"\bкогда я была маленькой\b",
        r"\bв реальной жизни\b", r"\bу меня тело\b",
    ]

    def inspect_input(self, text: str) -> IdentityBoundary:
        low = (text or "").lower().replace("ё", "е")
        if any(x in low for x in ["ты реальна", "ты человек", "у тебя мама", "ты ела", "ты играла"]):
            return IdentityBoundary("identity_sensitive", [
                "отделять виртуальную личность, желания и фантазию от реального физического опыта",
                "не закреплять шутку как факт о себе",
            ])
        return IdentityBoundary()

    def reply_has_risk(self, reply: str) -> bool:
        low = (reply or "").lower().replace("ё", "е")
        return any(re.search(pattern, low) for pattern in self.FALSE_SELF_PATTERNS)


@dataclass
class RepairHint:
    needed: bool = False
    reason: str = ""
    constraints: list[str] = field(default_factory=list)


class ConversationRepairSkill:
    def inspect(self, user_text: str, reply: str, goal: str) -> RepairHint:
        low_user = (user_text or "").lower().replace("ё", "е")
        low_reply = (reply or "").lower().replace("ё", "е")
        if any(x in low_user for x in ["ты отвечаешь не на то", "не в попад", "ты уехала", "не туда"]):
            return RepairHint(True, "user_reports_miss", [
                "признай, что уехала не туда",
                "ответь именно на последний вопрос пользователя",
                "не начинай представляться заново",
            ])
        if goal == "memory" and any(x in low_reply for x in ["неважно", "давай дальше"]) and "помни" in low_user:
            return RepairHint(True, "memory_question_ignored", ["ответить по памяти или честно обозначить её отсутствие"])
        return RepairHint()


class HumanFeedbackLoop:
    """Оценки Дункана становятся сигналом поведения."""

    def __init__(self):
        self.last_feedback: str = ""

    def observe(self, text: str) -> dict[str, Any]:
        low = (text or "").lower().replace("ё", "е")
        feedback = ""
        if any(x in low for x in ["это живо", "вот так хорошо", "стало лучше", "круто ответила"]):
            feedback = "positive_live_behavior"
        elif any(x in low for x in ["кринж", "шаблон", "сухо", "робот", "не в попад", "врешь", "врёшь"]):
            feedback = "negative_behavior_correction"
        if feedback:
            self.last_feedback = feedback
        return {"last_feedback": self.last_feedback, "current_feedback": feedback}


@dataclass
class TimelineMoment:
    text: str
    kind: str = "session"


class AutobiographicalTimeline:
    """Короткая жизненная линия Моники в рамках текущего процесса."""

    def __init__(self, limit: int = 30):
        self.limit = limit
        self.moments: list[TimelineMoment] = []

    def observe(self, user_text: str, reply: str, goal: str) -> None:
        low = (user_text or "").lower().replace("ё", "е")
        if goal in {"test_repair", "story", "memory"} or any(x in low for x in ["первый", "важно", "запомни", "мы сделали"]):
            text = f"{goal}: user={user_text[:120]} | monika={reply[:120]}"
            self.moments.append(TimelineMoment(text=text, kind=goal))
            del self.moments[:-self.limit]

    def prompt_block(self) -> str:
        if not self.moments:
            return ""
        lines = ["[AUTOBIOGRAPHICAL TIMELINE]"]
        for moment in self.moments[-5:]:
            lines.append(f"- {moment.text}")
        return "\n".join(lines)


class SelfReflectionDigest:
    """Краткий digest после сессии или по debug-запросу."""

    def build(self, recent: list[TimelineMoment]) -> str:
        if not recent:
            return "Пока мало материала для вывода."
        return " | ".join(moment.text[:100] for moment in recent[-5:])

