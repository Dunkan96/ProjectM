from __future__ import annotations

import sys
from stage_director import StageDirector


def main() -> None:
    text = ' '.join(sys.argv[1:]).strip() or 'Придумай страшилку про мой компьютер и тебя'
    director = StageDirector()
    decision = director.classify(text, relationship_role='creator')
    print('Input:', text)
    print('Decision:', decision.as_dict())
    print('\nPrompt block:\n')
    print(director.build_prompt_block_from_info(decision))


if __name__ == '__main__':
    main()
