# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ActionPlan:
    text: str = ""
    emotion: str = "Neutral"
    gesture: str = "none"
    eyes: str = "normal"
    tts_style: str = "normal"
    moderation: str = "none"
    obs_actions: list[str] = field(default_factory=list)


class ActionLayer:
    """Единый контракт выхода: речь + эмоция + будущие действия Streamer.bot/OBS."""

    def plan(self, reply: str, response_decision=None, emotion: dict | None = None) -> ActionPlan:
        emotion = emotion or {}
        return ActionPlan(
            text=reply,
            emotion=str(emotion.get("avatar_emotion") or emotion.get("avatar") or "Neutral"),
            tts_style=str(getattr(response_decision, "tts_style", "normal") or "normal"),
            gesture="small_react" if getattr(response_decision, "mode", "") in {"donation", "fast_react"} else "none",
        )

