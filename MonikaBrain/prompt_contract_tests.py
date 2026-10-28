# -*- coding: utf-8 -*-
from __future__ import annotations

from cognitive_postguard import CognitivePostGuard
from eval_cognitive_pipeline import build_conn
from cognitive_state_compiler import CognitiveStateCompiler


def run() -> None:
    compiler = CognitiveStateCompiler(build_conn())
    guard = CognitivePostGuard()
    state = compiler.compile(
        source="telegram",
        user_text="Моника, помнишь других людей?",
        person_id="Duncan",
        display_name="Дункан",
        role="creator",
        memory_facts=[],
    )
    bad = guard.assess("Да, помню какого-то загадочного киберсамурая.", "Моника, помнишь других людей?", state)
    if bad.ok:
        raise AssertionError("PostGuard должен ловить игнор PeopleModel")
    good = guard.assess("Да, вижу в памяти viewer123 и alex.", "Моника, помнишь других людей?", state)
    if not good.ok:
        raise AssertionError(f"PostGuard ошибочно заблокировал нормальный ответ: {good.reasons}")
    print("prompt contract tests ok")


if __name__ == "__main__":
    run()

