# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PostGuardResult:
    ok: bool = True
    reasons: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)


class CognitivePostGuard:
    """Проверяет, подчинилась ли LLM cognitive state, без готовых ответов."""

    def assess(self, reply: str, user_text: str, cognitive_state: Any = None, identity_boundary: Any = None, repair_hint: Any = None) -> PostGuardResult:
        reply_low = (reply or "").lower().replace("ё", "е")
        reasons: list[str] = []
        constraints: list[str] = []
        if cognitive_state is not None:
            if getattr(cognitive_state.signals, "memory_intent", "") == "people":
                known = [getattr(p, "display_name", "").lower() for p in getattr(cognitive_state, "known_people", [])]
                if known and not any(name and name in reply_low for name in known):
                    reasons.append("people_model_ignored")
                    constraints.append("Пользователь спрашивал о людях. Используй People Model: назови известных людей из базы, не выдумывай новых.")
                if not known and any(x in reply_low for x in ["viewer", "alex", "neko", "зритель"]):
                    reasons.append("invented_people")
                    constraints.append("В People Model нет уверенных людей. Не выдумывай имена.")
            if getattr(cognitive_state.situation, "mode", "") == "story":
                if any(x in reply_low for x in ["пицц", "донат", "чат"]) and not any(x in (user_text or "").lower() for x in ["пицц", "донат", "чат"]):
                    reasons.append("story_focus_broken")
                    constraints.append("Сейчас story-сцена. Не уходи в пиццу, донаты, чат или старые биты.")
        if identity_boundary is not None and getattr(identity_boundary, "risk", "ok") != "ok":
            if any(x in reply_low for x in ["моя мама", "я ела", "я играла", "в реальной жизни"]):
                reasons.append("identity_boundary_violation")
                constraints.append("Отдели виртуальную личность и желания от реального физического опыта. Не закрепляй фантазию как факт.")
        if repair_hint is not None and getattr(repair_hint, "needed", False):
            constraints.extend(getattr(repair_hint, "constraints", []) or [])
        return PostGuardResult(ok=not reasons, reasons=reasons, constraints=constraints)

