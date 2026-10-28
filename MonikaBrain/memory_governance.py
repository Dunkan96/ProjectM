# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass


def _norm(text: str) -> str:
    return (text or "").lower().replace("ё", "е")


@dataclass
class MemoryGovernanceDecision:
    write_allowed: bool = True
    mode: str = "normal"
    reason: str = "normal"
    source_type: str = "dialogue"

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "write_allowed": self.write_allowed,
            "mode": self.mode,
            "reason": self.reason,
            "source_type": self.source_type,
        }


class MemoryGovernance:
    """Prevents jokes, repairs, private scenes and uncertain claims from becoming semantic facts."""

    JOKE_HINTS = ["шутка", "рофл", "мем", "кличк", "придумай", "ахах", "хаха"]
    REPAIR_HINTS = ["ты врешь", "ты врёшь", "выдумываешь", "не было", "ошибка", "сбой"]
    PRIVATE_HINTS = ["!18+", "!18-", "приват"]
    UNCERTAIN_HINTS = ["кажется", "наверное", "может быть", "вроде"]

    def decide(self, user_text: str, reply: str = "", *, contract=None, boundary_decision=None) -> MemoryGovernanceDecision:
        text = _norm(user_text)
        if boundary_decision is not None and not bool(getattr(boundary_decision, "memory_allowed", True)):
            return MemoryGovernanceDecision(False, "ephemeral", "boundary_consent", "private_or_boundary")
        if contract is not None:
            mode = str(getattr(contract, "memory_write_mode", "normal") or "normal")
            if mode in {"ephemeral", "joke_not_fact", "quarantine"}:
                return MemoryGovernanceDecision(mode != "ephemeral", mode, "turn_contract", mode)
        if any(x in text for x in self.PRIVATE_HINTS):
            return MemoryGovernanceDecision(False, "ephemeral", "private_command", "private")
        if any(x in text for x in self.JOKE_HINTS):
            return MemoryGovernanceDecision(True, "joke_not_fact", "joke_or_bit", "performance")
        if any(x in text for x in self.REPAIR_HINTS):
            return MemoryGovernanceDecision(False, "ephemeral", "repair_turn", "repair")
        if any(x in text for x in self.UNCERTAIN_HINTS):
            return MemoryGovernanceDecision(True, "quarantine", "uncertain_language", "uncertain")
        return MemoryGovernanceDecision(True, "normal", "normal", "dialogue")

