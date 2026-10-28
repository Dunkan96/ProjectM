# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def _norm(text: str) -> str:
    return (text or "").lower().replace("ё", "е").strip()


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zа-я0-9]{3,}", _norm(text)) if t not in _STOP}


_STOP = {
    "что", "как", "это", "тебя", "меня", "твой", "твоя", "тебе", "мне",
    "там", "вот", "она", "они", "для", "или", "уже", "про", "без",
}


@dataclass
class AnswerEvaluation:
    ok: bool
    score: float = 1.0
    reasons: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "score": round(self.score, 3),
            "reasons": self.reasons,
            "constraints": self.constraints,
        }


class AnswerEvaluator:
    """Checks whether the final reply obeyed the turn contract before it reaches the user."""

    META_LEAKS = [
        "отвечай живее", "response policy", "cognitive state", "turn contract",
        "служебн", "внутренн", "constraint", "reasoning", "<think>",
    ]
    FALSE_INTIMACY = ["я это ты", "мы одно", "мы оба ищем ответы", "часть игры врать"]
    FALSE_EXPERIENCE = [
        "я играла", "я проходила", "моя мама", "мамины рецепты", "я ела",
        "я готовила", "когда я была", "в детстве",
    ]
    TEMPLATE_MARKERS = [
        "я сбилась. повтори коротко", "скажу проще и без выкрутасов",
        "привет, я тут как всегда", "есть в этом вайб", "уже лучше",
    ]
    STORY_MARKERS = ["бип", "корабль", "каньон", "пещер", "лиан", "робот"]
    IDENTITY_MARKERS = ["я моника", "ai-vtuber", "витубер", "виртуаль"]

    def evaluate(
        self,
        reply: str,
        user_text: str,
        *,
        contract: Any = None,
        cognitive_state: Any = None,
        memory_facts: list[str] | None = None,
    ) -> AnswerEvaluation:
        reply_n = _norm(reply)
        user_n = _norm(user_text)
        reasons: list[str] = []
        constraints: list[str] = []
        score = 1.0

        if not reply_n:
            reasons.append("empty_reply")
            constraints.append("Give one direct Monika reply; do not return empty text.")
            score -= 0.7

        if any(x in reply_n for x in self.META_LEAKS):
            reasons.append("internal_instruction_leak")
            constraints.append("Do not mention internal instructions, contracts, policies or 'answer livelier'.")
            score -= 0.35

        if any(x in reply_n for x in self.TEMPLATE_MARKERS):
            reasons.append("template_phrase")
            constraints.append("Do not use the repeated fallback/template phrase; generate from the current situation.")
            score -= 0.3

        primary_intent = getattr(contract, "primary_intent", "reply") if contract is not None else "reply"
        should_story = bool(getattr(contract, "should_continue_story", False)) if contract is not None else False
        suppressed = [str(x).lower() for x in getattr(contract, "suppressed_topics", [])] if contract is not None else []

        if not should_story and any(x in reply_n for x in self.STORY_MARKERS) and not any(x in user_n for x in self.STORY_MARKERS):
            reasons.append("old_story_leak")
            constraints.append("Do not continue the old story; answer the current message only.")
            score -= 0.35

        for topic in suppressed:
            if len(topic) >= 3 and topic in reply_n and topic not in user_n:
                reasons.append("suppressed_topic_leak")
                constraints.append(f"Do not reopen suppressed topic: {topic}.")
                score -= 0.35
                break

        if primary_intent == "focus" and len(re.split(r"[.!?]+", reply)) > 2:
            reasons.append("too_long_for_focus")
            constraints.append("User is busy/fighting; answer in one short supportive line.")
            score -= 0.25

        if primary_intent in {"memory_people", "memory_fact"}:
            facts = memory_facts or getattr(getattr(cognitive_state, "memory", None), "facts", []) or []
            confidence = getattr(getattr(cognitive_state, "memory", None), "confidence", "none")
            if confidence in {"low", "none"} and self._sounds_certain_memory(reply_n):
                reasons.append("unsupported_memory_certainty")
                constraints.append("Memory evidence is weak; say uncertainty naturally and do not invent names/events.")
                score -= 0.35
            if primary_intent == "memory_people" and not facts and self._lists_fake_names(reply):
                reasons.append("invented_people")
                constraints.append("Do not list invented people or nicknames as real users.")
                score -= 0.45

        if primary_intent != "identity" and any(x in reply_n for x in self.IDENTITY_MARKERS):
            if not any(x in user_n for x in ["кто ты", "расскажи о себе", "ты кто"]):
                reasons.append("stale_identity_answer")
                constraints.append("Do not introduce yourself again; answer the current question.")
                score -= 0.25

        if any(x in reply_n for x in self.FALSE_INTIMACY):
            reasons.append("false_intimacy")
            constraints.append("Keep personality, but do not merge identities or make vague existential intimacy claims.")
            score -= 0.35

        if any(x in reply_n for x in self.FALSE_EXPERIENCE):
            if not self._grounded_by_user_or_memory(reply_n, user_n, memory_facts or []):
                reasons.append("false_experience")
                constraints.append("Separate desire/imagination from real experience; do not claim real life, family or played games.")
                score -= 0.35

        if "?" in user_text and self._low_overlap(user_text, reply) and primary_intent not in {"focus", "farewell"}:
            reasons.append("low_current_relevance")
            constraints.append("Answer the latest user question directly before adding personality.")
            score -= 0.12

        ok = score >= 0.72 and not any(r in reasons for r in {
            "empty_reply", "invented_people", "internal_instruction_leak", "unsupported_memory_certainty",
        })
        if not constraints:
            constraints.append("Keep the answer grounded in the current turn and Monika's personality.")
        return AnswerEvaluation(ok=ok, score=max(0.0, score), reasons=reasons, constraints=constraints)

    def _sounds_certain_memory(self, text: str) -> bool:
        return any(x in text for x in ["точно помню", "мы обсуждали", "ты говорил", "я знаю, что", "помню, как"])

    def _lists_fake_names(self, reply: str) -> bool:
        if "," not in reply:
            return False
        funny_markers = ["барон", "ведьмак", "архимаг", "дирижер", "босс", "рыцарь"]
        return any(x in _norm(reply) for x in funny_markers)

    def _grounded_by_user_or_memory(self, reply_n: str, user_n: str, facts: list[str]) -> bool:
        if any(x in user_n for x in ["представь", "фантазируй", "вообрази", "история"]):
            return True
        joined = _norm(" ".join(facts or []))
        return bool(joined and any(x in joined for x in self.FALSE_EXPERIENCE))

    def _low_overlap(self, user_text: str, reply: str) -> bool:
        user_tokens = _tokens(user_text)
        if not user_tokens:
            return False
        reply_tokens = _tokens(reply)
        if not reply_tokens:
            return True
        if user_tokens & reply_tokens:
            return False
        return len(user_tokens) >= 3
