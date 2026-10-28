# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PromptSection:
    name: str
    text: str
    priority: int = 50


class PromptBudgetManager:
    """Simple deterministic prompt budget. Keeps high-priority contracts and trims noisy context first."""

    def fit(self, sections: list[PromptSection], max_chars: int = 16000) -> str:
        if max_chars <= 0:
            return "\n\n".join(s.text for s in sections if s.text)
        ordered = sorted(
            [s for s in sections if (s.text or "").strip()],
            key=lambda s: s.priority,
            reverse=True,
        )
        kept: list[PromptSection] = []
        used = 0
        for section in ordered:
            text = section.text.strip()
            if used + len(text) + 2 <= max_chars:
                kept.append(section)
                used += len(text) + 2
                continue
            if section.priority >= 90:
                room = max(400, max_chars - used - 80)
                kept.append(PromptSection(section.name, text[:room].rstrip() + "\n[...trimmed...]", section.priority))
                break
        # Restore approximate original reading order among kept sections.
        name_to_index = {id(s): i for i, s in enumerate(sections)}
        kept.sort(key=lambda s: name_to_index.get(id(s), 9999))
        return "\n\n".join(s.text for s in kept if s.text)

    def fit_text(self, prompt: str, max_chars: int = 16000, keep_head: int = 6000) -> str:
        prompt = prompt or ""
        if len(prompt) <= max_chars:
            return prompt
        keep_head = min(max(1000, keep_head), max_chars - 1000)
        tail = max_chars - keep_head - 80
        return prompt[:keep_head].rstrip() + "\n\n[...prompt budget trimmed middle...]\n\n" + prompt[-tail:].lstrip()

