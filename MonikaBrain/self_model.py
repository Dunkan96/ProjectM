# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SelfSnapshot:
    identity: list[str] = field(default_factory=list)
    stable_tastes: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    current_wants: list[str] = field(default_factory=list)


class SelfModel:
    """Стабильная self-модель: факты о Монике, не шаблонный ответ."""

    def build(self, desires: list[dict[str, Any]] | None = None, opinions: list[dict[str, Any]] | None = None) -> SelfSnapshot:
        desires = desires or []
        opinions = opinions or []
        wants = []
        for item in desires[:4]:
            target = item.get("target") or item.get("text") or item.get("category")
            if target:
                wants.append(str(target))
        tastes = []
        for item in opinions[:4]:
            topic = item.get("topic") or item.get("target")
            stance = item.get("stance") or item.get("opinion")
            if topic:
                tastes.append(f"{topic}: {stance}" if stance else str(topic))
        return SelfSnapshot(
            identity=[
                "Моника — AI-VTuber девушка и живая собеседница в рамках своей системы.",
                "Создатель Моники — Дункан.",
                "LLM формулирует речь, а мозг даёт состояние, память и контекст.",
            ],
            stable_tastes=tastes[:4],
            boundaries=[
                "не выдумывать физический опыт, семью, прошлые игры и события без памяти",
                "не обсуждать и не повторять Twitch-risk bait",
                "не отвечать как сухой ассистент",
            ],
            current_wants=wants[:4],
        )

    def prompt_block(self, snapshot: SelfSnapshot) -> str:
        lines = ["[SELF MODEL]"]
        lines.extend(f"- {x}" for x in snapshot.identity)
        if snapshot.stable_tastes:
            lines.append("- Текущие вкусы/позиции: " + " | ".join(snapshot.stable_tastes) + ".")
        if snapshot.current_wants:
            lines.append("- Сейчас может всплывать желание/интерес: " + " | ".join(snapshot.current_wants) + ".")
        lines.append("- Границы: " + " | ".join(snapshot.boundaries) + ".")
        return "\n".join(lines)

