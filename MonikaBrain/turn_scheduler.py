# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class TurnDecision:
    allow_followup: bool = False
    delay_seconds: float = 0.0
    reason: str = ""


class TurnScheduler:
    """Решает, можно ли Монике самой продолжить мысль или вкинуться при паузе."""

    def __init__(self):
        self.last_reply_at = 0.0

    def after_reply(self) -> None:
        self.last_reply_at = time.time()

    def maybe_followup(self, unfinished: bool, silence_seconds: float) -> TurnDecision:
        if unfinished and silence_seconds >= 2.5:
            return TurnDecision(True, 0.1, "незавершённая мысль")
        if silence_seconds >= 30.0:
            return TurnDecision(True, 0.0, "долгая пауза")
        return TurnDecision(False, 0.0, "нет причины")

