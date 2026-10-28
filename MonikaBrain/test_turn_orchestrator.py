# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from answer_evaluator import AnswerEvaluator
from turn_orchestrator import TurnOrchestrator


def _state(*, mode="dialogue", memory_confidence="none", facts=None):
    return SimpleNamespace(
        event=SimpleNamespace(source="console", role="creator"),
        situation=SimpleNamespace(mode=mode),
        story=SimpleNamespace(status="active" if mode == "story" else "idle"),
        signals=SimpleNamespace(memory_intent="none", intent="reply"),
        memory=SimpleNamespace(confidence=memory_confidence, facts=facts or []),
        audience=SimpleNamespace(load="low"),
    )


def test_direct_identity_exits_story():
    orch = TurnOrchestrator()
    contract = orch.build(
        user_text="Кто ты?",
        source="console",
        role="creator",
        cognitive_state=_state(mode="story"),
        scene_state={"story_focus": "active"},
    )
    assert contract.primary_intent == "identity"
    assert contract.should_continue_story is False
    assert contract.scene_action == "exit_or_suspend_scene"


def test_story_continues_only_on_explicit_continue():
    orch = TurnOrchestrator()
    contract = orch.build(
        user_text="Продолжи дальше, Бип пошел в пещеру",
        source="console",
        role="creator",
        cognitive_state=_state(mode="story"),
        scene_state={"story_focus": "active"},
    )
    assert contract.primary_intent == "story_continue"
    assert contract.should_continue_story is True


def test_people_memory_disables_desires():
    orch = TurnOrchestrator()
    contract = orch.build(
        user_text="Ты помнишь других людей, которые тебе писали?",
        source="telegram",
        role="creator",
        cognitive_state=_state(),
        active_desires=[{"topic": "pizza"}],
    )
    assert contract.primary_intent == "memory_people"
    assert contract.allow_desires is False
    assert contract.memory_mode == "people_timeline"


def test_evaluator_catches_fake_people_list():
    evaluator = AnswerEvaluator()
    contract = TurnOrchestrator().build(
        user_text="Кто тебе писал? Назови имена",
        source="telegram",
        role="creator",
        cognitive_state=_state(memory_confidence="low", facts=[]),
    )
    ev = evaluator.evaluate(
        "Стримовый ведьмак, Кнопочный барон, Хаос-дирижёр.",
        "Кто тебе писал? Назови имена",
        contract=contract,
        cognitive_state=_state(memory_confidence="low", facts=[]),
        memory_facts=[],
    )
    assert not ev.ok
    assert "invented_people" in ev.reasons


def test_evaluator_catches_false_experience():
    evaluator = AnswerEvaluator()
    contract = TurnOrchestrator().build(
        user_text="Играла в Cyberpunk?",
        source="console",
        role="creator",
        cognitive_state=_state(memory_confidence="none", facts=[]),
    )
    ev = evaluator.evaluate(
        "Да, я играла и проходила его пару раз.",
        "Играла в Cyberpunk?",
        contract=contract,
        cognitive_state=_state(memory_confidence="none", facts=[]),
        memory_facts=[],
    )
    assert not ev.ok
    assert "false_experience" in ev.reasons


def test_evaluator_catches_false_intimacy():
    evaluator = AnswerEvaluator()
    ev = evaluator.evaluate(
        "Может быть, мы оба ищем ответы.",
        "Ты просто алгоритм?",
        contract=TurnOrchestrator().build(user_text="Ты просто алгоритм?", cognitive_state=_state()),
    )
    assert not ev.ok
    assert "false_intimacy" in ev.reasons


if __name__ == "__main__":
    tests = [
        test_direct_identity_exits_story,
        test_story_continues_only_on_explicit_continue,
        test_people_memory_disables_desires,
        test_evaluator_catches_fake_people_list,
        test_evaluator_catches_false_experience,
        test_evaluator_catches_false_intimacy,
    ]
    for test in tests:
        test()
    print("test_turn_orchestrator: ok")

