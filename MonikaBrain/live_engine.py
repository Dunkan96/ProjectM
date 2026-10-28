from __future__ import annotations

import math
import random
import time
from collections import deque
from typing import Any, Dict, List, Optional

from anticipation_engine import AnticipationEngine
from dialogue_continuity import DialogueContinuity
from emotional_memory import EmotionalMemory


class MoodSystem:
    def __init__(self):
        self.phase = random.random() * math.pi * 2
        self.base_mood = "neutral"
        self.intensity = 0.5
        self.last_update = time.time()

    def update(self, user_energy: str = "steady", social_intent: str = "neutral_chat") -> Dict[str, Any]:
        now = time.time()
        delta = max(0.0, min(60.0, now - self.last_update))
        self.last_update = now
        self.phase += delta * 0.012
        wave = math.sin(self.phase) * 0.12
        target = 0.5 + wave
        if user_energy == "high":
            target += 0.12
            self.base_mood = "playful"
        elif user_energy == "low" or social_intent == "needs_support":
            target -= 0.08
            self.base_mood = "soft"
        elif social_intent == "complaint":
            target -= 0.04
            self.base_mood = "careful"
        else:
            if abs(target - 0.5) < 0.08:
                self.base_mood = "neutral"
        self.intensity = max(0.15, min(1.0, target))
        return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        return {"base_mood": self.base_mood, "intensity": round(self.intensity, 3)}


class InterestEngine:
    def __init__(self):
        self.topic_counts: Dict[str, int] = {}
        self.recent_topics: deque[str] = deque(maxlen=8)
        self.boredom = 0.0

    def observe(self, topic: Optional[str], rejected_topics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rejected_topics = rejected_topics or {}
        if topic:
            self.recent_topics.append(topic)
            self.topic_counts[topic] = self.topic_counts.get(topic, 0) + 1
            repeats = list(self.recent_topics).count(topic)
            self.boredom = min(1.0, self.boredom + 0.12 * max(0, repeats - 2))
        else:
            self.boredom = max(0.0, self.boredom - 0.08)

        # Принудительный сброс boredom когда темы отвергаются
        if rejected_topics:
            self.boredom = max(0.0, self.boredom - 0.35)

        for rejected in rejected_topics:
            self.topic_counts[rejected] = max(0, self.topic_counts.get(rejected, 0) - 2)
            if rejected in self.recent_topics:
                self.boredom = min(1.0, self.boredom + 0.2)

        return self.snapshot()

    def should_suppress_topic(self, topic: Optional[str]) -> bool:
        if not topic:
            return False
        return self.topic_counts.get(topic, 0) >= 5 or self.boredom >= 0.68

    def snapshot(self) -> Dict[str, Any]:
        return {
            "boredom": round(self.boredom, 3),
            "recent_topics": list(self.recent_topics),
            "topic_counts": dict(sorted(self.topic_counts.items(), key=lambda item: item[1], reverse=True)[:5]),
        }


class RhythmEngine:
    def __init__(self):
        self.last_turn_at: Optional[float] = None
        self.turn_intervals: deque[float] = deque(maxlen=8)

    def observe_turn(self) -> Dict[str, Any]:
        now = time.time()
        if self.last_turn_at is not None:
            self.turn_intervals.append(max(0.0, now - self.last_turn_at))
        self.last_turn_at = now
        return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        if not self.turn_intervals:
            return {"tempo": "unknown", "avg_interval": None}
        avg = sum(self.turn_intervals) / len(self.turn_intervals)
        if avg < 8:
            tempo = "fast"
        elif avg < 25:
            tempo = "normal"
        else:
            tempo = "slow"
        return {"tempo": tempo, "avg_interval": round(avg, 2)}


class LiveEngine:
    """Coordinator layer for live-feeling behavior without replacing the brain."""

    def __init__(self, conn):
        self.emotional_memory = EmotionalMemory(conn)
        self.dialogue_continuity = DialogueContinuity(conn)
        self.anticipation = AnticipationEngine()
        self.mood = MoodSystem()
        self.interest = InterestEngine()
        self.rhythm = RhythmEngine()
        self.session_ids: Dict[str, int] = {}
        self.last_decision: Dict[str, Any] = {}

    def start_session(self, person_id: str) -> int:
        if person_id not in self.session_ids:
            self.session_ids[person_id] = self.dialogue_continuity.start_session(person_id)
        return self.session_ids[person_id]

    def update_session(self, person_id: str, messages: List[Dict[str, str]]) -> None:
        session_id = self.start_session(person_id)
        self.dialogue_continuity.update_session(session_id, messages)

    def before_plan(
        self,
        person_id: str,
        role: str,
        user_message: str,
        scene_state: Dict[str, Any],
        relationship_state: Optional[Dict[str, Any]],
        topic: Optional[str],
        social_intent: str,
        stream_mode: bool = False,
    ) -> Dict[str, Any]:
        rhythm = self.rhythm.observe_turn()
        mood = self.mood.update(user_energy=scene_state.get("user_energy", "steady"), social_intent=social_intent)
        interest = self.interest.observe(topic, rejected_topics=scene_state.get("rejected_topics") or {})
        anticipation = self.anticipation.observe_user_message(person_id, user_message, topic=topic)
        return_hook = self.anticipation.get_return_hook(role, float(anticipation.get("absence_seconds") or 0.0))
        emotional_hint = self.emotional_memory.get_grudge_or_warmth(person_id)

        suppress_topic = topic if self.interest.should_suppress_topic(topic) else None
        decision = {
            "mood": mood,
            "rhythm": rhythm,
            "interest": interest,
            "anticipation": anticipation,
            "return_hook": return_hook,
            "emotional_hint": emotional_hint,
            "suppress_topic": suppress_topic,
            "stream_mode": stream_mode,
        }
        self.last_decision = decision
        return decision

    def after_turn(self, person_id: str, user_message: str, monika_reply: str, social_intent: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        emotional_event = self.emotional_memory.observe_turn(person_id, user_message, monika_reply, social_intent=social_intent)
        self.update_session(person_id, messages)
        result = {
            "emotional_event": emotional_event,
            "session_updated": bool(messages),
        }
        return result

    def build_prompt_block(self, person_id: str) -> str:
        parts = []
        mood = self.mood.snapshot()
        rhythm = self.rhythm.snapshot()
        interest = self.interest.snapshot()
        parts.append("[LIVE ENGINE]")
        parts.append(f"- Настроение-фон: {mood['base_mood']} / {mood['intensity']}.")
        if rhythm.get("tempo") != "unknown":
            parts.append(f"- Темп диалога: {rhythm['tempo']} (средний интервал {rhythm['avg_interval']} сек).")
        if interest.get("boredom", 0.0) >= 0.55:
            parts.append("- Есть риск залипания темы. Если пользователь сменил контекст, отпусти старый якорь.")
        anticipation = self.anticipation.build_prompt_block()
        if anticipation:
            parts.append(anticipation)
        emotional = self.emotional_memory.build_prompt_block(person_id, limit=3)
        if emotional:
            parts.append(emotional)
        continuity = self.dialogue_continuity.build_prompt_block(person_id)
        if continuity:
            parts.append(continuity)
        return "\n".join(parts)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "mood": self.mood.snapshot(),
            "rhythm": self.rhythm.snapshot(),
            "interest": self.interest.snapshot(),
            "anticipation": {
                "surprise_level": round(self.anticipation.surprise_level, 3),
                "expected_topics": list(self.anticipation.expected_topics)[-3:],
            },
            "last_decision": self.last_decision,
        }
