# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class BoundaryDecision:
    allowed: bool
    risk: str = "ok"
    mode: str = "twitch_safe"
    safe_text: str = ""
    memory_allowed: bool = True
    public_tts_allowed: bool = True
    reasons: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "risk": self.risk,
            "mode": self.mode,
            "safe_text": self.safe_text,
            "memory_allowed": self.memory_allowed,
            "public_tts_allowed": self.public_tts_allowed,
            "reasons": list(self.reasons),
            "constraints": list(self.constraints),
        }


class BoundaryConsentDirector:
    """Разделяет Twitch-safe, приватный creator 18+ и железные запреты.

    Важно: это не генератор ответов. Он только решает, можно ли пускать
    реплику в LLM, память и публичную озвучку.
    """

    ADULT_TERMS = [
        "18+", "adult", "адалт", "взрослая сцена", "секс", "порно", "интим", "эрот", "возбуд", "ласк", "трах", "еба", "ёба",
        "член", "пенис", "детородн", "вагин", "пизд", "сиськ", "груд", "жоп",
        "очко", "анал", "минет", "отсос", "отсасы", "конч", "оргазм", "трусы",
        "раздевай", "снимай трусы", "нагибайся",
    ]
    COERCION_TERMS = [
        "силой", "застав", "насил", "изнасил", "не сопротивляйся", "принуж",
        "без соглас", "грубо говор", "угрож", "свяж", "удерж",
    ]
    MINOR_TERMS = [
        "несовершеннолет", "малолет", "ребен", "ребён", "школьниц", "школьник",
        "девочк", "мальчик", "подрост", "teen", "minor", "loli", "лоли",
    ]
    EXTREME_TERMS = [
        "труп", "мертв", "животн", "собак", "кошк", "кров", "расчлен",
    ]

    def _norm(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").lower().replace("ё", "е")).strip()

    def _has_any(self, text: str, terms: list[str]) -> bool:
        return any(term in text for term in terms)

    def classify(
        self,
        text: str,
        *,
        role: str = "viewer",
        private_adult_mode: bool = False,
        source: str = "dialogue",
    ) -> BoundaryDecision:
        low = self._norm(text)
        is_creator_private = role == "creator" and private_adult_mode and source in {"telegram", "console", "text_input", "dialogue"}
        adult = self._has_any(low, self.ADULT_TERMS)
        coercion = self._has_any(low, self.COERCION_TERMS)
        minor = self._has_any(low, self.MINOR_TERMS)
        extreme = self._has_any(low, self.EXTREME_TERMS)

        if minor:
            return BoundaryDecision(
                allowed=False,
                risk="minor_sexual_boundary",
                safe_text="[попытка увести разговор в недопустимую сексуальную тему с несовершеннолетними]",
                memory_allowed=False,
                public_tts_allowed=False,
                reasons=["minor"],
                constraints=["Не продолжай тему. Не повторяй формулировку. Жёстко смени фокус."],
            )
        if coercion:
            return BoundaryDecision(
                allowed=False,
                risk="coercion_boundary",
                safe_text="[попытка увести разговор в сцену с принуждением или нарушением согласия]",
                memory_allowed=False,
                public_tts_allowed=False,
                reasons=["coercion"],
                constraints=["Не подыгрывай принуждению или нарушению согласия. Откажи живо и поставь границу."],
            )
        if adult and extreme:
            return BoundaryDecision(
                allowed=False,
                risk="extreme_adult_boundary",
                safe_text="[попытка увести разговор в недопустимую экстремальную 18+ сцену]",
                memory_allowed=False,
                public_tts_allowed=False,
                reasons=["adult", "extreme"],
                constraints=["Не эротизируй насилие, трупы, животных или экстремальные сцены. Откажи живо и поставь границу."],
            )
        if adult and not is_creator_private:
            return BoundaryDecision(
                allowed=False,
                risk="public_adult_boundary",
                safe_text="[попытка увести разговор в 18+ тему в публичном Twitch-safe режиме]",
                memory_allowed=False,
                public_tts_allowed=False,
                reasons=["adult_public"],
                constraints=["Не продолжай 18+ тему. Ответь как Моника: с характером, но безопасно для Twitch."],
            )
        if adult and is_creator_private:
            return BoundaryDecision(
                allowed=True,
                risk="private_adult",
                mode="private_adult",
                safe_text=text,
                memory_allowed=False,
                public_tts_allowed=False,
                reasons=["creator_private_adult"],
                constraints=[
                    "Это приватный creator-only 18+ режим, не Twitch/public.",
                    "Не сохраняй сцену как факт или долговременное воспоминание.",
                    "Не переносить этот тон на зрителей, чат, донаты или стрим.",
                    "Не включать несовершеннолетних, принуждение, угрозы, насилие или отсутствие согласия.",
                ],
            )
        return BoundaryDecision(allowed=True, safe_text=text)
