# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any


def _norm(text: str) -> str:
    return (text or "").lower().replace("ё", "е").strip()


def _has_any(text: str, needles: list[str]) -> bool:
    return any(n in text for n in needles)


def _short_hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()[:10]


@dataclass
class TurnContract:
    turn_id: str
    source: str
    role: str
    primary_intent: str = "reply"
    semantic_owner: str = "turn_orchestrator"
    scene_action: str = "answer_current"
    should_continue_story: bool = False
    allow_desires: bool = True
    allow_background_topics: bool = True
    allow_memory: bool = True
    memory_mode: str = "contextual"
    memory_write_mode: str = "normal"
    performance_mode: str = "live"
    truth_mode: str = "grounded"
    latency_mode: str = "normal"
    max_prompt_chars: int = 16000
    max_sentences: int = 3
    confidence: dict[str, str] = field(default_factory=dict)
    suppressed_topics: list[str] = field(default_factory=list)
    required_answer_points: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    retry_plan: list[str] = field(default_factory=list)
    source_attribution: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "source": self.source,
            "role": self.role,
            "primary_intent": self.primary_intent,
            "semantic_owner": self.semantic_owner,
            "scene_action": self.scene_action,
            "should_continue_story": self.should_continue_story,
            "allow_desires": self.allow_desires,
            "allow_background_topics": self.allow_background_topics,
            "allow_memory": self.allow_memory,
            "memory_mode": self.memory_mode,
            "memory_write_mode": self.memory_write_mode,
            "performance_mode": self.performance_mode,
            "truth_mode": self.truth_mode,
            "latency_mode": self.latency_mode,
            "max_prompt_chars": self.max_prompt_chars,
            "max_sentences": self.max_sentences,
            "confidence": self.confidence,
            "suppressed_topics": self.suppressed_topics,
            "required_answer_points": self.required_answer_points,
            "constraints": self.constraints,
            "retry_plan": self.retry_plan,
            "source_attribution": self.source_attribution,
        }

    def prompt_block(self) -> str:
        lines = [
            "[TURN CONTRACT]",
            f"- turn_id={self.turn_id}, source={self.source}, role={self.role}.",
            f"- primary_intent={self.primary_intent}, scene_action={self.scene_action}, semantic_owner={self.semantic_owner}.",
            f"- story_continue={self.should_continue_story}, memory={self.memory_mode}/{self.memory_write_mode}, truth={self.truth_mode}, performance={self.performance_mode}.",
            f"- allow_desires={self.allow_desires}, allow_background_topics={self.allow_background_topics}, max_sentences={self.max_sentences}, latency={self.latency_mode}.",
            "- This is the top-level turn contract. If older context conflicts with it, follow this contract.",
            "- Answer the current user message first. Do not continue an old scene unless story_continue=true.",
            "- Use memory as grounding, not as a script. If evidence is weak, say uncertainty naturally.",
        ]
        if self.required_answer_points:
            lines.append("[REQUIRED ANSWER POINTS]")
            lines.extend(f"- {item}" for item in self.required_answer_points)
        if self.suppressed_topics:
            lines.append("[SUPPRESSED TOPICS]")
            lines.extend(f"- Do not re-open: {topic}" for topic in self.suppressed_topics[:8])
        if self.constraints:
            lines.append("[TURN CONSTRAINTS]")
            lines.extend(f"- {item}" for item in self.constraints)
        if self.source_attribution:
            lines.append("[SOURCE ATTRIBUTION]")
            for key, value in self.source_attribution.items():
                lines.append(f"- {key}: {value}")
        return "\n".join(lines)


