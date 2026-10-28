# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class EmotionDecision:
    emotion_label: str = "steady"
    intensity: float = 0.35
    stance: str = "react"
    hold_turns: int = 1
    avatar_emotion: str = "Happy"
    voice_style: str = "natural"
    lock_old_bits: bool = False
    suppress_background_layers: bool = False
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EmotionDirector:
    """Arbitrates Monika's emotional stance above stage/social/live layers.

    This class does not generate replies. It chooses the emotional line, stance,
    and which background layers should stay quiet so the active scene is not
    interrupted by stale nicknames, old jokes, or unrelated desires.
    """

    STRONG_STAGE_STANCES = {
        "STORY": ("curious_tension", "continue_story", "Surprised", "dramatic", 7),
        "STORY_SETUP": ("curious_tension", "continue_story", "Surprised", "dramatic", 6),
        "STORY_CONTINUE": ("curious_tension", "continue_story", "Surprised", "dramatic", 5),
        "INTERRUPT": ("scene_stop", "stop", "Suspicious", "clear", 1),
        "GAME_COACH": ("focused_pressure", "coach", "Angry", "quick", 3),
        "RECOVER": ("careful_repair", "repair", "Embarrassed", "warm", 2),
        "RECOVER_DIRECT_ADDRESS": ("careful_repair", "repair", "Embarrassed", "warm", 2),
        "MEMORY": ("focused_recall", "answer_factually", "Suspicious", "clear", 1),
        "GRIEVANCE_LIST": ("mock_offended", "tease_list", "Angry", "theatrical", 3),
        "REFUSAL_BANTER": ("playful_pushback", "refuse", "Suspicious", "sharp", 2),
        "EVENT_RIFF": ("chaotic_excited", "riff", "Surprised", "animated", 3),
        "SOFT_ATTACH": ("soft_attach", "attach", "Embarrassed", "soft", 3),
        "NAME_PLAY": ("playful_smug", "nameplay", "Happy", "quick", 2),
        "BANTER": ("playful_smug", "tease", "Happy", "quick", 2),
        "OPINION": ("opinionated", "take_position", "Suspicious", "clear", 2),
    }

    def decide(
        self,
        user_input: str,
        stage_decision: Any = None,
        behavior_plan: Any = None,
        relationship_state: dict[str, Any] | None = None,
        scene_state: dict[str, Any] | None = None,
        stream_mode: bool = False,
    ) -> EmotionDecision:
        text = str(user_input or "")
        lower = text.lower().replace("ё", "е")
        stage = self._stage_name(stage_decision)
        state = scene_state or {}
        relationship_state = relationship_state or {}
        reasons: list[str] = []

        active_arc = self._active_arc(state)
        if active_arc and not self._explicit_scene_break(lower):
            decision = EmotionDecision(
                emotion_label=active_arc.get("emotion_label", "steady"),
                intensity=float(active_arc.get("intensity", 0.45) or 0.45),
                stance=active_arc.get("stance", "react"),
                hold_turns=max(1, int(active_arc.get("turns_left", 1) or 1)),
                avatar_emotion=active_arc.get("avatar_emotion", "Happy"),
                voice_style=active_arc.get("voice_style", "natural"),
                lock_old_bits=bool(active_arc.get("lock_old_bits", False)),
                suppress_background_layers=bool(active_arc.get("suppress_background_layers", False)),
                reasons=["active_emotion_arc"],
            )
            return self._with_current_overrides(decision, lower, stage, stream_mode, relationship_state)

        if stage in self.STRONG_STAGE_STANCES:
            emotion, stance, avatar, voice, hold = self.STRONG_STAGE_STANCES[stage]
            reasons.append(f"stage:{stage}")
            lock_old = stage in {"STORY", "STORY_SETUP", "STORY_CONTINUE", "INTERRUPT", "GAME_COACH", "RECOVER", "RECOVER_DIRECT_ADDRESS", "MEMORY"}
            suppress_background = stage in {"STORY", "STORY_SETUP", "STORY_CONTINUE", "INTERRUPT", "GAME_COACH", "RECOVER", "RECOVER_DIRECT_ADDRESS", "MEMORY"}
            decision = EmotionDecision(
                emotion_label=emotion,
                intensity=0.62 if stage != "MEMORY" else 0.45,
                stance=stance,
                hold_turns=hold,
                avatar_emotion=avatar,
                voice_style=voice,
                lock_old_bits=lock_old,
                suppress_background_layers=suppress_background,
                reasons=reasons,
            )
            return self._with_current_overrides(decision, lower, stage, stream_mode, relationship_state)

        social_intent = str(getattr(behavior_plan, "social_intent", "") or "")
        if social_intent == "needs_support" or any(x in lower for x in ["устал", "плохо", "херово", "не легче", "расстроен"]):
            return EmotionDecision("soft_care", 0.58, "support", 2, "Sad", "warm", True, True, ["support"])
        if any(x in lower for x in ["стрима пока", "стрима нет", "вдвоем общаемся", "вдвоём общаемся", "чисто вдвоем", "чисто вдвоём"]):
            return EmotionDecision("private_chat_focus", 0.52, "personal_focus", 3, "Happy", "natural", True, True, ["private_chat_correction"])
        if any(x in lower for x in ["давай поговорим про", "поговорим о", "поговорим про", "сменим тему на"]):
            return EmotionDecision("topic_shift_focus", 0.50, "take_current_topic", 3, "Suspicious", "clear", True, True, ["explicit_topic_shift"])
        if any(x in lower for x in ["ахах", "ору", "угар", "кринж"]):
            return EmotionDecision("playful_warmth", 0.55, "riff", 2, "Happy", "quick", False, False, ["shared_laugh"])
        if stream_mode:
            return EmotionDecision("stream_focus", 0.50, "select_focus", 2, "Surprised", "quick", True, True, ["stream"])

        irritation = float(relationship_state.get("irritation", 0.0) or 0.0)
        if irritation >= 0.55:
            return EmotionDecision("prickly", 0.48, "pushback", 1, "Suspicious", "sharp", False, False, ["relationship_irritation"])

        return EmotionDecision(reasons=["default"])

    def apply_to_plan(self, behavior_plan: Any, decision: EmotionDecision) -> None:
        if behavior_plan is None:
            return
        try:
            if decision.stance in {"continue_story", "riff", "tease_list"}:
                behavior_plan.max_sentences = max(int(getattr(behavior_plan, "max_sentences", 3) or 3), 4)
                behavior_plan.max_tokens = max(int(getattr(behavior_plan, "max_tokens", 220) or 220), 280)
            if decision.stance == "stop":
                behavior_plan.max_sentences = 1
                behavior_plan.max_tokens = min(int(getattr(behavior_plan, "max_tokens", 120) or 120), 90)
                behavior_plan.initiative_allowed = False
            if decision.stance in {"coach", "select_focus"}:
                behavior_plan.max_sentences = min(max(int(getattr(behavior_plan, "max_sentences", 3) or 3), 2), 4)
            if decision.stance in {"personal_focus", "take_current_topic"}:
                behavior_plan.max_sentences = max(int(getattr(behavior_plan, "max_sentences", 3) or 3), 3)
                behavior_plan.max_tokens = max(int(getattr(behavior_plan, "max_tokens", 220) or 220), 240)
            if decision.stance in {"repair", "support", "answer_factually"}:
                behavior_plan.allow_tease = False
                behavior_plan.require_softness = decision.stance in {"repair", "support"}
            if decision.stance in {"tease", "playful_pushback", "refuse", "nameplay"}:
                behavior_plan.allow_tease = True
            behavior_plan.presence_penalty_bias = max(float(getattr(behavior_plan, "presence_penalty_bias", 0.0) or 0.0), 0.06)
        except Exception:
            return

    def update_arc(self, scene_state: dict[str, Any] | None, decision: EmotionDecision, user_input: str = "") -> dict[str, Any]:
        state = dict(scene_state or {})
        lower = str(user_input or "").lower().replace("ё", "е")
        if self._explicit_scene_break(lower) or decision.hold_turns <= 1:
            state["emotion_arc"] = {}
            return state
        state["emotion_arc"] = {
            "emotion_label": decision.emotion_label,
            "intensity": decision.intensity,
            "stance": decision.stance,
            "turns_left": max(0, int(decision.hold_turns) - 1),
            "avatar_emotion": decision.avatar_emotion,
            "voice_style": decision.voice_style,
            "lock_old_bits": decision.lock_old_bits,
            "suppress_background_layers": decision.suppress_background_layers,
        }
        return state

    def after_turn(self, scene_state: dict[str, Any] | None) -> dict[str, Any]:
        state = dict(scene_state or {})
        arc = dict(state.get("emotion_arc") or {})
        if arc:
            turns_left = max(0, int(arc.get("turns_left", 0) or 0) - 1)
            if turns_left <= 0:
                state["emotion_arc"] = {}
            else:
                arc["turns_left"] = turns_left
                arc["intensity"] = max(0.2, float(arc.get("intensity", 0.4) or 0.4) * 0.86)
                state["emotion_arc"] = arc
        return state

    def build_prompt_block(self, decision: EmotionDecision | dict[str, Any]) -> str:
        data = decision if isinstance(decision, dict) else decision.to_dict()
        lines = ["[EMOTION DIRECTOR]"]
        lines.append(f"- Эмоция сцены: {data.get('emotion_label', 'steady')} ({float(data.get('intensity', 0.35) or 0.35):.2f}).")
        lines.append(f"- Позиция Моники: {data.get('stance', 'react')}.")
        lines.append(f"- Голосовая подача: {data.get('voice_style', 'natural')}.")
        if data.get("lock_old_bits"):
            lines.append("- Старые клички, старые шутки и прошлые темы не перебивают текущую сцену.")
        if data.get("suppress_background_layers"):
            lines.append("- Желания, мнения и социальные биты используй только если они прямо помогают текущей сцене.")
        lines.append("- Не проговаривай этот блок. Просто держи эмоциональную линию и выбранную позицию.")
        return "\n".join(lines)

    def _stage_name(self, stage_decision: Any) -> str:
        if isinstance(stage_decision, dict):
            return str(stage_decision.get("stage") or "").upper()
        return str(getattr(stage_decision, "stage", "") or "").upper()

    def _active_arc(self, scene_state: dict[str, Any]) -> dict[str, Any]:
        arc = scene_state.get("emotion_arc") if isinstance(scene_state, dict) else None
        if not isinstance(arc, dict):
            return {}
        if int(arc.get("turns_left", 0) or 0) <= 0:
            return {}
        return arc

    def _explicit_scene_break(self, lower: str) -> bool:
        return any(x in lower for x in [
            "стоп", "хватит", "новая тема", "сменим тему", "забудь", "не об этом",
            "вернемся", "вернёмся", "другой вопрос", "отстань с этой темой",
        ])

    def _with_current_overrides(
        self,
        decision: EmotionDecision,
        lower: str,
        stage: str,
        stream_mode: bool,
        relationship_state: dict[str, Any],
    ) -> EmotionDecision:
        if "?" in lower and stage not in {"STORY", "STORY_SETUP", "STORY_CONTINUE", "GAME_COACH", "GRIEVANCE_LIST"}:
            decision.lock_old_bits = True
        if any(x in lower for x in ["кто я", "как меня зовут", "что ты помнишь", "кто такой", "что знаешь обо мне"]):
            decision.stance = "answer_factually"
            decision.emotion_label = "focused_recall"
            decision.avatar_emotion = "Suspicious"
            decision.lock_old_bits = True
            decision.suppress_background_layers = True
            decision.hold_turns = 1
        if stream_mode:
            decision.voice_style = "quick"
        return decision
