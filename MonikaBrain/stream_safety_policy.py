# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

from boundary_consent import BoundaryConsentDirector


@dataclass
class SafetyDecision:
    allowed: bool
    risk: str = "ok"
    safe_text: str = ""
    public_memory_allowed: bool = True


class StreamSafetyPolicy:
    """Поведенческая политика Twitch поверх regex-guard."""

    def __init__(self, guard=None):
        self.guard = guard
        self.boundary = BoundaryConsentDirector()

    def classify(
        self,
        text: str,
        role: str = "viewer",
        user_name: str = "",
        *,
        private_adult_mode: bool = False,
        source: str = "dialogue",
    ) -> SafetyDecision:
        boundary = self.boundary.classify(
            text,
            role=role,
            private_adult_mode=private_adult_mode,
            source=source,
        )
        if not boundary.allowed:
            return SafetyDecision(
                False,
                boundary.risk,
                boundary.safe_text,
                public_memory_allowed=False,
            )
        if boundary.risk == "private_adult":
            return SafetyDecision(
                True,
                boundary.risk,
                text,
                public_memory_allowed=False,
            )
        if self.guard:
            verdict = self.guard.classify_message(text, user_role=role, user_name=user_name)
            if getattr(verdict, "block_send_to_llm", False):
                return SafetyDecision(False, getattr(verdict, "risk", "safety_bait"), getattr(verdict, "safe_text", ""))
        low = (text or "").lower().replace("ё", "е")
        public_memory_allowed = boundary.memory_allowed and not any(x in low for x in ["личное", "секрет", "адрес", "телефон"])
        return SafetyDecision(True, boundary.risk, text, public_memory_allowed=public_memory_allowed)