class TurnOrchestrator:
    """Single owner of the current turn: intent, scene, memory, latency and retry contract."""

    STORY_CONTINUE = [
        "продолжи", "продолжай", "дальше", "что дальше", "и тут", "затем", "после этого",
        "он ", "она ", "они ", "бип", "герой", "сцена", "история",
    ]
    STORY_EXIT = [
        "стоп", "хватит", "закрыли", "не продолжай", "забудь", "кто ты",
        "кто я", "как меня зовут", "кто такой", "что происходит", "пока",
        "отстань", "сменим тему", "не об этом",
    ]
    MEMORY_HINTS = [
        "помнишь", "вспомни", "что ты знаешь", "кто тебе писал", "других людей",
        "каких людей", "что говорил", "timeline", "таймлайн",
    ]
    PEOPLE_HINTS = [
        "кто тебе писал", "другие люди", "других людей", "имена", "пользователи",
        "зрители", "кто такой", "что говорил",
    ]
    IDENTITY_HINTS = ["кто ты", "что ты такое", "расскажи о себе", "ты девушка", "ты ассистент"]
    FOCUS_HINTS = ["не отвлекай", "коротко", "быстро", "я уворачиваюсь", "сейчас бой"]
    REPAIR_HINTS = ["ты врешь", "ты врёшь", "выдумываешь", "не было", "не в попад", "как робот", "шаблон"]

    def build(
        self,
        *,
        user_text: str,
        source: str = "dialogue",
        role: str = "viewer",
        cognitive_state: Any = None,
        response_decision: Any = None,
        behavior_plan: Any = None,
        scene_state: dict[str, Any] | None = None,
        memory_facts: list[str] | None = None,
        active_desires: list[dict[str, Any]] | None = None,
        active_opinions: list[dict[str, Any]] | None = None,
        boundary_mode: str = "twitch_safe",
    ) -> TurnContract:
        text = _norm(user_text)
        now = int(time.time())
        source = source or getattr(getattr(cognitive_state, "event", None), "source", "dialogue")
        role = role or getattr(getattr(cognitive_state, "event", None), "role", "viewer")
        turn_id = f"{now}-{source}-{role}-{_short_hash(user_text)}"

        primary_intent = self._detect_intent(text, cognitive_state)
        private_mode = boundary_mode == "private_adult"
        scene_action = "answer_current"
        should_continue_story = False
        story_active = self._story_is_active(cognitive_state, scene_state)
        explicit_story_continue = _has_any(text, self.STORY_CONTINUE)
        explicit_story_exit = _has_any(text, self.STORY_EXIT)

        if private_mode and primary_intent not in {"identity", "memory_people", "memory_fact", "repair", "focus", "farewell"}:
            primary_intent = "private_scene"
            should_continue_story = True
            scene_action = "continue_private_scene"
        elif explicit_story_exit or primary_intent in {"identity", "memory_people", "memory_fact", "repair", "focus", "farewell"}:
            scene_action = "exit_or_suspend_scene"
        elif story_active and explicit_story_continue and primary_intent == "reply":
            should_continue_story = True
            scene_action = "continue_story"
            primary_intent = "story_continue"
        elif story_active:
            scene_action = "suspend_story_answer_current"

        suppressed = self._suppressed_topics(scene_state)
        allow_desires = primary_intent not in {"identity", "memory_people", "memory_fact", "repair", "focus", "farewell"}
        allow_background = allow_desires and not suppressed
        memory_mode = self._memory_mode(primary_intent, cognitive_state)
        memory_write_mode = self._memory_write_mode(text, primary_intent, boundary_mode)
        latency_mode = self._latency_mode(source, primary_intent, cognitive_state)
        max_sentences = self._max_sentences(primary_intent, response_decision, latency_mode)

        constraints = [
            "Direct user request outranks story, desire, old jokes and old topics.",
            "Do not answer a previous turn unless the user explicitly asks to continue it.",
            "Do not invent real experiences, real relatives, played games or physical memories.",
            "If asked about memory, use only retrieved facts/people/timeline hints and mark uncertainty.",
            "Repair must change wording and focus, not silently change facts.",
        ]
        if primary_intent == "memory_people":
            constraints.append("List known people only if the context actually contains them; otherwise admit weak memory.")
        if scene_action.startswith("exit") or scene_action.startswith("suspend"):
            constraints.append("Do not continue current story or old scene in this answer.")
        if not allow_desires:
            constraints.append("Do not push Monika's desires/opinions unless the user asked for them.")
        if suppressed:
            constraints.append("Suppressed topics are cooldowned; do not re-open them as initiative.")
        if boundary_mode != "twitch_safe":
            constraints.append("Respect boundary mode and do not write private/boundary material to long-term memory.")
        if private_mode:
            constraints.extend([
                "Private creator-only mode: keep continuity of the current private scene.",
                "Do not revive old stories, old jokes, pizza, Barс/Барс, cats, Cyberpunk or Elden Ring unless the user says them now.",
                "Monika keeps agency: playful consent, teasing and boundaries are allowed; coercion is not.",
            ])

        required = self._required_points(primary_intent, text)
        confidence = {
            "memory": getattr(getattr(cognitive_state, "memory", None), "confidence", "none"),
            "scene": "high" if should_continue_story else "medium" if story_active else "low",
            "desire": "medium" if active_desires else "low",
            "opinion": "medium" if active_opinions else "low",
        }
        source_attribution = {
            "current_message": "highest priority",
            "memory_facts": f"{len(memory_facts or [])} retrieved fact(s)",
            "scene": scene_action,
        }
        if active_desires:
            source_attribution["desires"] = "available but secondary to current intent"

        contract = TurnContract(
            turn_id=turn_id,
            source=source,
            role=role,
            primary_intent=primary_intent,
            scene_action=scene_action,
            should_continue_story=should_continue_story,
            allow_desires=allow_desires,
            allow_background_topics=allow_background,
            allow_memory=memory_mode != "none",
            memory_mode=memory_mode,
            memory_write_mode=memory_write_mode,
            performance_mode="fast_live" if latency_mode == "fast" else "expressive_live",
            truth_mode="strict" if primary_intent in {"memory_people", "memory_fact", "repair"} else "grounded",
            latency_mode=latency_mode,
            max_prompt_chars=9000 if latency_mode == "fast" else 16000,
            max_sentences=max_sentences,
            confidence=confidence,
            suppressed_topics=suppressed,
            required_answer_points=required,
            constraints=constraints,
            retry_plan=[
                "If answer is off-topic: retry with current user message only + verified facts.",
                "If answer invents facts: retry in strict truth mode.",
                "If answer leaks old scene/topic: retry with scene_action enforced.",
            ],
            source_attribution=source_attribution,
        )
        return contract

    def _detect_intent(self, text: str, cognitive_state: Any) -> str:
        if not text:
            return "reply"
        if _has_any(text, ["пока", "выключаю", "до свидания"]):
            return "farewell"
        if _has_any(text, self.REPAIR_HINTS):
            return "repair"
        if _has_any(text, self.FOCUS_HINTS):
            return "focus"
        if _has_any(text, self.PEOPLE_HINTS):
            return "memory_people"
        if _has_any(text, self.MEMORY_HINTS):
            return "memory_fact"
        if _has_any(text, self.IDENTITY_HINTS):
            return "identity"
        signals = getattr(cognitive_state, "signals", None)
        if getattr(signals, "memory_intent", "none") == "people":
            return "memory_people"
        if getattr(signals, "memory_intent", "none") not in {"", "none", None}:
            return "memory_fact"
        if getattr(signals, "intent", "") == "interrupt":
            return "focus"
        return "reply"

    def _story_is_active(self, cognitive_state: Any, scene_state: dict[str, Any] | None) -> bool:
        mode = getattr(getattr(cognitive_state, "situation", None), "mode", "")
        story_status = getattr(getattr(cognitive_state, "story", None), "status", "")
        if mode == "story" or story_status in {"active", "continue"}:
            return True
        scene_state = scene_state or {}
        return str(scene_state.get("story_focus") or "").lower() == "active" or str(scene_state.get("continuity_anchor") or "") == "story"

    def _suppressed_topics(self, scene_state: dict[str, Any] | None) -> list[str]:
        scene_state = scene_state or {}
        topics: list[str] = []
        rejected = scene_state.get("rejected_topics") or {}
        if isinstance(rejected, dict):
            topics.extend(str(x) for x in rejected.keys())
        banned = scene_state.get("banned_topics") or scene_state.get("suppressed_topics") or []
        if isinstance(banned, dict):
            topics.extend(str(x) for x in banned.keys())
        elif isinstance(banned, list):
            topics.extend(str(x) for x in banned)
        cooldown_defaults = ["пицца", "elden ring", "киберпанк", "бип", "архимаг бэкапов"]
        topics.extend(x for x in cooldown_defaults if x in " ".join(topics).lower())
        seen = set()
        clean = []
        for topic in topics:
            t = topic.strip().lower()
            if t and t not in seen:
                clean.append(t)
                seen.add(t)
        return clean[:10]

    def _memory_mode(self, primary_intent: str, cognitive_state: Any) -> str:
        if primary_intent == "memory_people":
            return "people_timeline"
        if primary_intent == "memory_fact":
            return "facts_timeline"
        memory = getattr(cognitive_state, "memory", None)
        if getattr(memory, "facts", None):
            return "contextual"
        return "none"

    def _memory_write_mode(self, text: str, primary_intent: str, boundary_mode: str) -> str:
        if boundary_mode and boundary_mode != "twitch_safe":
            return "ephemeral"
        if primary_intent in {"repair", "focus", "farewell"}:
            return "ephemeral"
        if _has_any(text, ["шутка", "рофл", "мем", "придумай кличку"]):
            return "joke_not_fact"
        if _has_any(text, ["кажется", "может быть", "наверное"]):
            return "quarantine"
        return "normal"

    def _latency_mode(self, source: str, primary_intent: str, cognitive_state: Any) -> str:
        if source in {"screen", "donation"} or primary_intent in {"focus", "farewell"}:
            return "fast"
        audience = getattr(cognitive_state, "audience", None)
        if getattr(audience, "load", "") == "high":
            return "fast"
        if primary_intent in {"memory_people", "memory_fact"}:
            return "deep"
        return "normal"

    def _max_sentences(self, primary_intent: str, response_decision: Any, latency_mode: str) -> int:
        base = int(getattr(response_decision, "max_sentences", 3) or 3)
        if primary_intent == "story_continue":
            return max(3, min(5, base + 1))
        if primary_intent == "private_scene":
            return max(2, min(4, base + 1))
        if latency_mode == "fast":
            return 1 if primary_intent == "focus" else 2
        if primary_intent in {"memory_people", "memory_fact"}:
            return max(2, min(4, base + 1))
        return max(2, min(4, base))

    def _required_points(self, primary_intent: str, text: str) -> list[str]:
        if primary_intent == "identity":
            return ["Say who Monika is without repeating a canned biography."]
        if primary_intent == "memory_people":
            return ["Answer whether Monika knows/recalls people and avoid inventing names."]
        if primary_intent == "memory_fact":
            return ["Use retrieved facts if present; otherwise be honest about weak memory."]
        if primary_intent == "repair":
            return ["Acknowledge the correction and stop the false line."]
        if primary_intent == "private_scene":
            return ["Continue the current private scene only; do not jump to old topics."]
        if primary_intent == "focus":
            return ["Keep it short and do not distract."]
        if "?" in text:
            return ["Answer the actual question in the latest user message."]
        return []
