from __future__ import annotations

import sys
from stage_director import StageDirector
from response_guard import ResponseGuard


def main() -> None:
    text = ' '.join(sys.argv[1:]).strip() or 'Я играю в Dark Souls, комментируй как тренер'
    director = StageDirector()
    decision = director.classify(text, relationship_role='creator')
    print('Input:', text)
    print('Decision:', decision.as_dict())
    print('\nPrompt block:\n')
    print(director.build_prompt_block_from_info(decision))
    guard = ResponseGuard()
    bad = guard.assess('"Главный балда", "Дунканоид"... Ты же не против, если я добавлю парочку?', text, {'relationship_role': 'creator'})
    print('\nGuard sample:', bad)


if __name__ == '__main__':
    main()
