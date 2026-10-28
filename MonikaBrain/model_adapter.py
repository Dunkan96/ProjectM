# -*- coding: utf-8 -*-
from __future__ import annotations


class ModelAdapter:
    """Подстройка prompt/параметров под семейство LLM."""

    def __init__(self, model_name: str = ""):
        self.model_name = model_name or ""

    @property
    def family(self) -> str:
        low = self.model_name.lower()
        if "qwen" in low:
            return "qwen"
        if "gemma" in low:
            return "gemma"
        if "mistral" in low:
            return "mistral"
        return "generic"

    def system_prefix(self) -> str:
        if self.family == "qwen":
            return "/no_think\n"
        return ""

    def clamp_tokens(self, desired: int, latency_mode: str = "normal") -> int:
        desired = int(desired or 220)
        if latency_mode == "fast":
            return min(desired, 180)
        if latency_mode == "deep":
            return max(desired, 320)
        return desired

