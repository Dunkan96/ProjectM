# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3

from cognitive_state_compiler import CognitiveStateCompiler
from response_policy import ResponsePolicy


def build_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE relationship_state (
            person_id TEXT PRIMARY KEY,
            display_name TEXT,
            role TEXT,
            affection REAL,
            irritation REAL,
            familiarity REAL,
            message_count INTEGER,
            last_seen TEXT
        )
        """
    )
    conn.execute("INSERT INTO relationship_state VALUES ('viewer123','viewer123','viewer',0.2,0.1,0.5,12,datetime('now'))")
    conn.execute("INSERT INTO relationship_state VALUES ('alex','alex','viewer',0.5,0.0,0.7,4,datetime('now'))")
    return conn


def run() -> None:
    compiler = CognitiveStateCompiler(build_conn())
    policy = ResponsePolicy()
    cases = [
        ("telegram", "Моника, помнишь других людей?", "people_memory"),
        ("donation", "alex 300р: купи себе энергетик", "donation"),
        ("chat", "ахах он сейчас умрёт", None),
        ("screen", "на экране появился огромный босс", None),
        ("telegram", "Стоп, не продолжай", "interrupt"),
    ]
    for source, text, expected_mode in cases:
        state = compiler.compile(
            source=source,
            user_text=text,
            person_id="Duncan",
            display_name="Дункан",
            role="creator" if source == "telegram" else "viewer",
            priority=90,
            memory_facts=[],
        )
        decision = policy.decide(state)
        if expected_mode and decision.mode != expected_mode:
            raise AssertionError(f"{text!r}: expected {expected_mode}, got {decision.mode}")
        if "людей" in text and not state.known_people:
            raise AssertionError("people recall did not include known people")
        print(f"OK {source}: intent={state.signals.intent}, memory={state.signals.memory_intent}, mode={decision.mode}")


if __name__ == "__main__":
    run()

