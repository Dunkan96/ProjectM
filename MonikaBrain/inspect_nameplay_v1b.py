from __future__ import annotations

import sys
from stage_director import StageDirector
from response_guard import ResponseGuard


def main() -> None:
    text = " ".join(sys.argv[1:]).strip() or "Да давай придумай мне ещё кличек"
    social = {"aliases": ["Дунканыч", "Дунканоид", "главный балда", "тестировщик моей психики"]}
    d = StageDirector()
    decision = d.classify(text, relationship_role="creator", social_memory=social)
    print("Input:", text)
    print("Stage:", decision.as_dict())
    print("\nPrompt block:\n" + d.build_prompt_block_from_info(decision))
    g = ResponseGuard()
    samples = [
        '1. Дунканоид\n2. Главный балда',
        '"Главный балда", "Дунканоид", "Тестировщик моей психики" — ты же не против?',
        'Стримовый ведьмак, Кнопочный барон, Хаос-дирижёр, Босс тестов.',
    ]
    for sample in samples:
        print("\nSample:", sample)
        print(g.assess(sample, text, {"relationship_role": "creator", "social_memory": social}))


if __name__ == "__main__":
    main()
