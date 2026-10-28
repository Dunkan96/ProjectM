# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from event_bus import NormalizedEvent
from signal_extractor import ExtractedSignals


@dataclass
class GoalSnapshot:
    goal: str = "casual"
    confidence: float = 0.4
    reason: str = "default"


class ConversationGoalManager:
    """Понимает цель диалога: тест, поддержка, история, спор, память."""

    def detect(self, event: NormalizedEvent, signals: ExtractedSignals, scene_state: dict[str, Any] | None = None) -> GoalSnapshot:
        text = (event.text or "").lower().replace("ё", "е")
        if signals.intent == "memory_recall" or signals.memory_intent != "none":
            return GoalSnapshot("memory", 0.9, "memory_intent")
        if any(x in text for x in ["тест", "провер", "сломал", "баг", "почини"]):
            return GoalSnapshot("test_repair", 0.85, "debug_language")
        if any(x in text for x in ["мне плохо", "устал", "грустно", "поддержи", "херово"]):
            return GoalSnapshot("support", 0.85, "support_language")
        if signals.topic == "история" or (scene_state or {}).get("story_focus"):
            return GoalSnapshot("story", 0.85, "story_context")
        if any(x in text for x in ["врешь", "врёшь", "неправда", "выдумала", "ошибка"]):
            return GoalSnapshot("repair", 0.8, "contradiction_or_correction")
        if event.source in {"chat", "donation", "screen"}:
            return GoalSnapshot("stream_react", 0.7, "stream_source")
        return GoalSnapshot("casual", 0.45, "default")


@dataclass
class TopicStatus:
    topic: str = ""
    status: str = "none"
    turns_left: int = 0
    notes: list[str] = field(default_factory=list)


class TopicLifecycle:
    """Тема имеет статус, а не просто строку в prompt."""

    def update(self, scene_state: dict[str, Any] | None, signals: ExtractedSignals, user_text: str) -> TopicStatus:
        scene_state = scene_state or {}
        text = (user_text or "").lower().replace("ё", "е")
        topic = signals.topic or str(scene_state.get("topic") or "")
        rejected = set((scene_state.get("rejected_topics") or {}).keys()) if isinstance(scene_state.get("rejected_topics"), dict) else set()
        if any(x in text for x in ["забудь", "отстань", "хватит", "не об этом", "сменим тему"]):
            return TopicStatus(topic=topic, status="rejected", turns_left=5, notes=["не возвращать без прямой просьбы"])
        if topic and topic in rejected:
            return TopicStatus(topic=topic, status="rejected", turns_left=3, notes=["тема была отвергнута"])
        if any(x in text for x in ["ну всё", "закрыли", "ладно дальше"]):
            return TopicStatus(topic=topic, status="closed", turns_left=2, notes=["тема завершена"])
        if topic:
            return TopicStatus(topic=topic, status="active", turns_left=4, notes=["держать, пока пользователь не сменит"])
        return TopicStatus()


@dataclass
class StorySnapshot:
    active: bool = False
    premise: str = ""
    open_threads: list[str] = field(default_factory=list)
    continuity_turns: int = 0


class SceneStoryManager:
    """Держит долгую сцену: место, персонажи, незакрытые элементы."""

    def update(self, scene_state: dict[str, Any] | None, event: NormalizedEvent, signals: ExtractedSignals) -> StorySnapshot:
        scene_state = scene_state or {}
        text = event.text or ""
        active = bool(scene_state.get("story_focus")) or signals.topic == "история"
        premise = str(scene_state.get("story_premise") or "")
        if signals.topic == "история" and text:
            premise = text[:240]
            active = True
        threads: list[str] = []
        low = text.lower().replace("ё", "е")
        for marker in ["лес", "пещер", "босс", "робот", "каньон", "звук", "двер", "кораб"]:
            if marker in low:
                threads.append(marker)
        continuity = int(scene_state.get("continuity_turns", 0) or 0)
        if active:
            continuity = max(continuity, 5)
        return StorySnapshot(active=active, premise=premise, open_threads=threads[:6], continuity_turns=continuity)

    def prompt_block(self, story: StorySnapshot) -> str:
        if not story.active:
            return ""
        lines = ["[STORY MANAGER]", f"- story_active=True, continuity_turns={story.continuity_turns}."]
        if story.premise:
            lines.append(f"- Текущая сцена/посыл: {story.premise}")
        if story.open_threads:
            lines.append("- Незакрытые элементы сцены: " + ", ".join(story.open_threads) + ".")
        lines.append("- Продолжай именно эту сцену, пока пользователь явно не остановит или не сменит тему.")
        return "\n".join(lines)

