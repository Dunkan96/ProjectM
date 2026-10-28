# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class UnifiedEmotionalState:
    mood: str = "steady"
    intensity: float = 0.35
    stance: str = "react"
    valence: float = 0.0
    arousal: float = 0.35
    social_temperature: float = 0.5
    momentum: float = 0.0
    voice_style: str = "natural"
    avatar_emotion: str = "Happy"
    avatar_intensity: float = 0.45
    suppress_background_layers: bool = False
    lock_old_bits: bool = False
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EmotionalStateAggregator:
    """Unifies emotional signals so Monika follows one scene line.

    EmotionDirector chooses a stance for the current turn. Other systems
    (relationship, affection, live engine, scene memory) can disagree with it.
    This layer reconciles them into one final state for prompt/TTS/avatar and
    keeps a short emotional momentum without hardcoding reply text.
    """

    def build(
        self,
        user_input: str,
        emotion_decision: Any = None,
        behavior_plan: Any = None,
        stage_decision: Any = None,
        relationship_state: dict[str, Any] | None = None,
        affection_state: Any = None,
        live_decision: dict[str, Any] | None = None,
        scene_state: dict[str, Any] | None = None,
        stream_mode: bool = False,
    ) -> UnifiedEmotionalState:
        text = str(user_input or "").lower().replace("ё", "е")
        scene_state = scene_state or {}
        relationship_state = relationship_state or {}
        live_decision = live_decision or {}
        reasons: list[str] = []

        emotion = self._as_dict(emotion_decision)
        mood = str(emotion.get("emotion_label") or "steady")
        stance = str(emotion.get("stance") or "react")
        intensity = self._clamp(float(emotion.get("intensity", 0.35) or 0.35), 0.15, 1.0)
        voice_style = str(emotion.get("voice_style") or "natural")
        avatar = str(emotion.get("avatar_emotion") or "Happy")
        suppress_background = bool(emotion.get("suppress_background_layers", False))
        lock_old_bits = bool(emotion.get("lock_old_bits", False))
        reasons.extend([str(x) for x in emotion.get("reasons", []) if x])

        stage = self._stage_name(stage_decision)
        if stage:
            reasons.append(f"stage:{stage}")

        rel = self._relationship_numbers(relationship_state)
        social_temperature = self._social_temperature(rel, role=str(relationship_state.get("role") or ""))
        valence = self._clamp((social_temperature - 0.5) * 1.35, -1.0, 1.0)
        arousal = max(0.25, intensity)

        live_mood = self._live_mood(live_decision)
        if live_mood:
            reasons.append(f"live:{live_mood}")
            arousal = max(arousal, 0.5)
            if mood == "steady":
                mood = live_mood

        aff_mood = str(getattr(affection_state, "mood", "") or "")
        aff_intensity = self._safe_float(getattr(affection_state, "intensity", 0.0), 0.0)
        if aff_mood:
            reasons.append(f"affection:{aff_mood}")
        if aff_intensity > 0.35:
            arousal = max(arousal, min(0.8, aff_intensity))

        active = self._active_unified_arc(scene_state)
        if active and not self._explicit_break(text):
            reasons.append("unified_momentum")
            momentum = self._clamp(float(active.get("momentum", 0.35) or 0.35), 0.0, 1.0)
            if mood == "steady" or intensity < float(active.get("intensity", 0.35) or 0.35):
                mood = str(active.get("mood") or mood)
                stance = str(active.get("stance") or stance)
                voice_style = str(active.get("voice_style") or voice_style)
                avatar = str(active.get("avatar_emotion") or avatar)
                intensity = max(intensity, float(active.get("intensity", intensity) or intensity) * 0.88)
                suppress_background = suppress_background or bool(active.get("suppress_background_layers", False))
                lock_old_bits = lock_old_bits or bool(active.get("lock_old_bits", False))
        else:
            momentum = max(0.0, intensity - 0.2)

        if self._private_focus(text):
            mood = "private_chat_focus"
            stance = "personal_focus"
            voice_style = "natural"
            avatar = "Happy"
            intensity = max(intensity, 0.5)
            arousal = max(arousal, 0.42)
            suppress_background = True
            lock_old_bits = True
            reasons.append("private_focus")

        if self._support_signal(text):
            mood = "soft_care"
            stance = "support"
            voice_style = "warm"
            avatar = "Sad"
            intensity = max(intensity, 0.55)
            arousal = max(arousal, 0.48)
            suppress_background = True
            lock_old_bits = True
            social_temperature = max(social_temperature, 0.62)
            valence = max(valence, 0.2)
            reasons.append("support_signal")

        if self._topic_shift_signal(text):
            stance = "take_current_topic"
            suppress_background = True
            lock_old_bits = True
            reasons.append("explicit_topic_shift")

        if stream_mode:
            arousal = max(arousal, 0.5)
            if voice_style == "natural":
                voice_style = "quick"
            reasons.append("stream_mode")

        # Creator should not become cold just because one subsystem stored mild
        # irritation. Alliance/familiarity are treated as a warmth floor.
        if rel["alliance"] >= 0.75 and rel["familiarity"] >= 0.75 and rel["irritation"] < 0.65:
            social_temperature = max(social_temperature, 0.62)
            valence = max(valence, 0.18)
            reasons.append("creator_alliance_floor")

        avatar_intensity = self._clamp(max(intensity, arousal * 0.85), 0.2, 1.0)
        return UnifiedEmotionalState(
            mood=mood,
            intensity=self._clamp(intensity, 0.15, 1.0),
            stance=stance,
            valence=self._clamp(valence, -1.0, 1.0),
            arousal=self._clamp(arousal, 0.1, 1.0),
            social_temperature=self._clamp(social_temperature, 0.0, 1.0),
            momentum=self._clamp(momentum, 0.0, 1.0),
            voice_style=voice_style,
            avatar_emotion=avatar,
            avatar_intensity=avatar_intensity,
            suppress_background_layers=suppress_background,
            lock_old_bits=lock_old_bits,
            reasons=list(dict.fromkeys(reasons)),
        )

    def apply_to_plan(self, behavior_plan: Any, state: UnifiedEmotionalState) -> None:
        if behavior_plan is None:
            return
        try:
            if state.stance in {"support", "repair", "personal_focus"}:
                behavior_plan.allow_tease = state.stance == "personal_focus"
                behavior_plan.require_softness = state.stance in {"support", "repair"}
                behavior_plan.max_sentences = max(int(getattr(behavior_plan, "max_sentences", 3) or 3), 3)
            if state.stance in {"continue_story", "riff", "take_position"}:
                behavior_plan.max_sentences = max(int(getattr(behavior_plan, "max_sentences", 3) or 3), 4)
                behavior_plan.max_tokens = max(int(getattr(behavior_plan, "max_tokens", 220) or 220), 280)
            if state.suppress_background_layers:
                behavior_plan.initiative_allowed = False
        except Exception:
            return

    def update_scene_state(self, scene_state: dict[str, Any] | None, state: UnifiedEmotionalState, user_input: str = "") -> dict[str, Any]:
        result = dict(scene_state or {})
        if self._explicit_break(str(user_input or "").lower().replace("ё", "е")) or state.momentum < 0.25:
            result["unified_emotion"] = {}
            return result
        result["unified_emotion"] = {
            "mood": state.mood,
            "intensity": max(0.2, state.intensity * 0.9),
            "stance": state.stance,
            "voice_style": state.voice_style,
            "avatar_emotion": state.avatar_emotion,
            "suppress_background_layers": state.suppress_background_layers,
            "lock_old_bits": state.lock_old_bits,
            "momentum": state.momentum,
            "turns_left": 2 if state.intensity < 0.7 else 3,
        }
        return result

    def after_turn(self, scene_state: dict[str, Any] | None) -> dict[str, Any]:
        result = dict(scene_state or {})
        arc = dict(result.get("unified_emotion") or {})
        if not arc:
            return result
        turns_left = max(0, int(arc.get("turns_left", 0) or 0) - 1)
        if turns_left <= 0:
            result["unified_emotion"] = {}
            return result
        arc["turns_left"] = turns_left
        arc["intensity"] = max(0.18, float(arc.get("intensity", 0.35) or 0.35) * 0.84)
        arc["momentum"] = max(0.0, float(arc.get("momentum", 0.35) or 0.35) * 0.78)
        result["unified_emotion"] = arc
        return result

    def build_prompt_block(self, state: UnifiedEmotionalState | dict[str, Any]) -> str:
        data = state if isinstance(state, dict) else state.to_dict()
        lines = ["[UNIFIED EMOTIONAL STATE]"]
        lines.append(f"- Итоговый фон: {data.get('mood', 'steady')} / интенсивность {float(data.get('intensity', 0.35) or 0.35):.2f}.")
        lines.append(f"- Позиция в ответе: {data.get('stance', 'react')}.")
        lines.append(f"- Социальная температура: {float(data.get('social_temperature', 0.5) or 0.5):.2f}; валентность {float(data.get('valence', 0.0) or 0.0):.2f}.")
        lines.append(f"- Подача голоса: {data.get('voice_style', 'natural')}; аватар: {data.get('avatar_emotion', 'Happy')}.")
        if data.get("suppress_background_layers"):
            lines.append("- Не подтаскивай фоновые желания, старые шутки, старые клички и случайные темы, если пользователь их не поднял.")
        if data.get("lock_old_bits"):
            lines.append("- Текущая реплика важнее старых ассоциаций. Отвечай на неё напрямую и не перепрыгивай в прошлую сцену.")
        lines.append("- Не проговаривай этот блок. Он нужен только для внутреннего эмоционального курса.")
        return "\n".join(lines)

    def _relationship_numbers(self, state: dict[str, Any]) -> dict[str, float]:
        return {
            "affection": self._safe_float(state.get("affection", 0.0), 0.0),
            "trust": self._safe_float(state.get("trust", 0.0), 0.0),
            "irritation": self._safe_float(state.get("irritation", 0.0), 0.0),
            "alliance": self._safe_float(state.get("alliance", 0.0), 0.0),
            "familiarity": self._safe_float(state.get("familiarity", 0.0), 0.0),
        }

    def _social_temperature(self, rel: dict[str, float], role: str = "") -> float:
        base = 0.5 + rel["affection"] * 0.22 + rel["trust"] * 0.18 + rel["alliance"] * 0.16 + rel["familiarity"] * 0.10 - rel["irritation"] * 0.22
        if role == "creator":
            base += 0.08
        return self._clamp(base, 0.0, 1.0)

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_dict"):
            try:
                return value.to_dict()
            except Exception:
                pass
        return {k: getattr(value, k) for k in dir(value) if not k.startswith("_") and k in {
            "emotion_label", "intensity", "stance", "voice_style", "avatar_emotion",
            "suppress_background_layers", "lock_old_bits", "reasons",
        }}

    def _stage_name(self, stage_decision: Any) -> str:
        if isinstance(stage_decision, dict):
            return str(stage_decision.get("stage") or "").upper()
        return str(getattr(stage_decision, "stage", "") or "").upper()

    def _live_mood(self, live_decision: dict[str, Any]) -> str:
        mood = live_decision.get("mood") if isinstance(live_decision, dict) else None
        if isinstance(mood, dict):
            return str(mood.get("base_mood") or mood.get("mood") or "")
        return str(mood or "")

    def _active_unified_arc(self, scene_state: dict[str, Any]) -> dict[str, Any]:
        arc = scene_state.get("unified_emotion") if isinstance(scene_state, dict) else None
        if not isinstance(arc, dict):
            return {}
        if int(arc.get("turns_left", 0) or 0) <= 0:
            return {}
        return arc

    def _support_signal(self, text: str) -> bool:
        return any(x in text for x in ["устал", "плохо", "херово", "расстроен", "грустно", "тревожно", "не легче"])

    def _private_focus(self, text: str) -> bool:
        return any(x in text for x in ["стрима пока", "стрима нет", "вдвоем", "вдвоём", "не на стриме", "просто общаемся"])

    def _topic_shift_signal(self, text: str) -> bool:
        return any(x in text for x in ["давай поговорим про", "поговорим о", "смени тему", "новая тема"])

    def _explicit_break(self, text: str) -> bool:
        return any(x in text for x in ["стоп", "хватит", "забудь", "не об этом", "другая тема", "смени тему"])

    def _safe_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))
